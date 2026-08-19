from pathlib import Path

import pytest

FIXTURE_CORPUS = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def fixture_corpus() -> Path:
    """Path to the handcrafted fixture corpus CLI subcommands are tested against (Seam B)."""
    return FIXTURE_CORPUS
