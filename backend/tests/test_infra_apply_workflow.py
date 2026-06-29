"""Guards for the auto-apply Terraform CI path (issue #452).

The v3.8-v3.11 deploys hung because `infra/migrations.tf` was merged to `main`
but never `terraform apply`-ed, so the `autotiers-prod-migrate` task family did
not exist when the deploy workflow tried to use it. The fix establishes a
reviewed, automated apply path:

  - `.github/workflows/infra.yml` plans on PRs touching `infra/**` (posting the
    plan for review) and applies on merge to `main`.
  - `infra/main.tf` declares an S3 remote backend + DynamoDB lock so CI shares
    one authoritative state and concurrent applies cannot corrupt it.
  - `infra/backend.hcl` carries the non-secret backend values.
  - `deploy.yml` documents the infra→apply→release ordering.

These tests pin the structural invariants by reading the files — no live AWS.
A future edit that re-comments the backend, drops the plan/apply split, or
removes the lock would reopen the exact hole this issue closed, and trips here.
"""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "infra.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
MAIN_TF = REPO_ROOT / "infra" / "main.tf"
BACKEND_HCL = REPO_ROOT / "infra" / "backend.hcl"
CI_APPLY_POLICY = REPO_ROOT / "infra" / "ci-apply-policy.json"
CI_APPLY_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "terraform-ci-apply.md"


class TestRemoteStateBackend:
    TEXT = MAIN_TF.read_text()

    def test_backend_is_active_not_commented(self):
        """The S3 backend must be a live block. A commented-out backend means
        state lives only on whoever last applied locally — the pre-#452 state
        where CI could not apply at all."""
        lines = [ln.strip() for ln in self.TEXT.splitlines()]
        assert any(ln == 'backend "s3" {}' for ln in lines), (
            "infra/main.tf must declare an active `backend \"s3\" {}` block"
        )
        # No commented backend stanza masquerading as the real one.
        assert "# backend \"s3\"" not in self.TEXT

    def test_backend_is_partial_for_offline_init(self):
        """The block is intentionally EMPTY (partial) so credential-free
        `terraform init -backend=false` (validate/test) still works; concrete
        values are supplied via -backend-config=backend.hcl."""
        assert 'backend "s3" {}' in self.TEXT


class TestBackendHcl:
    TEXT = BACKEND_HCL.read_text()

    def test_required_keys_present(self):
        for key in ("bucket", "key", "region", "dynamodb_table", "encrypt"):
            assert f"{key}" in self.TEXT, f"backend.hcl missing {key}"

    def test_locking_table_configured(self):
        """A DynamoDB lock table is the locking half of issue #452 AC4."""
        assert "dynamodb_table" in self.TEXT
        assert "autotiers-terraform-locks" in self.TEXT

    def test_state_encrypted(self):
        assert "encrypt" in self.TEXT and "true" in self.TEXT


class TestInfraWorkflow:
    TEXT = INFRA_WORKFLOW.read_text()
    DOC = yaml.safe_load(INFRA_WORKFLOW.read_text())

    def test_yaml_parses(self):
        assert isinstance(self.DOC, dict)

    def test_triggers_on_pr_and_push_to_infra(self):
        # PyYAML parses the bare `on:` key as the boolean True.
        on = self.DOC.get("on") or self.DOC.get(True)
        assert "pull_request" in on and "push" in on
        assert "infra/**" in on["pull_request"]["paths"]
        assert on["push"]["branches"] == ["main"]
        assert "infra/**" in on["push"]["paths"]

    def test_has_plan_and_apply_jobs(self):
        jobs = self.DOC["jobs"]
        assert "plan" in jobs and "apply" in jobs

    def test_plan_only_on_pull_request(self):
        cond = self.DOC["jobs"]["plan"]["if"]
        assert "github.event_name == 'pull_request'" in cond
        # Same-repo gate: prod TF_VAR_* secrets must never reach forked-PR code.
        assert "head.repo.full_name == github.repository" in cond

    def test_apply_only_on_push(self):
        assert self.DOC["jobs"]["apply"]["if"] == "github.event_name == 'push'"

    def test_plan_runs_validate_and_test(self):
        """The PR job must run validate + `terraform test` so infra/tests/*.tftest.hcl
        is actually enforced in CI, and must produce a plan to review."""
        assert "terraform validate" in self.TEXT
        assert "terraform test" in self.TEXT
        assert "terraform plan" in self.TEXT

    def test_plan_posts_pr_comment(self):
        """Acceptance criterion 1: the plan is posted for review."""
        assert "actions/github-script" in self.TEXT
        assert "createComment" in self.TEXT or "updateComment" in self.TEXT

    def test_apply_is_auto_approve(self):
        """Acceptance criterion 2: apply runs automatically on merge."""
        assert "terraform apply -auto-approve" in self.TEXT

    def test_offline_checks_use_backend_false(self):
        """validate/test must init without the backend so they need no creds and
        do not touch S3 (keeps the mock_provider tests offline)."""
        assert "terraform init -backend=false" in self.TEXT

    def test_real_init_uses_backend_config(self):
        assert "-backend-config=backend.hcl" in self.TEXT

    def test_apply_concurrency_serializes(self):
        """Acceptance criterion 4: applies must be serialized so they cannot
        corrupt state; cancel-in-progress must be false so a second apply queues
        rather than aborting a half-finished one."""
        apply = self.DOC["jobs"]["apply"]
        assert apply["concurrency"]["group"] == "terraform-apply-production"
        assert apply["concurrency"]["cancel-in-progress"] is False


class TestDeployOrderingDocumented:
    TEXT = DEPLOY_WORKFLOW.read_text()

    def test_deploy_documents_infra_ordering(self):
        """Acceptance criterion 3: deploy must document the required ordering
        relative to the infra apply."""
        assert "infra.yml" in self.TEXT
        assert "452" in self.TEXT
        assert "terraform-ci-apply.md" in self.TEXT


class TestCiApplyPolicy:
    def test_policy_is_valid_json(self):
        doc = json.loads(CI_APPLY_POLICY.read_text())
        assert doc["Version"] == "2012-10-17"
        assert isinstance(doc["Statement"], list) and doc["Statement"]

    def test_policy_grants_state_bucket_and_lock(self):
        doc = json.loads(CI_APPLY_POLICY.read_text())
        sids = {s.get("Sid") for s in doc["Statement"]}
        assert "TerraformStateBucket" in sids
        assert "TerraformStateLock" in sids


class TestBootstrapRunbook:
    def test_runbook_exists(self):
        assert CI_APPLY_RUNBOOK.is_file()

    def test_runbook_covers_bootstrap_and_locking(self):
        text = CI_APPLY_RUNBOOK.read_text().lower()
        assert "bootstrap" in text
        assert "migrate-state" in text or "migrate state" in text
        assert "lock" in text
