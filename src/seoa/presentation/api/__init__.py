"""HTTP surface: REST API (/v1) and server-rendered pages."""

from seoa.presentation.api.app import create_app
from seoa.presentation.api.errors import ApiError

__all__ = ["ApiError", "create_app"]
