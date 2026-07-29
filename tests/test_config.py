from pathlib import Path

from sndocs.config import load_settings


def test_project_site_and_repository_settings():
    root = Path(__file__).parents[1]

    settings = load_settings(root / "pipeline.toml")

    assert settings.site_name == "sndocs"
    assert settings.site_url == "https://sndocs.com"
    assert settings.repo_url == "https://github.com/vbilgin/sndocs.com"
    assert settings.repo_name == "vbilgin/sndocs.com"
    assert settings.repository == "ServiceNow/ServiceNowDocs"
