"""Top-level package for Realtime GUI."""

from . import dc
__all__ = ["dc", "rpc_client"]

try:
    from ._version import version as __version__
    from ._version import version_tuple
except ImportError:
    __version__ = "unknown version"
    version_tuple = (0, 0, "unknown version")
