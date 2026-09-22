"""What the published Server-PT sources claim about the repository.

A source manifest is only evidence while every identifier in it resolves and
every digest in it matches. A forty-one character revision resolves to nothing,
so the entry it belongs to states a provenance that cannot be checked -- which
is indistinguishable, to a later reader, from one that was never checked.

The rendering check is here for the same reason. A heading written directly
under a Markdown table is not a heading: the table swallows the line, so the
section it announces has no heading element and no anchor to link to. Building
the site proves the build succeeded, not that the page says what it meant to.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "reference" / "server-pt" / "source-manifest.json"
BRIEF = (
    ROOT / "docs" / "engineering" / "change-briefs" / "server-pt-goal-foundations.md"
)
MKDOCS_CONFIG = ROOT / "mkdocs.yml"

#: The repository path the published archive stores under `archive_path`.
ARCHIVE_ROOT = "docs/reference/server-pt/"

ATX_HEADING = re.compile(r"^#{1,6} \S")
TABLE_ROW = re.compile(r"^\s*\|")


def _git_bytes(*arguments: str) -> bytes:
    """Return one read-only git command's exact bytes, never re-encoded.

    Binary throughout on purpose: a stored blob is bytes, and decoding it
    through the console's locale before measuring it would make the size and
    digest depend on where the suite happens to run.
    """
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(
            f"git could not answer {arguments!r}: "
            f"{completed.stderr.decode('utf-8', 'replace').strip()}"
        )
    return completed.stdout


def _git(*arguments: str) -> str:
    """Return one read-only git command's output as text."""
    return _git_bytes(*arguments).decode("utf-8")


def _errata() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["revision_errata"]


def test_the_manifest_revision_errata_identify_real_revisions() -> None:
    """Every declared revision is a forty-character commit that resolves."""
    entries = _errata()
    assert entries

    for entry in entries:
        for key in ("original_declaration_revision", "current_revision_from"):
            revision = entry[key]
            assert len(revision) == 40, (entry["archive_path"], key, revision)
            assert re.fullmatch(r"[0-9a-f]{40}", revision), revision
            kind = _git("cat-file", "-t", revision).strip()
            assert kind == "commit", (entry["archive_path"], key, revision, kind)


def test_the_manifest_errata_bytes_and_digests_match_their_revisions() -> None:
    """The recorded sizes and digests are the ones those revisions hold.

    Nothing here rewrites history to agree with a digest: the comparison runs
    the other way, from the stored Git objects to the published claim.
    """
    from hashlib import sha256

    for entry in _errata():
        path = entry["archive_path"]
        assert path.startswith("evidence/"), path
        repository_path = ARCHIVE_ROOT + path

        original = _git_bytes(
            "cat-file",
            "-p",
            f"{entry['original_declaration_revision']}:{repository_path}",
        )
        current = _git_bytes(
            "cat-file", "-p", f"{entry['current_revision_from']}:{repository_path}"
        )

        assert len(original) == entry["original_bytes"], path
        assert sha256(original).hexdigest() == entry["original_sha256"], path
        assert len(current) == entry["current_bytes"], path
        assert sha256(current).hexdigest() == entry["current_sha256"], path
        assert (
            _git(
                "rev-parse", f"{entry['current_revision_from']}:{repository_path}"
            ).strip()
            == entry["current_blob"]
        ), path


def test_no_maintained_heading_is_swallowed_by_the_table_above_it() -> None:
    """A heading needs the blank line that separates it from a table.

    This is the source-level invariant behind the rendering check below, and
    it needs no documentation toolchain, so it runs everywhere the suite does.
    """
    offenders: list[tuple[str, int, str]] = []
    for path in sorted((ROOT / "docs" / "engineering").rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines[1:], start=1):
            if ATX_HEADING.match(line) and TABLE_ROW.match(lines[index - 1]):
                offenders.append((str(path.relative_to(ROOT)), index + 1, line))
    assert offenders == []


def test_the_risk_l_headings_render_outside_the_tables_above_them() -> None:
    """Every risk-L heading of the brief renders as a heading, with an anchor.

    Rendered with the extensions `mkdocs.yml` actually configures, so this is
    the project's own Markdown pipeline rather than a generic one. The heading
    that was swallowed announced the previous correction, so the check covers
    all of them rather than only the one this change added.
    """
    markdown = pytest.importorskip(
        "markdown",
        reason="the documentation extra (`.[docs]`) is not installed here",
    )
    yaml = pytest.importorskip(
        "yaml",
        reason="the documentation extra (`.[docs]`) is not installed here",
    )
    configured = yaml.safe_load(
        MKDOCS_CONFIG.read_text(encoding="utf-8").replace("!!python/name:", "")
    )
    extensions: list[str] = []
    configuration: dict[str, dict] = {}
    for entry in configured["markdown_extensions"]:
        if isinstance(entry, str):
            extensions.append(entry)
            continue
        ((name, options),) = entry.items()
        extensions.append(name)
        configuration[name] = options or {}

    source = BRIEF.read_text(encoding="utf-8")
    html = markdown.markdown(
        source,
        extensions=extensions,
        extension_configs=configuration,
    )

    written = [
        line[3:].strip()
        for line in source.splitlines()
        if line.startswith("## ") and line.rstrip().endswith("(risk L)")
    ]
    assert len(written) >= 2, written

    rendered = {
        match.group(2): match.group(1)
        for match in re.finditer(r'<h2 id="([^"]+)">(.+?)</h2>', html, re.DOTALL)
    }
    for title in written:
        # The heading text renders with its inline code as markup, so the
        # comparison is on the words around it, which is what makes the
        # difference between a heading and a swallowed table row.
        plain = title.replace("`", "")
        matched = [
            (text, anchor)
            for text, anchor in rendered.items()
            if plain.split(" at ")[0] in re.sub(r"<[^>]+>", "", text)
        ]
        assert matched, f"{title!r} did not render as a heading"
        assert f'href="#{matched[0][1]}"' in html, f"{title!r} has no anchor"

    # And no risk-L heading survived inside a table cell.
    assert not re.search(r"<td>[^<]*## 2026", html)
