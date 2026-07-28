"""
KickTV — Providers Package

Content provider architecture with pluggable backends.
"""

from app.providers.base import BaseProvider, VideoResult

__all__ = ["BaseProvider", "VideoResult"]
