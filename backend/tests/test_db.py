"""Tests for db queries: playlists, pruning, and search."""
import db


def _seed_track(conn, *, title="Song", album="Album", artist="Artist", path=None):
    artist_id = db.upsert_artist(conn, artist)
    album_id = db.upsert_album(conn, album, artist_id, None, None)
    if path is None:
        path = "/music/%s-%s.mp3" % (artist, title)
    track_id = db.upsert_track(conn, title, album_id, artist_id, None, None, path)
    return track_id, album_id, artist_id


# --- Playlists ------------------------------------------------------------

def test_add_tracks_assigns_contiguous_positions(conn):
    t1, _, _ = _seed_track(conn, title="A", path="/m/a.mp3")
    t2, _, _ = _seed_track(conn, title="B", path="/m/b.mp3")
    t3, _, _ = _seed_track(conn, title="C", path="/m/c.mp3")
    pid = db.create_playlist(conn, "Mix")
    for t in (t1, t2, t3):
        db.add_track_to_playlist(conn, pid, t)
    ids = [t["id"] for t in db.get_playlist(conn, pid)["tracks"]]
    assert ids == [t1, t2, t3]


def test_add_duplicate_track_is_noop(conn):
    t1, _, _ = _seed_track(conn, title="A", path="/m/a.mp3")
    pid = db.create_playlist(conn, "Mix")
    db.add_track_to_playlist(conn, pid, t1)
    db.add_track_to_playlist(conn, pid, t1)
    assert len(db.get_playlist(conn, pid)["tracks"]) == 1


def test_remove_track_compacts_positions(conn):
    ids = [_seed_track(conn, title=str(i), path="/m/%d.mp3" % i)[0] for i in range(3)]
    pid = db.create_playlist(conn, "Mix")
    for t in ids:
        db.add_track_to_playlist(conn, pid, t)
    db.remove_track_from_playlist(conn, pid, ids[0])
    rows = conn.execute(
        "SELECT track_id, position FROM playlist_tracks WHERE playlist_id=? ORDER BY position",
        (pid,),
    ).fetchall()
    assert [r["position"] for r in rows] == [0, 1]
    assert [r["track_id"] for r in rows] == [ids[1], ids[2]]


def test_reorder_reverses_order(conn):
    ids = [_seed_track(conn, title=str(i), path="/m/%d.mp3" % i)[0] for i in range(3)]
    pid = db.create_playlist(conn, "Mix")
    for t in ids:
        db.add_track_to_playlist(conn, pid, t)
    db.reorder_playlist(conn, pid, list(reversed(ids)))
    out = [t["id"] for t in db.get_playlist(conn, pid)["tracks"]]
    assert out == list(reversed(ids))


def test_reorder_ignores_foreign_ids_and_appends_omitted(conn):
    ids = [_seed_track(conn, title=str(i), path="/m/%d.mp3" % i)[0] for i in range(3)]
    pid = db.create_playlist(conn, "Mix")
    for t in ids:
        db.add_track_to_playlist(conn, pid, t)
    # Only mention the last track + a bogus id; the rest must be appended,
    # nothing dropped.
    db.reorder_playlist(conn, pid, [ids[2], 9999])
    out = [t["id"] for t in db.get_playlist(conn, pid)["tracks"]]
    assert out[0] == ids[2]
    assert set(out) == set(ids)
    assert len(out) == 3


# --- Pruning --------------------------------------------------------------

def test_prune_orphans_removes_unreferenced_album_and_artist(conn):
    t1, album1, artist1 = _seed_track(conn, artist="Keep", album="KeepAlbum", path="/m/k.mp3")
    t2, album2, artist2 = _seed_track(conn, artist="Drop", album="DropAlbum", path="/m/d.mp3")
    conn.execute("UPDATE albums SET cover_path=? WHERE id=?", ("/covers/2.jpg", album2))

    removed = db.delete_tracks(conn, [t2])
    assert removed == 1
    covers = db.prune_orphans(conn)

    assert covers == ["/covers/2.jpg"]
    remaining_albums = {r["id"] for r in conn.execute("SELECT id FROM albums").fetchall()}
    remaining_artists = {r["id"] for r in conn.execute("SELECT id FROM artists").fetchall()}
    assert remaining_albums == {album1}
    assert remaining_artists == {artist1}


def test_delete_tracks_empty_is_safe(conn):
    assert db.delete_tracks(conn, []) == 0


# --- Search ---------------------------------------------------------------

def test_escape_fts():
    assert db._escape_fts("") == ""
    assert db._escape_fts("   ") == ""
    assert db._escape_fts("hello world") == '"hello"* "world"*'
    assert db._escape_fts('a"b') == '"a"* "b"*'


def test_search_matches_each_kind(conn):
    db.upsert_track(
        conn,
        "Another Brick",
        db.upsert_album(conn, "The Wall", db.upsert_artist(conn, "Pink Floyd"), 1979, None),
        db.upsert_artist(conn, "Pink Floyd"),
        None,
        None,
        "/m/brick.mp3",
    )
    db.rebuild_search_index(conn)

    assert any(t["title"] == "Another Brick" for t in db.search(conn, "brick")["tracks"])
    assert any(a["title"] == "The Wall" for a in db.search(conn, "wall")["albums"])
    assert any(ar["name"] == "Pink Floyd" for ar in db.search(conn, "floyd")["artists"])
    assert db.search(conn, "") == {"artists": [], "albums": [], "tracks": []}
