from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings


if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run("app.api.server:app", host=settings.server_host, port=settings.server_port, reload=False)
