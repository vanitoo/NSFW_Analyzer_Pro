from __future__ import annotations

import os
import shutil
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
OPENCLIP_CACHE_DIR = HUGGINGFACE_CACHE_DIR / "open_clip"
RAMPP_CACHE_DIR = CACHE_DIR / "rampp"
TFHUB_CACHE_DIR = CACHE_DIR / "tfhub"
OPENNSFW2_CACHE_DIR = CACHE_DIR / "opennsfw2"
OPENNSFW2_WEIGHTS = OPENNSFW2_CACHE_DIR / "open_nsfw_weights.h5"
GANTMAN_CACHE_DIR = CACHE_DIR / "gantman"

_LEGACY_CACHE_DIR = Path.home() / ".cache" / "nsfw-analyzer-pro"
_LEGACY_OPENNSFW2_WEIGHTS = (
    _LEGACY_CACHE_DIR
    / "opennsfw2"
    / ".opennsfw2"
    / "weights"
    / "open_nsfw_weights.h5"
)


def _move_if_missing(source: Path, destination: Path) -> None:
    if not source.exists() or destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(destination))
    except OSError:
        # Cache migration is best-effort; a failed move must not prevent startup.
        pass


def migrate_legacy_cache() -> None:
    """Best-effort migration from the old per-user cache to the project cache."""
    if os.getenv("NSFW_ANALYZER_CACHE_DIR"):
        return

    try:
        if _LEGACY_CACHE_DIR.resolve() == CACHE_DIR:
            return
    except OSError:
        return

    _move_if_missing(_LEGACY_CACHE_DIR / "huggingface", HUGGINGFACE_CACHE_DIR)
    _move_if_missing(_LEGACY_CACHE_DIR / "tfhub", TFHUB_CACHE_DIR)
    _move_if_missing(_LEGACY_CACHE_DIR / "gantman", GANTMAN_CACHE_DIR)
    _move_if_missing(_LEGACY_CACHE_DIR / "downloads", DOWNLOADS_DIR)
    _move_if_missing(_LEGACY_OPENNSFW2_WEIGHTS, OPENNSFW2_WEIGHTS)


def configure_cache_environment() -> None:
    """Point model frameworks at the application's cache directory."""
    migrate_legacy_cache()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    HUGGINGFACE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OPENCLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RAMPP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TFHUB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OPENNSFW2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GANTMAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(HUGGINGFACE_CACHE_DIR)
    os.environ["HF_HUB_CACHE"] = str(HUGGINGFACE_CACHE_DIR / "hub")
    os.environ["TFHUB_CACHE_DIR"] = str(TFHUB_CACHE_DIR)
