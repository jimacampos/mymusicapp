"""Shared pytest fixtures.

The app modules read DATA_DIR/DB_PATH/COVERS_DIR at import time, so we point
them at a throwaway temp directory *before* anything imports `db` or `main`.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

# Isolate the app's on-disk state for the whole test session.
_TMP = tempfile.mkdtemp(prefix="mymusic-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["COVERS_DIR"] = os.path.join(_TMP, "covers")
os.environ.setdefault("MUSIC_DIR", os.path.join(_TMP, "music"))

import pytest  # noqa: E402

import db  # noqa: E402


@pytest.fixture
def conn():
    """A fresh in-memory database with the full schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db.init_db(c)
    yield c
    c.close()
