"""Voice dataset builder: turn YouTube URLs into TTS-ready training datasets."""

from .config import BuildConfig
from .pipeline import build_dataset

__all__ = ["BuildConfig", "build_dataset"]
__version__ = "0.1.0"
