"""repolens — x-ray any codebase in one command."""

__version__ = "0.3.2"

from .analyzer import analyze  # noqa: E402,F401  (public API)

__all__ = ["analyze", "__version__"]
