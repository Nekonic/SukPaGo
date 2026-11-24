import pytest

from sukpago import paths


@pytest.fixture
def model_path():
    """models/ 아래 경로를 돌려준다. 없으면 테스트를 건너뛴다."""

    def _get(*parts: str):
        p = paths.models_dir().joinpath(*parts)
        if not p.exists():
            pytest.skip(f"모델 없음: {p} (uv run python tools/download_models.py 로 받으세요)")
        return p

    return _get
