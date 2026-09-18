"""Repo-root compatibility shim for managed-cloud (Render) deploys.

Render's stock Python web-service start command is ``uvicorn app.main:app``
running from the repository root, where the real package lives under
``backend/app``. This shim lets that stock command boot the FastAPI app
unchanged. The render.yaml blueprint (``uvicorn backend.app.main:app``) and the
Docker image (which copies ``backend/app`` into ``/app/app``) do not use it.
"""

from backend.app.main import app  # noqa: F401