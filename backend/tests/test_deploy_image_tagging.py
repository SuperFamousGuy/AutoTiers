"""Guards for versioned Docker image tagging in the deploy workflow (issue #188).

The deploy workflow used to push only `:latest`, so a release that shipped a
broken image had no easy recovery path (rebuild + re-push the old code). The fix
tags every build with both `:latest` AND an immutable versioned tag (the release
name, e.g. `v1.2.3`), so a prior good image is always sitting in ECR ready for an
ECS-level rollback.

These tests pin the structural invariants of that change by reading
`.github/workflows/deploy.yml` and the rollback runbook — no live AWS.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
ROLLBACK_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "deploy-rollback.md"


class TestVersionedImageTag:
    TEXT = DEPLOY_WORKFLOW.read_text()

    def test_release_tag_is_resolved(self):
        """A step must derive the versioned tag from the release name."""
        assert "github.event.release.tag_name" in self.TEXT
        assert "steps.tags.outputs.release_tag" in self.TEXT

    def test_workflow_dispatch_has_fallback_tag(self):
        """Manual dispatch has no release, so the tag must fall back to a SHA
        rather than producing an empty `repo:` reference."""
        assert "manual-${GITHUB_SHA::7}" in self.TEXT

    def test_release_tag_read_from_env_not_interpolated_into_script(self):
        """The release name is attacker-influenceable; it must reach the shell
        via an env var, not direct `${{ }}` interpolation inside run:."""
        assert "RELEASE_TAG: ${{ github.event.release.tag_name }}" in self.TEXT
        # The bare interpolation must NOT appear inside a shell command line.
        assert 'RELEASE_TAG="${{ github.event.release.tag_name }}"' not in self.TEXT

    def test_build_tags_both_latest_and_version(self):
        """docker build must carry both the moving :latest tag and the
        immutable versioned tag. The versioned tag must reach the shell via the
        IMAGE_TAG env var (not direct interpolation) and be quoted."""
        assert "IMAGE_TAG: ${{ steps.tags.outputs.release_tag }}" in self.TEXT
        assert '-t "${{ vars.ECR_REPO }}:latest"' in self.TEXT
        assert '-t "${{ vars.ECR_REPO }}:${IMAGE_TAG}"' in self.TEXT

    def test_pushes_both_tags(self):
        """Both tags must be pushed — a built-but-unpushed versioned tag is no
        use for rollback. The versioned push uses the quoted IMAGE_TAG env var
        rather than inline expression interpolation."""
        assert 'docker push "${{ vars.ECR_REPO }}:latest"' in self.TEXT
        assert 'docker push "${{ vars.ECR_REPO }}:${IMAGE_TAG}"' in self.TEXT

    def test_latest_still_pushed(self):
        """:latest must keep being pushed — the ECS task definition references
        it (acceptance criterion)."""
        assert self.TEXT.count('docker push "${{ vars.ECR_REPO }}:latest"') == 1

    def test_tags_resolved_before_build(self):
        """The tag-resolution step must precede the build that consumes it."""
        resolve_idx = self.TEXT.index("Resolve image tags")
        build_idx = self.TEXT.index("Build Docker image")
        assert resolve_idx < build_idx


class TestRollbackRunbook:
    def test_runbook_exists(self):
        assert ROLLBACK_RUNBOOK.is_file()

    def test_runbook_documents_prior_task_definition_revision(self):
        """Acceptance criterion: rollback via forcing ECS to a prior task
        definition revision pointing at the versioned tag."""
        text = ROLLBACK_RUNBOOK.read_text().lower()
        assert "task definition" in text
        assert "rollback" in text or "roll back" in text
        assert "register-task-definition" in text or "update-service" in text
