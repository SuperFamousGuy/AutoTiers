"""Guards for the Terraform-driven Alembic migration bootstrap (issue #182).

PR #179 provisions Aurora but never runs `alembic upgrade head`, so the backend
would start against an empty schema. The fix is a single dedicated one-off ECS
migrate task (alembic upgrade head) that:

  * runs on `terraform apply` (null_resource.run_migrations) with the services
    depending on it, so the schema exists before traffic;
  * runs on every release in the deploy workflow before force-redeploy, so new
    migrations are applied before the new image serves;
  * is the ONLY thing that migrates in prod — the backend/scheduler services set
    RUN_MIGRATIONS=false so the autoscaled replicas and the scheduler do not race
    `alembic upgrade head` against the same database.

These tests pin the structural and behavioural invariants of that fix. Two
flavours:

  * static guards that read the infra/workflow/entrypoint files (no live AWS);
  * a functional test that actually executes entrypoint.sh with fake binaries to
    prove the RUN_MIGRATIONS gate and the failure-blocks-startup contract.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "backend" / "scripts" / "entrypoint.sh"
MIGRATIONS_TF = REPO_ROOT / "infra" / "migrations.tf"
ECS_TF = REPO_ROOT / "infra" / "ecs.tf"
VARIABLES_TF = REPO_ROOT / "infra" / "variables.tf"
RUN_MIGRATIONS_SH = REPO_ROOT / "infra" / "scripts" / "run_migrations.sh"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


# ---------------------------------------------------------------------------
# entrypoint.sh — static guards
# ---------------------------------------------------------------------------
class TestEntrypointStatic:
    TEXT = ENTRYPOINT.read_text()

    def test_exists(self):
        assert ENTRYPOINT.exists()

    def test_fails_fast(self):
        """set -euo pipefail must stay — a failed migration must abort the boot
        so a broken schema can never partially start a serving container."""
        assert "set -euo pipefail" in self.TEXT

    def test_migration_is_gated_on_run_migrations(self):
        """Migrations run only when RUN_MIGRATIONS is true (default true)."""
        assert '"${RUN_MIGRATIONS:-true}" = "true"' in self.TEXT
        assert "alembic upgrade head" in self.TEXT

    def test_default_is_to_migrate(self):
        """Unset RUN_MIGRATIONS keeps local/compose behaviour (self-migrate)."""
        assert "RUN_MIGRATIONS:-true" in self.TEXT

    def test_still_execs_cmd(self):
        assert 'exec "$@"' in self.TEXT


# ---------------------------------------------------------------------------
# entrypoint.sh — functional: the gate actually gates, and failure aborts.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
class TestEntrypointBehaviour:
    """Run the real entrypoint with fake pg_isready/alembic/server on PATH."""

    @staticmethod
    def _write_exe(path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _run(self, tmp_path, *, run_migrations, alembic_exit=0):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        markers = tmp_path / "markers"
        markers.mkdir()

        # Fakes: pg_isready always ready; alembic records that it ran (and its
        # requested exit code); the "server" CMD records that it was exec'd.
        self._write_exe(bin_dir / "pg_isready", "exit 0\n")
        self._write_exe(
            bin_dir / "alembic",
            f'echo "$@" > "{markers}/alembic_ran"\nexit {alembic_exit}\n',
        )
        self._write_exe(
            bin_dir / "fake-server",
            f'echo started > "{markers}/server_started"\nexit 0\n',
        )

        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"  # real `python` still resolves
        env["DATABASE_URL_SYNC"] = "postgresql+psycopg2://u:p@localhost:5432/db"
        if run_migrations is not None:
            env["RUN_MIGRATIONS"] = run_migrations
        env.pop("SEED_DEV_DATA", None)  # default false → no seed step

        proc = subprocess.run(
            ["bash", str(ENTRYPOINT), "fake-server"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc, markers

    def test_default_runs_migrations_then_starts(self, tmp_path):
        proc, markers = self._run(tmp_path, run_migrations=None)
        assert proc.returncode == 0, proc.stderr
        assert (markers / "alembic_ran").exists()
        assert (markers / "server_started").exists()

    def test_run_migrations_false_skips_migrations_but_starts(self, tmp_path):
        proc, markers = self._run(tmp_path, run_migrations="false")
        assert proc.returncode == 0, proc.stderr
        assert not (markers / "alembic_ran").exists()
        assert (markers / "server_started").exists()

    def test_migration_failure_blocks_startup(self, tmp_path):
        """Criterion: a failed migration must NOT partially start the service."""
        proc, markers = self._run(tmp_path, run_migrations="true", alembic_exit=1)
        assert proc.returncode != 0
        assert (markers / "alembic_ran").exists()
        assert not (markers / "server_started").exists()


# ---------------------------------------------------------------------------
# Terraform — the dedicated migrate task and its bootstrap.
# ---------------------------------------------------------------------------
class TestMigrationsTerraform:
    TF = MIGRATIONS_TF.read_text()
    ECS = ECS_TF.read_text()
    VARS = VARIABLES_TF.read_text()

    def test_migrations_tf_exists(self):
        assert MIGRATIONS_TF.exists()

    def test_dedicated_migrate_task_definition(self):
        assert 'resource "aws_ecs_task_definition" "migrate"' in self.TF

    def test_migrate_command_is_alembic_upgrade_head(self):
        assert '["alembic", "upgrade", "head"]' in self.TF

    def test_migrate_task_does_not_self_migrate(self):
        """The migrate task's command IS the migration; the entrypoint must not
        also migrate, so RUN_MIGRATIONS=false on it too."""
        assert '{ name = "RUN_MIGRATIONS", value = "false" }' in self.TF

    def test_migrate_task_has_sync_db_secret(self):
        """alembic/env.py reads settings.database_url_sync."""
        assert "DATABASE_URL_SYNC" in self.TF
        assert "aws_secretsmanager_secret.database_url_sync.arn" in self.TF

    def test_run_migrations_null_resource(self):
        assert 'resource "null_resource" "run_migrations"' in self.TF

    def test_run_migrations_invokes_runner_script(self):
        assert "scripts/run_migrations.sh" in self.TF

    def test_reruns_on_image_or_migration_change(self):
        """triggers must include the image tag and a hash of the migrations so a
        schema change actually re-runs the task on apply."""
        assert "image_tag" in self.TF
        assert "migrations_sha" in self.TF
        assert "alembic/versions" in self.TF

    def test_bootstrap_can_be_disabled_for_planonly(self):
        assert 'variable "run_migrations_on_apply"' in self.VARS
        assert "var.run_migrations_on_apply" in self.TF

    def test_services_set_run_migrations_false(self):
        """Both prod services opt out of in-container migration (no race)."""
        assert self.ECS.count('name  = "RUN_MIGRATIONS"') >= 1  # backend block
        assert '{ name = "RUN_MIGRATIONS", value = "false" }' in self.ECS  # scheduler

    def test_services_depend_on_migrations(self):
        """Schema must exist before either service serves traffic."""
        assert self.ECS.count("null_resource.run_migrations") >= 2


# ---------------------------------------------------------------------------
# run_migrations.sh — the runner contract.
# ---------------------------------------------------------------------------
class TestRunnerScript:
    TEXT = RUN_MIGRATIONS_SH.read_text()

    def test_exists_and_executable(self):
        assert RUN_MIGRATIONS_SH.exists()
        assert os.access(RUN_MIGRATIONS_SH, os.X_OK)

    def test_runs_task_and_waits(self):
        assert "aws ecs run-task" in self.TEXT
        assert "aws ecs wait tasks-stopped" in self.TEXT

    def test_checks_exit_code(self):
        """A non-zero migration exit must fail the script (block the deploy)."""
        assert "exitCode" in self.TEXT
        assert 'if [ "${EXIT_CODE}" != "0" ]' in self.TEXT

    def test_fails_fast(self):
        assert "set -euo pipefail" in self.TEXT

    def test_supports_network_discovery_from_service(self):
        assert "--from-service" in self.TEXT
        assert "describe-services" in self.TEXT


# ---------------------------------------------------------------------------
# run_migrations.sh — functional: drive it with a fake `aws` on PATH so the
# exit-code handling and network discovery are pinned, not just string-matched.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
class TestRunnerScriptBehaviour:
    FAKE_AWS = r"""#!/usr/bin/env bash
args="$*"
case "$args" in
  *"wait tasks-stopped"*) exit 0 ;;
  *"run-task"*) printf '{"tasks":[{"taskArn":"%s"}],"failures":[]}\n' "${FAKE_TASK_ARN:-arn:aws:ecs:us-east-1:1:task/abc}"; exit 0 ;;
  *"describe-services"*"securityGroups"*) printf '%s\n' "${FAKE_SGS:-sg-123}"; exit 0 ;;
  *"describe-services"*"subnets"*) printf 'subnet-a\tsubnet-b\n'; exit 0 ;;
  *"describe-tasks"*"exitCode"*) printf '%s\n' "${FAKE_EXIT_CODE:-0}"; exit 0 ;;
  *"describe-tasks"*"stoppedReason"*) echo "Essential container exited"; exit 0 ;;
  *) echo "unexpected aws call: $args" >&2; exit 99 ;;
esac
"""

    def _run(self, tmp_path, extra_args, *, exit_code="0", task_arn=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        aws = bin_dir / "aws"
        aws.write_text(self.FAKE_AWS)
        aws.chmod(0o755)

        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["FAKE_EXIT_CODE"] = exit_code
        if task_arn is not None:
            env["FAKE_TASK_ARN"] = task_arn

        return subprocess.run(
            ["bash", str(RUN_MIGRATIONS_SH),
             "--cluster", "c", "--task-definition", "c-migrate",
             "--region", "us-east-1", *extra_args],
            env=env, capture_output=True, text=True, timeout=60,
        )

    def test_success_exits_zero(self, tmp_path):
        proc = self._run(tmp_path, ["--subnets", "s-a,s-b", "--security-groups", "sg-1"])
        assert proc.returncode == 0, proc.stderr

    def test_migration_failure_exits_nonzero(self, tmp_path):
        """A non-zero container exit code must fail the runner (block deploy)."""
        proc = self._run(
            tmp_path, ["--subnets", "s-a,s-b", "--security-groups", "sg-1"],
            exit_code="1",
        )
        assert proc.returncode != 0

    def test_task_failed_to_start_exits_nonzero(self, tmp_path):
        """run-task returning no ARN ("None") must be treated as failure."""
        proc = self._run(
            tmp_path, ["--subnets", "s-a,s-b", "--security-groups", "sg-1"],
            task_arn="None",
        )
        assert proc.returncode != 0

    def test_network_discovery_from_service(self, tmp_path):
        """With --from-service (no explicit subnets), it resolves them and runs."""
        proc = self._run(tmp_path, ["--from-service", "c-backend"])
        assert proc.returncode == 0, proc.stderr

    def test_missing_required_args_exits_nonzero(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "aws").write_text(self.FAKE_AWS)
        (bin_dir / "aws").chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        # No --cluster / --task-definition.
        proc = subprocess.run(
            ["bash", str(RUN_MIGRATIONS_SH), "--region", "us-east-1"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode != 0


# ---------------------------------------------------------------------------
# deploy.yml — migrations run before the services roll.
# ---------------------------------------------------------------------------
class TestDeployWorkflow:
    TEXT = DEPLOY_WORKFLOW.read_text()

    def test_has_migration_step(self):
        assert "Run database migrations" in self.TEXT
        assert "run_migrations.sh" in self.TEXT

    def test_migrations_run_before_force_redeploy(self):
        """Migrate, then roll the services — never the other way around."""
        migrate_idx = self.TEXT.index("Run database migrations")
        redeploy_idx = self.TEXT.index("Force redeploy backend service")
        assert migrate_idx < redeploy_idx

    def test_redeploy_pins_committed_task_definition(self):
        """Drift fix (issue #405): both services declare
        lifecycle.ignore_changes = [task_definition], so `terraform apply`
        registers a new revision when env vars change (e.g. RUN_MIGRATIONS=false)
        but never rolls the running service onto it. A bare
        --force-new-deployment reuses the service's CURRENT (stale) revision, so
        the committed env change never reaches the container and the scheduler
        keeps migrating on boot. Each redeploy must pin --task-definition to the
        Terraform-managed family so the deploy reconciles the service to the
        committed task definition."""
        assert "--task-definition ${{ vars.ECS_CLUSTER }}-backend" in self.TEXT
        assert "--task-definition ${{ vars.ECS_CLUSTER }}-scheduler" in self.TEXT

    def test_both_services_are_pinned_on_redeploy(self):
        """Neither service may be force-redeployed without an explicit
        --task-definition — that is the exact bare-redeploy path that let the
        stale revision survive (issue #405)."""
        import re

        # Each `aws ecs update-service ... --force-new-deployment` invocation
        # must also carry a --task-definition flag. Scan the actual command
        # bodies (not prose) so a bare redeploy can never sneak back in.
        cmds = re.findall(
            r"aws ecs update-service.*?--force-new-deployment",
            self.TEXT,
            re.DOTALL,
        )
        assert len(cmds) == 2, f"expected 2 redeploy commands, found {len(cmds)}"
        for cmd in cmds:
            assert "--task-definition" in cmd
