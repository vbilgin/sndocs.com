import json
import subprocess
import sys
from datetime import datetime, timezone
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
        "![Diagram & details](../image/missing.png)\n\n"
        "```text\nfirst line\n    indented line\n```\n\n"
        "<textarea>first line\n    indented line</textarea>\n\n"
        "<script>\n  window.fixtureValue = 1 + 2;\n</script>\n"
        "<table id=\"fixture-cards\" class=\"nav-card presentation\"><tbody><tr><td>\n\n"
        "[ServiceNow Vault\\[Omitted image \"vault.svg\"\\] Alt text:Protect sensitive data.]"
        "(https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/new/page.md)\n\n"
        "</td></tr></tbody></table>\n",
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
    assert loaded["theme"]["logo"] == "assets/images/branding/logomark-on-light.svg"
    assert loaded["theme"]["favicon"] == "assets/images/branding/favicon.svg"
    assert loaded["theme"]["palette"] == [{"scheme": "default"}]
    assert loaded["use_directory_urls"] is True
    assert loaded["extra"]["servicenow_copyright_year"] == datetime.now(timezone.utc).year
    plugin_names = [plugin if isinstance(plugin, str) else next(iter(plugin)) for plugin in loaded["plugins"]]
    assert ("search" in plugin_names) is search
    assert plugin_names[-1] == "minify_html"
    assert loaded["plugins"][-1] == {"minify_html": {"minify_css": False, "minify_js": False}}
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--clean", "--config-file", str(config)], check=True)
    rendered = (site / "pub" / "new" / "page" / "index.html").read_text(encoding="utf-8")
    assert "Page" in rendered and "View source" in rendered
    assert "\n\n" not in rendered
    assert "first line\n    indented line" in rendered
    assert "<script>window.fixtureValue = 1 + 2;</script>" in rendered
    assert "logomark-on-light.svg" in rendered
    assert "favicon.svg" in rendered
    assert "favicon-96x96.png" in rendered
    assert "favicon.ico" in rendered
    assert "apple-touch-icon.png" in rendered
    assert "site.webmanifest" in rendered
    assert 'class=nav-card-grid id=fixture-cards' in rendered
    assert 'class=nav-card__item href=./' in rendered
    assert "Protect sensitive data." in rendered
    assert "[ServiceNow Vault" not in rendered
    assert 'href="/assets/' not in rendered
    publication_landing = (site / "pub" / "index.html").read_text(encoding="utf-8")
    assert "href=new/page/" in publication_landing
    assert "new/page/index.html" not in publication_landing
    landing = (site / "index.html").read_text(encoding="utf-8")
    assert "Australia documentation" in landing and "Publication" in landing
    assert "logomark-on-light.svg" in landing and "site.webmanifest" in landing
    assert "independent community mirror" in rendered
    assert (
        "ServiceNow, the ServiceNow logo, Now, and other ServiceNow marks are trademarks and/or "
        "registered trademarks of ServiceNow, Inc., in the United States and/or other countries. "
        "Other company and product names may be trademarks of the respective companies with which "
        "they are associated."
    ) in rendered
    assert f"© {loaded['extra']['servicenow_copyright_year']} ServiceNow, Inc. All rights reserved." in rendered
    assert "Documentation content is redistributed under the Apache License 2.0" in rendered
    assert 'href=https://github.com/ServiceNow/ServiceNowDocs' in rendered
    assert ">ServiceNowDocs repository</a>" in rendered
    assert "assets/javascripts/versions.js" in rendered
    assert "Image omitted" in rendered and "Diagram & details" in rendered
    placeholder = (site / "pub" / "nav-only" / "index.html").read_text(encoding="utf-8")
    assert "Upstream document unavailable" in placeholder
    assert (site / "search" / "search_index.json").exists() is search
    branding = site / "assets" / "images" / "branding"
    expected_assets = {
        "apple-touch-icon.png",
        "favicon-96x96.png",
        "favicon.ico",
        "favicon.svg",
        "logomark-on-light.svg",
        "site.webmanifest",
        "web-app-manifest-192x192.png",
        "web-app-manifest-512x512.png",
    }
    assert {path.name for path in branding.iterdir()} == expected_assets
    webmanifest = json.loads((branding / "site.webmanifest").read_text(encoding="utf-8"))
    assert [icon["src"] for icon in webmanifest["icons"]] == [
        "web-app-manifest-192x192.png",
        "web-app-manifest-512x512.png",
    ]
    assert all(not icon["src"].startswith("/") for icon in webmanifest["icons"])
    assert not (work / "site").exists()
    assert report["counts"]["navigation_links"] == {
        "exact": 0,
        "repaired": 1,
        "missing": 1,
        "ambiguous": 0,
    }
    assert report["counts"]["placeholders"] == 1
    assert report["counts"]["omitted_images"] == {"occurrences": 1, "targets": 1}
