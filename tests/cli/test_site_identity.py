"""Site identity, palette, and ServiceNow attribution (issue #42, v1.1).

Splits into two halves:

* config-level pins on the shipped `mkdocs.yml` (`load_config`), and
* rendered-output checks that build the fixture corpus (Seam B) and assert the
  wordmark, repo link, five-colour palette, release-family selector, and footer
  attribution reach the page.
"""

import re
import shutil
from pathlib import Path

import material
import pytest
from click.testing import CliRunner
from mkdocs.config import load_config

from sndocs.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
MKDOCS_CONFIG = REPO_ROOT / "mkdocs.yml"
OVERRIDES_DIR = REPO_ROOT / "overrides"


def _load_shipped_config(fixture_corpus: Path):
    """`load_config` on the real `mkdocs.yml`, with `docs_dir` pointed at the fixture
    corpus so validation of an existing directory passes without a prior build."""
    return load_config(str(MKDOCS_CONFIG), docs_dir=str(fixture_corpus / "markdown"))


def _seed_normalized(fixture_corpus: Path) -> None:
    shutil.copytree(fixture_corpus / "markdown", Path(".sndocs/repo/markdown"))
    assert CliRunner().invoke(cli, ["normalize"]).exit_code == 0
    shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")
    shutil.copytree(OVERRIDES_DIR, "overrides")


# --- config-level pins -------------------------------------------------------


def test_config_sets_the_sndocs_site_identity(fixture_corpus: Path) -> None:
    config = _load_shipped_config(fixture_corpus)

    assert config["site_name"] == "sndocs"
    assert config["site_description"]
    assert config["repo_url"] == "https://github.com/vbilgin/sndocs.com"
    assert config["repo_name"] == "sndocs.com"
    # `edit_uri: ""` suppresses Material's per-page edit link (pages are generated).
    assert config["edit_uri"] == ""
    # Plain-text fallback for any context that bypasses the copyright partial.
    assert "ServiceNow" in config["copyright"]
    assert "independent" in config["copyright"]
    assert "<a" not in config["copyright"]


def test_config_palette_has_paired_schemes_a_media_default_and_a_toggle(fixture_corpus: Path) -> None:
    palette = _load_shipped_config(fixture_corpus)["theme"]["palette"]

    assert isinstance(palette, list) and len(palette) == 2
    light, dark = palette
    assert light["scheme"] == "default"
    assert dark["scheme"] == "slate"
    # `prefers-color-scheme` picks the first-visit scheme...
    assert light["media"] == "(prefers-color-scheme: light)"
    assert dark["media"] == "(prefers-color-scheme: dark)"
    # ...and each entry carries a manual toggle that overrides it.
    assert light["toggle"]["name"] and dark["toggle"]["name"]


# --- rendered output -------------------------------------------------------


@pytest.fixture
def built_index(fixture_corpus: Path, tmp_path: Path) -> str:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)
        result = runner.invoke(cli, ["build", "--no-minify"])
        assert result.exit_code == 0, result.output
        return Path(".sndocs/site/markdown/category-one/index.html").read_text()


def test_rendered_page_carries_the_text_wordmark_styling(built_index: str) -> None:
    # The wordmark is the CSS-styled site title — no <img>, no theme.icon.logo.
    assert 'class="md-header__title"' in built_index
    assert re.search(r"\.md-header__title\s*\{[^}]*font-weight:\s*700", built_index)
    assert re.search(r"\.md-header__title\s*\{[^}]*letter-spacing:\s*-0\.02em", built_index)
    # Material's default logo glyph is hidden.
    assert re.search(r"\.md-header__button\.md-logo\s*\{[^}]*display:\s*none", built_index)
    # ...so the wordmark itself has to carry the home link.
    home = re.search(r'<a class="sndocs-wordmark" href="([^"]*)">\s*sndocs\s*</a>', built_index)
    assert home is not None, built_index
    assert home.group(1) in ("..", "../..", "../../..", ".", "./")  # a relative path to the site root


def test_rendered_page_has_materials_repo_link(built_index: str) -> None:
    assert 'class="md-source"' in built_index
    assert "https://github.com/vbilgin/sndocs.com" in built_index


def test_rendered_page_applies_the_five_colour_palette(built_index: str) -> None:
    # Raw palette values, mapped onto Material's custom properties, scoped to
    # both colour schemes.
    assert '[data-md-color-scheme="default"]' in built_index
    assert '[data-md-color-scheme="slate"]' in built_index
    for hex_value in ("#d7263d", "#6a4cff", "#ff8c42", "#262626", "#faf7f2"):
        assert hex_value in built_index
    # Dark-scheme lightened brights.
    for hex_value in ("#f2536a", "#9b86ff", "#ff9e5c"):
        assert hex_value in built_index
    assert "--md-primary-fg-color" in built_index
    assert "--md-accent-fg-color" in built_index


def test_rendered_page_has_the_static_release_family_selector(built_index: str) -> None:
    assert '<details class="sndocs-release">' in built_index
    assert "<summary" in built_index
    assert "Release family" in built_index
    assert "Australia" in built_index
    # Marked current, and no navigation anywhere in the disclosure.
    assert "sndocs-release__item--current" in built_index
    disclosure = built_index[built_index.index('<details class="sndocs-release">'):]
    disclosure = disclosure[: disclosure.index("</details>")]
    assert 'aria-current="true"' in disclosure
    assert "<a " not in disclosure and "href=" not in disclosure


def test_rendered_footer_attributes_content_to_servicenow(built_index: str) -> None:
    assert 'class="md-copyright"' in built_index
    # Line 1: content copyright + source repo + licence, both linked.
    assert "ServiceNow, Inc." in built_index
    assert 'href="https://github.com/ServiceNow/ServiceNowDocs"' in built_index
    assert 'href="https://www.apache.org/licenses/LICENSE-2.0"' in built_index
    # Line 2: independence + trademark statement.
    assert "not affiliated with, endorsed by, or" in built_index
    assert "trademarks of ServiceNow, Inc." in built_index
    # Line 3: unchanged.
    assert "Made with" in built_index and "Material for MkDocs" in built_index


# --- vendored-partial drift guard ---------------------------------------


def test_vendored_header_tracks_installed_material() -> None:
    """`overrides/partials/header.html` is a copy of Material's own header partial
    plus two tagged `sndocs:` additions. Assert every non-blank line of the
    *installed* template still appears, in order, in our copy (as a substring, so
    the one wrapped line — `{{ config.site_name }}` inside our `<a>` — still
    matches). A Material upgrade that restructures the partial fails here instead
    of silently shadowing the upstream version. See ADR 0003."""
    template = Path(material.__file__).parent / "templates" / "partials" / "header.html"
    # Drop Jinja comment blocks from both sides (ours and upstream carry
    # different ones) before comparing.
    strip_comments = lambda text: re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)
    upstream = strip_comments(template.read_text())
    ours = strip_comments((OVERRIDES_DIR / "partials" / "header.html").read_text())

    cursor = 0
    for line in upstream.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        found = ours.find(stripped, cursor)
        assert found != -1, f"upstream header line not found in our copy (drift?): {stripped!r}"
        cursor = found + len(stripped)
