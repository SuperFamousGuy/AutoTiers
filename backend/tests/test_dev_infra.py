"""Infrastructure guard tests.

Protect two failure modes that previously broke the Podman local dev environment:

1. web/index.html must have no truncated <link> href attributes — Vite's HTML
   parser crashes with a 500 on every request when any href is cut off mid-value
   (e.g. href="/favico" instead of "/favicon.ico"), which can happen when the
   file is read during a hot-reload while a git checkout or write is in progress.

2. web/Dockerfile must not bring package-lock.json into the build context before
   npm runs — npm bug #4828 silently skips optional platform-specific native
   bindings (e.g. rolldown's Alpine/musl binary) when a lockfile is present,
   crashing Vite on startup inside the container.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
WEB_DIR = REPO_ROOT / "web"
BACKEND_DIR = REPO_ROOT / "backend"


class _LinkHrefCollector(HTMLParser):
    """Collect href values from all <link> tags."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "link":
            d = dict(attrs)
            if d.get("href"):
                self.hrefs.append(d["href"])


class TestIndexHtml:
    HTML = WEB_DIR / "index.html"

    def test_file_exists(self):
        assert self.HTML.exists()

    def test_local_link_hrefs_have_file_extensions(self):
        """Every local /path href in a <link> tag must end with a file extension.

        Catches mid-write truncation: href="/favico" has no extension and would
        fail this check, while the complete href="/favicon.ico" passes.
        Works regardless of which <link> tags are present — vacuously passes
        when there are none, and protects each one as links are added.
        """
        collector = _LinkHrefCollector()
        collector.feed(self.HTML.read_text(encoding="utf-8"))
        collector.close()

        for href in collector.hrefs:
            if href.startswith("/"):
                assert re.search(r"\.\w+$", href), (
                    f"Local <link> href looks truncated (no file extension): {href!r}"
                )


class TestWebDockerfile:
    DOCKERFILE = WEB_DIR / "Dockerfile"

    # Patterns in a COPY instruction that would bring package-lock.json into
    # the build context before npm runs, triggering npm bug #4828.
    _RISKY_PATTERNS = (
        "package-lock.json",
        "package*.json",
        "*.json",
        "npm-shrinkwrap.json",
    )

    def test_dockerfile_exists(self):
        assert self.DOCKERFILE.exists()

    def test_no_lockfile_copied_before_npm_install(self):
        """COPY instructions before 'RUN npm install/ci' must not bring in the lockfile.

        npm#4828: when package-lock.json is present in the build context at
        install time, npm silently skips optional platform-specific native
        bindings (e.g. rolldown's Alpine/musl binary), crashing Vite on startup.

        Checks explicit names and globs (package*.json, *.json) that would
        match package-lock.json. COPY . . lines that appear *after* npm install
        are intentionally excluded — the lockfile in the final image layer is
        harmless; the bug is triggered only during the install step.
        """
        lines = self.DOCKERFILE.read_text().splitlines()

        npm_install_idx = next(
            (i for i, ln in enumerate(lines) if re.search(r"RUN\s+npm\s+(install|ci)\b", ln)),
            len(lines),
        )
        pre_install_copy_lines = [
            ln.strip()
            for ln in lines[:npm_install_idx]
            if ln.strip().upper().startswith("COPY")
        ]

        for line in pre_install_copy_lines:
            for pattern in self._RISKY_PATTERNS:
                assert pattern not in line, (
                    f"COPY before 'npm install' includes '{pattern}' — "
                    f"npm#4828 silently skips optional native bindings (e.g. rolldown musl). "
                    f"Use 'COPY package.json ./' explicitly. Offending line: {line!r}"
                )


class TestBackendDockerfile:
    DOCKERFILE = BACKEND_DIR / "Dockerfile"

    def test_dockerfile_exists(self):
        assert self.DOCKERFILE.exists()

    def test_prod_cmd_has_no_uvicorn_reload(self):
        """The backend image CMD must not pass uvicorn --reload.

        This image runs in prod for both the API and the pinned single-task
        scheduler service. uvicorn --reload runs WatchFiles over /app; the
        scheduler's refresh_all writes cache files under /app (nfl_data_py,
        __pycache__), tripping a reload that restarts the process before
        APScheduler's hourly IntervalTrigger ever fires — silently freezing
        all data updates (the 2026-06-09 stale-data incident).

        Dev hot reload is opted back in via the `command:` override in
        docker-compose.yml, which is the correct place for it.
        """
        # Join backslash line-continuations into logical instructions first, so a
        # CMD reformatted across multiple lines (with `--reload` on a continuation
        # line) is still inspected as a single CMD instruction.
        logical_lines: list[str] = []
        buffer = ""
        for raw in self.DOCKERFILE.read_text().splitlines():
            buffer = f"{buffer} {raw.strip()}".strip() if buffer else raw.strip()
            if buffer.endswith("\\"):
                buffer = buffer[:-1].rstrip()
            else:
                logical_lines.append(buffer)
                buffer = ""
        if buffer:
            logical_lines.append(buffer)
        cmd_lines = [ln for ln in logical_lines if ln.upper().startswith("CMD")]
        for line in cmd_lines:
            assert "--reload" not in line, (
                "backend/Dockerfile CMD must not include '--reload' — it breaks "
                "the prod scheduler (WatchFiles reload loop starves the hourly "
                f"refresh job). Put --reload in docker-compose.yml instead. Offending line: {line!r}"
            )
