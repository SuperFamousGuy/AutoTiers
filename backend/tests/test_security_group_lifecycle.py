"""Guards for the ALB security-group zero-downtime lifecycle (issue #411).

`terraform plan` against prod drifted and wanted to **recreate** the
internet-facing ALB security group. Under Terraform's default
destroy-before-create lifecycle that drops/disrupts prod traffic: the ALB and the
ECS ingress rule both reference `aws_security_group.alb`, so the old SG is torn
down before the new one is wired in.

The fix makes any replacement of that SG safe by coupling two settings on
`aws_security_group.alb`:

  * `create_before_destroy = true` — build the replacement, repoint the ALB and
    the ECS ingress, then destroy the old SG;
  * `name_prefix` instead of `name` — required for the above, because AWS rejects
    a second SG with a duplicate fixed `name` (`InvalidGroup.Duplicate`) before
    the old one is gone.

These tests pin that contract by reading the Terraform source (no live AWS): if a
later edit reverts `name_prefix` to a fixed `name`, drops `create_before_destroy`,
or splits them apart, the guard fails.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_GROUPS_TF = REPO_ROOT / "infra" / "security_groups.tf"
RECONCILE_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "terraform-state-reconcile.md"


def _alb_sg_block(text: str) -> str:
    """Return the body of the `aws_security_group.alb` resource block.

    Brace-matches from the resource header to its closing brace so the assertions
    below are scoped to the ALB SG and never accidentally satisfied by the ECS or
    RDS security-group blocks lower in the file.
    """
    start = text.index('resource "aws_security_group" "alb"')
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError("unbalanced braces in aws_security_group.alb block")


class TestAlbSecurityGroupLifecycle:
    TEXT = SECURITY_GROUPS_TF.read_text()
    ALB = _alb_sg_block(TEXT)

    def test_security_groups_tf_exists(self):
        assert SECURITY_GROUPS_TF.exists()

    def test_alb_sg_uses_name_prefix_not_fixed_name(self):
        """A fixed `name` makes create_before_destroy impossible (duplicate name
        collision), so the ALB SG must use name_prefix."""
        assert re.search(r'^\s*name_prefix\s*=', self.ALB, re.MULTILINE), (
            "aws_security_group.alb must set name_prefix"
        )
        assert not re.search(r'^\s*name\s*=', self.ALB, re.MULTILINE), (
            "aws_security_group.alb must NOT set a fixed `name` — it blocks "
            "create_before_destroy"
        )

    def test_alb_sg_has_create_before_destroy(self):
        """The replacement must build the new SG before destroying the old one so
        the internet-facing ALB is never left without a security group."""
        assert "create_before_destroy = true" in self.ALB

    def test_create_before_destroy_lives_in_a_lifecycle_block(self):
        assert re.search(
            r"lifecycle\s*\{[^}]*create_before_destroy\s*=\s*true",
            self.ALB,
            re.DOTALL,
        )

    def test_name_prefix_preserves_human_readable_tag(self):
        """The stable identifier moves to the Name tag so console/tag lookups for
        the SG still resolve after the GroupName gains a random suffix."""
        assert re.search(
            r'name_prefix\s*=\s*"\$\{var\.app_name\}-\$\{var\.environment\}-sg-alb-"',
            self.ALB,
        )
        assert re.search(
            r'Name\s*=\s*"\$\{var\.app_name\}-\$\{var\.environment\}-sg-alb"',
            self.ALB,
        )

    def test_ecs_ingress_still_references_alb_sg(self):
        """The cascade the fix protects only exists because the ECS SG ingress
        references the ALB SG — pin that reference so the rationale stays valid."""
        assert re.search(
            r"security_groups\s*=\s*\[\s*aws_security_group\.alb\.id\s*,?\s*\]",
            self.TEXT,
        ), "ECS SG ingress must reference aws_security_group.alb.id"


class TestReconcileRunbook:
    def test_runbook_exists(self):
        assert RECONCILE_RUNBOOK.exists()

    def test_runbook_documents_the_three_drift_classes(self):
        text = RECONCILE_RUNBOOK.read_text()
        assert "create_before_destroy" in text
        assert "untaint" in text  # the run_migrations decision
        assert "ignore_changes" in text  # why task-def replacement is harmless
