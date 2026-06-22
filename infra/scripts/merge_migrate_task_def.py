#!/usr/bin/env python3
"""Build an `aws ecs register-task-definition` input for the migrate task.

Issue #395: the deploy workflow must OWN routine migration task-definition
registration so a release can never again depend on a human running
`terraform apply` locally. This module performs the pure merge half of that:
it takes the committed migrate "recipe" (migrate-task-definition.json — the
migrate-specific command/env/secrets/cpu/memory, the half that lives in git)
and folds in the account-specific values (execution role ARN, secret ARNs, and
log configuration) read live from the RUNNING backend task definition.

Why derive from the live backend task def instead of committing the ARNs?
  - Zero new GitHub variables: the execution role, secret ARNs and log group
    are already pinned on the backend task def that ECS is running right now.
  - No drift: the meaningful content (command, env, which secrets) is committed
    in git; only the account-specific ARNs are resolved live, so they can never
    go stale relative to the account.
  - Self-contained: the backend service is always running on a release, so its
    task def is guaranteed to exist. We therefore do NOT depend on the dedicated
    migrate log group / task role from infra/migrations.tf having been applied
    (that apply never running is exactly what broke v3.8-v3.11 — see #395).

The image is passed in explicitly (the freshly-pushed release tag) rather than
copied from the backend task def, so the migration runs the NEW code's
`alembic upgrade head`, not whatever revision the backend last rolled.

This module is intentionally pure (no AWS calls, no global state) so it can be
unit-tested directly; register_migrate_task_def.sh does the AWS I/O around it.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class MergeError(ValueError):
    """Raised when the backend task def can't satisfy the migrate recipe."""


def _backend_container(backend_task_def: dict[str, Any]) -> dict[str, Any]:
    containers = backend_task_def.get("containerDefinitions") or []
    if not containers:
        raise MergeError("backend task definition has no containerDefinitions")
    return containers[0]


def build_migrate_task_def(
    recipe: dict[str, Any],
    backend_task_def: dict[str, Any],
    *,
    family: str,
    image: str,
) -> dict[str, Any]:
    """Merge the committed recipe with the live backend task def.

    Returns a dict suitable as the argument to `aws ecs register-task-definition
    --cli-input-json`. Raises MergeError if the backend task def is missing a
    value the recipe needs (e.g. a secret the migrate task requires).
    """
    if not family:
        raise MergeError("family is required")
    if not image:
        raise MergeError("image is required")

    execution_role_arn = backend_task_def.get("executionRoleArn")
    if not execution_role_arn:
        raise MergeError("backend task definition has no executionRoleArn")

    backend_container = _backend_container(backend_task_def)

    # Map secret NAME -> valueFrom ARN from the backend container so the recipe
    # only has to name the secrets it needs, not pin their account-specific ARNs.
    backend_secrets = {
        s["name"]: s["valueFrom"]
        for s in (backend_container.get("secrets") or [])
        if s.get("name") and s.get("valueFrom")
    }

    backend_log_config = backend_container.get("logConfiguration")
    if not backend_log_config:
        raise MergeError("backend container has no logConfiguration to reuse")

    recipe_container = _backend_container(recipe)
    container_name = recipe_container.get("name") or "migrate"

    resolved_secrets = []
    for secret in recipe_container.get("secrets") or []:
        name = secret.get("name")
        if not name:
            raise MergeError("recipe secret entry is missing a name")
        if name not in backend_secrets:
            raise MergeError(
                f"backend task definition does not expose secret '{name}'; "
                "cannot resolve its valueFrom ARN"
            )
        resolved_secrets.append({"name": name, "valueFrom": backend_secrets[name]})

    # Reuse the backend's log group (guaranteed to exist) but stream the migrate
    # task under its own prefix so its logs stay findable.
    log_config = json.loads(json.dumps(backend_log_config))  # deep copy
    log_config.setdefault("options", {})
    log_config["options"]["awslogs-stream-prefix"] = container_name

    container = {
        "name": container_name,
        "image": image,
        "command": list(recipe_container.get("command") or []),
        "essential": bool(recipe_container.get("essential", True)),
        "environment": list(recipe_container.get("environment") or []),
        "secrets": resolved_secrets,
        "logConfiguration": log_config,
    }

    return {
        "family": family,
        "requiresCompatibilities": list(
            recipe.get("requiresCompatibilities") or ["FARGATE"]
        ),
        "networkMode": recipe.get("networkMode") or "awsvpc",
        "cpu": str(recipe["cpu"]),
        "memory": str(recipe["memory"]),
        "executionRoleArn": execution_role_arn,
        "containerDefinitions": [container],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recipe", required=True, help="path to migrate-task-definition.json"
    )
    parser.add_argument(
        "--backend-task-def",
        default="-",
        help="path to the backend task definition JSON, or '-' for stdin",
    )
    parser.add_argument("--family", required=True, help="migrate task def family")
    parser.add_argument(
        "--image", required=True, help="fully-qualified image URI to migrate with"
    )
    args = parser.parse_args(argv)

    with open(args.recipe, encoding="utf-8") as fh:
        recipe = json.load(fh)

    if args.backend_task_def == "-":
        backend_task_def = json.load(sys.stdin)
    else:
        with open(args.backend_task_def, encoding="utf-8") as fh:
            backend_task_def = json.load(fh)

    try:
        result = build_migrate_task_def(
            recipe, backend_task_def, family=args.family, image=args.image
        )
    except MergeError as exc:
        print(f"[register-migrate] ERROR: {exc}", file=sys.stderr)
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
