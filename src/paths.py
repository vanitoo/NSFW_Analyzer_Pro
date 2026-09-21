from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _cache_root() -> Path:
    override = os.getenv("NSFW_ANALYZER_CACHE_DIR")
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override))).resolve()
    return (PROJECT_ROOT / ".cache").resolve()


CACHE_DIR = _cache_root()
DOWNLOADS_DIR = CACHE_DIR / "downloads"
HUGGINGFACE_CACHE_DIR = CACHE_DIR / "huggingface"
TFHUB_CACHE_DIR = CACHE_DIR / "tfhub"
OPENNSFW2_CACHE_DIR = CACHE_DIR / "opennsfw2"
OPENNSFW2_WEIGHTS = OPENNSFW2_CACHE_DIR / "open_nsfw_weights.h5"
GANTMAN_CACHE_DIR = CACHE_DIR / "gantman"


def configure_cache_environment() -> None:
    """Point model frameworks at the application's cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    HUGGINGFACE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TFHUB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OPENNSFW2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GANTMAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(HUGGINGFACE_CACHE_DIR)
    os.environ["HF_HUB_CACHE"] = str(HUGGINGFACE_CACHE_DIR / "hub")
    os.environ["TFHUB_CACHE_DIR"] = str(TFHUB_CACHE_DIR)
