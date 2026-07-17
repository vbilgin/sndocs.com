import subprocess
import sys
from pathlib import Path

from sndocs.builder import write_mkdocs_config
from sndocs.models import Discovery, Publication, Settings
from sndocs.transform import transform_tree


def test_fixture_builds_with_material_theme(tmp_path):
    root = Path(__file__).parents[1]
    source = tmp_path / "source"
    publication = source / "markdown" / "pub"
    publication.mkdir(parents=True)
    publication.joinpath("index.md").write_text(
        "---\ntitle: Publication\n---\n# Publication\n\n"
        "- [Page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/page.md)\n",
        encoding="utf-8",
    )
    publication.joinpath("page.md").write_text(
        "---\ntitle: Page\nrelease: australia\n---\n# Page\n\n"
        "[Missing](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/missing.md)\n",
        encoding="utf-8",
    )
    settings = Settings(root, "sndocs.com", "https://sndocs.com", "Mirror", "ServiceNow/ServiceNowDocs", "llms.txt", (), "sndocs-site")
    discovery = Discovery(["australia"], "australia", [Publication("Publication", "pub", "url")], {"australia": "abc"})
    work = tmp_path / "work"
    docs = work / "docs"
    report = transform_tree(source / "markdown", docs, "australia", {"australia"}, settings.repository)
    config = write_mkdocs_config(settings, source, work, "australia", discovery)
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--clean", "--config-file", str(config)], check=True)
    rendered = (work / "site" / "pub" / "page" / "index.html").read_text(encoding="utf-8")
    assert "Page" in rendered and "View source" in rendered
    assert "independent community mirror" in rendered
    assert "assets/javascripts/versions.js" in rendered
    placeholder = (work / "site" / "pub" / "missing" / "index.html").read_text(encoding="utf-8")
    assert "Upstream document unavailable" in placeholder
    assert report["counts"]["placeholder"] == 1
