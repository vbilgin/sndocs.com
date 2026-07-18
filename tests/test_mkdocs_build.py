import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from sndocs.builder import publication_nav, write_family_landing, write_mkdocs_config
from sndocs.links import FamilyLinkResolver
from sndocs.models import Discovery, Publication, Settings
from sndocs.transform import transform_tree, write_missing_placeholders


@pytest.mark.parametrize("search", [True, False], ids=["production", "smoke"])
def test_fixture_builds_with_material_theme(tmp_path, search):
    root = Path(__file__).parents[1]
    source = tmp_path / "source"
    publication = source / "markdown" / "pub"
    publication.mkdir(parents=True)
    publication.joinpath("index.md").write_text(
        "---\ntitle: Publication\n---\n# Publication\n\n"
        "- [Page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/old/page.md)\n"
        "- [Unavailable](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/nav-only.md)\n",
        encoding="utf-8",
    )
    publication.joinpath("new").mkdir()
    publication.joinpath("new/page.md").write_text(
        "---\ntitle: Page\nrelease: australia\n---\n# Page\n\n"
        "![Diagram & details](../image/missing.png)\n",
        encoding="utf-8",
    )
    settings = Settings(root, "sndocs.com", "https://sndocs.com", "Mirror", "ServiceNow/ServiceNowDocs", "llms.txt", (), "sndocs-site")
    discovery = Discovery(["australia"], "australia", [Publication("Publication", "pub", "url")], {"australia": "abc"})
    work = tmp_path / "work"
    docs = work / "docs"
    resolver = FamilyLinkResolver(source / "markdown", "australia")
    transform_tree(
        source / "markdown",
        docs,
        "australia",
        {"australia"},
        settings.repository,
        resolver,
        finalize=False,
    )
    nav = publication_nav(source, discovery, resolver)
    write_missing_placeholders(docs, resolver)
    write_family_landing(docs, "australia", discovery)
    report = resolver.report()
    site = tmp_path / "site"
    config = write_mkdocs_config(
        settings, source, work, "australia", discovery, site_dir=site, search=search, nav=nav
    )
    loaded = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert "navigation.prune" in loaded["theme"]["features"]
    assert loaded["use_directory_urls"] is True
    assert bool(loaded["plugins"]) is search
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--clean", "--config-file", str(config)], check=True)
    rendered = (site / "pub" / "new" / "page" / "index.html").read_text(encoding="utf-8")
    assert "Page" in rendered and "View source" in rendered
    publication_landing = (site / "pub" / "index.html").read_text(encoding="utf-8")
    assert 'href="new/page/"' in publication_landing
    assert 'href="new/page/index.html"' not in publication_landing
    landing = (site / "index.html").read_text(encoding="utf-8")
    assert "Australia documentation" in landing and "Publication" in landing
    assert "independent community mirror" in rendered
    assert "assets/javascripts/versions.js" in rendered
    assert "Image omitted" in rendered and "Diagram &amp; details" in rendered
    placeholder = (site / "pub" / "nav-only" / "index.html").read_text(encoding="utf-8")
    assert "Upstream document unavailable" in placeholder
    assert (site / "search" / "search_index.json").exists() is search
    assert not (work / "site").exists()
    assert report["counts"]["navigation_links"] == {
        "exact": 0,
        "repaired": 1,
        "missing": 1,
        "ambiguous": 0,
    }
    assert report["counts"]["placeholders"] == 1
    assert report["counts"]["omitted_images"] == {"occurrences": 1, "targets": 1}
