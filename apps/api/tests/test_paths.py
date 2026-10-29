import pytest

from nova_api.config import get_settings
from nova_api.paths import repo_root
from nova_api.seed import find_docs_dir


def test_data_root_env_overrides_autodetect(monkeypatch, tmp_path):
    (tmp_path / "data" / "seed" / "sample-documents").mkdir(parents=True)
    monkeypatch.setenv("NOVA_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert repo_root() == tmp_path
        assert find_docs_dir() == tmp_path / "data" / "seed" / "sample-documents"
    finally:
        get_settings.cache_clear()


def test_missing_seed_dir_is_a_loud_error(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        with pytest.raises(FileNotFoundError, match="NOVA_DATA_ROOT"):
            find_docs_dir()
    finally:
        get_settings.cache_clear()


def test_autodetect_works_in_checkout():
    assert (repo_root() / "evals" / "datasets").is_dir()
