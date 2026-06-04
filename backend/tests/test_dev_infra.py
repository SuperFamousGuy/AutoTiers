"""Infrastructure guard tests.

Protect two failure modes that previously broke the Podman local dev environment:

1. web/index.html must have complete favicon link hrefs — Vite's HTML parser
   crashes with a 500 on every request when the href attribute is truncated
   (e.g. from a mid-write file read during hot-reload).

2. web/Dockerfile must not COPY package-lock.json — npm bug #4828 causes
   optional platform-specific native bindings (rolldown's Alpine/musl binary)
   to be silently skipped when a lockfile is present in the build context,
   crashing Vite on startup inside the container.
"""

from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
WEB_DIR = REPO_ROOT / "web"


class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icon_hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "link":
            d = dict(attrs)
            if d.get("rel") == "icon" and d.get("href"):
                self.icon_hrefs.append(d["href"])


class TestIndexHtml:
    HTML = WEB_DIR / "index.html"

    def test_file_exists(self):
        assert self.HTML.exists()

    def test_svg_favicon_href_complete(self):
        content = self.HTML.read_text(encoding="utf-8")
        assert 'href="/favicon.svg"' in content

    def test_ico_favicon_href_complete(self):
        content = self.HTML.read_text(encoding="utf-8")
        assert 'href="/favicon.ico"' in content

    def test_icon_links_parsed_with_file_extensions(self):
        collector = _LinkCollector()
        collector.feed(self.HTML.read_text(encoding="utf-8"))
        collector.close()

        assert len(collector.icon_hrefs) >= 2, (
            f"Expected at least 2 icon link hrefs (svg + ico); got {collector.icon_hrefs}"
        )
        for href in collector.icon_hrefs:
            assert "." in href and not href.endswith(("/", ".")), (
                f"Favicon href looks truncated: {href!r}"
            )


class TestWebDockerfile:
    DOCKERFILE = WEB_DIR / "Dockerfile"

    def test_dockerfile_exists(self):
        assert self.DOCKERFILE.exists()

    def test_does_not_copy_lockfile(self):
        content = self.DOCKERFILE.read_text()
        copy_lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip().upper().startswith("COPY")
        ]
        for line in copy_lines:
            assert "package-lock.json" not in line, (
                "Dockerfile must not COPY package-lock.json — "
                "npm#4828 silently skips optional native bindings (rolldown musl) "
                f"when a lockfile is present. Offending line: {line!r}"
            )
