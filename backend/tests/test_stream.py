"""Tests for HTTP Range streaming in the /api/stream endpoint."""
import os

import pytest
from fastapi.testclient import TestClient

import db
import main

DATA = bytes(range(256)) * 4  # 1024 deterministic bytes
SIZE = len(DATA)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def track_id(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "song.mp3"
    path.write_bytes(DATA)
    conn = db.get_connection()
    try:
        artist = db.upsert_artist(conn, "Artist")
        album = db.upsert_album(conn, "Album", artist, None, None)
        tid = db.upsert_track(conn, "Song", album, artist, 1, 1.0, str(path))
        conn.commit()
    finally:
        conn.close()
    return tid


def test_full_request(client, track_id):
    r = client.get(f"/api/stream/{track_id}")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(SIZE)
    assert r.content == DATA


def test_explicit_range(client, track_id):
    r = client.get(f"/api/stream/{track_id}", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-9/{SIZE}"
    assert r.headers["content-length"] == "10"
    assert r.content == DATA[0:10]


def test_open_ended_range(client, track_id):
    r = client.get(f"/api/stream/{track_id}", headers={"Range": "bytes=512-"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 512-{SIZE - 1}/{SIZE}"
    assert r.content == DATA[512:]


def test_suffix_range(client, track_id):
    r = client.get(f"/api/stream/{track_id}", headers={"Range": "bytes=-5"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes {SIZE - 5}-{SIZE - 1}/{SIZE}"
    assert r.content == DATA[-5:]


def test_invalid_range_400(client, track_id):
    r = client.get(f"/api/stream/{track_id}", headers={"Range": "bytes=abc"})
    assert r.status_code == 400


def test_unsatisfiable_range_416(client, track_id):
    r = client.get(f"/api/stream/{track_id}", headers={"Range": f"bytes={SIZE + 100}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{SIZE}"


def test_head_with_range(client, track_id):
    r = client.head(f"/api/stream/{track_id}", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["content-length"] == "10"
    assert r.content == b""


def test_missing_track_404(client):
    r = client.get("/api/stream/999999")
    assert r.status_code == 404
