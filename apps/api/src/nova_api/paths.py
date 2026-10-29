from pathlib import Path

from .config import get_settings


def repo_root() -> Path:
    """Directory holding `data/` and `evals/`.

    NOVA_DATA_ROOT wins (required when the package is installed rather than run from a
    checkout, e.g. in the Docker image); otherwise walk up from this file.
    """
    configured = get_settings().data_root
    if configured:
        return Path(configured)
    for p in Path(__file__).resolve().parents:
        if (p / "evals" / "datasets").is_dir() or (p / "data" / "seed").is_dir():
            return p
    raise FileNotFoundError("Could not locate data/ and evals/; set NOVA_DATA_ROOT")
