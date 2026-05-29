from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "docs_sample.json"


@pytest.fixture
def sample_docs() -> Path:
    return FIXTURE
