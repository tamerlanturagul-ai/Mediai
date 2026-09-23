"""Shared pytest fixtures (TASK-010).

Import path is provided by ``pythonpath = ["medi-ai"]`` in pyproject.toml,
so test modules must NOT hack ``sys.path`` (all 8 hacks removed).

Fixtures
- ``client``: a fresh ``fastapi.testclient.TestClient`` bound to the app.
  Existing test modules keep their own module-level clients (untouched);
  new tests should use this fixture instead.
- ``tmp_upload_dir``: isolates ``app.services.photo_service`` file storage
  into a per-test tmp dir and clears the in-memory quality cache, so photo
  tests never touch the real ``medi-ai/app/uploads/`` directory.
"""
from __future__ import annotations

import pytest
from app.main import app
from app.services import photo_service
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def tmp_upload_dir(tmp_path, monkeypatch) -> object:
    """Redirect photo storage to tmp_path; restore afterwards."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(photo_service, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(photo_service, "_META", {})
    return upload_dir
