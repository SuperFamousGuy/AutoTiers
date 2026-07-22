"""Tests for the migrate task-definition merge logic (issue #395).

The deploy workflow now OWNS registration of the `autotiers-prod-migrate` ECS
task definition: it merges the committed recipe (infra/migrate-task-definition.json)
with the live backend task definition and registers the result before running
migrations. These tests lock down that pure merge so a release can never again
silently depend on a hand-run `terraform apply`.

The merge module lives under infra/scripts/ (outside the `app` package), so it
is loaded by path rather than imported as a package.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MERGE_PATH = _REPO_ROOT / "infra" / "scripts" / "merge_migrate_task_def.py"
_RECIPE_PATH = _REPO_ROOT / "infra" / "migrate-task-definition.json"


def _load_merge_module():
    spec = importlib.util.spec_from_file_location("merge_migrate_task_def", _MERGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge = _load_merge_module()


@pytest.fixture
def recipe():
    return json.loads(_RECIPE_PATH.read_text())


@pytest.fixture
def backend_task_def():
    """A trimmed-down but realistic backend task definition as returned by
    `aws ecs describe-task-definition --query taskDefinition`."""
    return {
        "family": "autotiers-prod-backend",
        "executionRoleArn": "arn:aws:iam::400360841089:role/autotiers-prod-ecs-exec-role",
        "taskRoleArn": "arn:aws:iam::400360841089:role/autotiers-prod-ecs-task-role",
        "containerDefinitions": [
            {
                "name": "backend",
                "image": "400360841089.dkr.ecr.us-east-1.amazonaws.com/autotiers-backend:latest",
                "secrets": [
                    {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:1:secret:database_url"},
                    {"name": "DATABASE_URL_SYNC", "valueFrom": "arn:aws:secretsmanager:us-east-1:1:secret:database_url_sync"},
                    {"name": "JWT_SECRET", "valueFrom": "arn:aws:secretsmanager:us-east-1:1:secret:jwt_secret"},
                    {"name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:1:secret:secret_key"},
                    {"name": "ADMIN_API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:1:secret:admin_api_key"},
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "/ecs/autotiers-prod/backend",
                        "awslogs-region": "us-east-1",
                        "awslogs-stream-prefix": "ecs",
                    },
                },
            }
        ],
    }


IMAGE = "400360841089.dkr.ecr.us-east-1.amazonaws.com/autotiers-backend:v3.13"
FAMILY = "autotiers-prod-migrate"


def _build(recipe, backend_task_def, **kw):
    kw.setdefault("family", FAMILY)
    kw.setdefault("image", IMAGE)
    return merge.build_migrate_task_def(recipe, backend_task_def, **kw)


def test_family_and_image_come_from_arguments(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    assert result["family"] == FAMILY
    container = result["containerDefinitions"][0]
    # The migration must run the freshly-pushed image, NOT whatever the backend
    # task def currently points at.
    assert container["image"] == IMAGE
    assert container["image"] != backend_task_def["containerDefinitions"][0]["image"]


def test_execution_role_borrowed_from_backend(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    assert result["executionRoleArn"] == backend_task_def["executionRoleArn"]


def test_secret_value_from_resolved_by_name(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    secrets = {s["name"]: s["valueFrom"] for s in result["containerDefinitions"][0]["secrets"]}
    # Only the secrets the recipe names — not the backend's full set. (JWT_SECRET
    # / SECRET_KEY were removed with the accounts+SES teardown, so the migrate
    # recipe now names just the two database URLs.)
    assert set(secrets) == {"DATABASE_URL", "DATABASE_URL_SYNC"}
    assert "ADMIN_API_KEY" not in secrets
    assert secrets["DATABASE_URL"] == "arn:aws:secretsmanager:us-east-1:1:secret:database_url"
    # No null placeholders survive the merge.
    assert all(v for v in secrets.values())


def test_run_migrations_false_is_preserved(recipe, backend_task_def):
    """The shared entrypoint must NOT double-migrate (migrations.tf contract)."""
    result = _build(recipe, backend_task_def)
    env = {e["name"]: e["value"] for e in result["containerDefinitions"][0]["environment"]}
    assert env["RUN_MIGRATIONS"] == "false"
    assert env["RUN_SCHEDULER"] == "false"


def test_command_is_alembic_upgrade_head(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    assert result["containerDefinitions"][0]["command"] == ["alembic", "upgrade", "head"]


def test_log_group_reused_with_migrate_stream_prefix(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    log = result["containerDefinitions"][0]["logConfiguration"]
    # Reuse the backend's (guaranteed-present) log group, but stream the migrate
    # task under its own prefix so its logs stay findable.
    assert log["options"]["awslogs-group"] == "/ecs/autotiers-prod/backend"
    assert log["options"]["awslogs-stream-prefix"] == "migrate"
    # Mutating the copy must not corrupt the backend's own log config.
    assert (
        backend_task_def["containerDefinitions"][0]["logConfiguration"]["options"][
            "awslogs-stream-prefix"
        ]
        == "ecs"
    )


def test_fargate_shape_is_complete(recipe, backend_task_def):
    result = _build(recipe, backend_task_def)
    assert result["requiresCompatibilities"] == ["FARGATE"]
    assert result["networkMode"] == "awsvpc"
    # cpu/memory must be strings for register-task-definition.
    assert result["cpu"] == "256"
    assert result["memory"] == "512"
    assert isinstance(result["cpu"], str)


def test_missing_secret_on_backend_raises(recipe, backend_task_def):
    # Drop a secret the recipe *does* name (DATABASE_URL_SYNC) from the backend
    # snapshot; the merge must refuse to register a task def that can't resolve it.
    backend_task_def["containerDefinitions"][0]["secrets"] = [
        s
        for s in backend_task_def["containerDefinitions"][0]["secrets"]
        if s["name"] != "DATABASE_URL_SYNC"
    ]
    with pytest.raises(merge.MergeError, match="DATABASE_URL_SYNC"):
        _build(recipe, backend_task_def)


def test_missing_execution_role_raises(recipe, backend_task_def):
    del backend_task_def["executionRoleArn"]
    with pytest.raises(merge.MergeError, match="executionRoleArn"):
        _build(recipe, backend_task_def)


def test_missing_image_raises(recipe, backend_task_def):
    with pytest.raises(merge.MergeError, match="image"):
        _build(recipe, backend_task_def, image="")


def test_committed_recipe_has_null_placeholders():
    """The committed recipe must defer account-specific values to deploy time
    (so they can't drift); merge fills them in."""
    recipe = json.loads(_RECIPE_PATH.read_text())
    assert recipe["family"] is None
    container = recipe["containerDefinitions"][0]
    assert container["image"] is None
    assert all(s["valueFrom"] is None for s in container["secrets"])
