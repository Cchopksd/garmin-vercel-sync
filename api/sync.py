"""Vercel function entry point for the scheduled sync route.

Vercel maps a Python file directly to its matching API path.  Keeping this
small alias makes ``/api/sync`` explicit while the FastAPI app and its
authentication remain defined once in ``api.index``.
"""

from api.index import app

