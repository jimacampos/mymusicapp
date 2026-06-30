import { useCallback, useEffect, useRef, useState } from "react";
import { AlbumSummary, PlaylistSummary, SearchResults, Stats, api } from "./api";
import { Library } from "./views/Library";
import { Album } from "./views/Album";
import { Search } from "./views/Search";
import { Playlists } from "./views/Playlists";
import { Playlist } from "./views/Playlist";
import { Player } from "./components/Player";

type View =
  | { name: "library" }
  | { name: "album"; id: number }
  | { name: "search" }
  | { name: "playlists" }
  | { name: "playlist"; id: number };

export default function App() {
  const [albums, setAlbums] = useState<AlbumSummary[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [playlists, setPlaylists] = useState<PlaylistSummary[]>([]);
  const [view, setView] = useState<View>({ name: "library" });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [rescanning, setRescanning] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);

  const loadLibrary = useCallback(() => {
    api.albums().then(setAlbums).catch(() => undefined);
    api.stats().then(setStats).catch(() => undefined);
  }, []);

  const loadPlaylists = useCallback(() => {
    api.playlists().then(setPlaylists).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadLibrary();
    loadPlaylists();
  }, [loadLibrary, loadPlaylists]);

  // Debounced search.
  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults(null);
      return;
    }
    debounceRef.current = window.setTimeout(() => {
      api.search(query).then(setResults).catch(() => setResults(null));
    }, 250);
    return () => window.clearTimeout(debounceRef.current);
  }, [query]);

  const onSearchChange = (q: string) => {
    setQuery(q);
    setView(q.trim() ? { name: "search" } : { name: "library" });
  };

  const rescan = async () => {
    setRescanning(true);
    try {
      await api.rescan();
      // The scan now runs in the background; poll until it finishes.
      for (;;) {
        await new Promise((r) => window.setTimeout(r, 1000));
        let status;
        try {
          status = await api.rescanStatus();
        } catch {
          continue; // transient error — keep polling
        }
        if (status.status === "idle") {
          if (status.error) throw new Error(status.error);
          break;
        }
      }
      loadLibrary();
    } catch (e) {
      alert("Rescan failed: " + e);
    } finally {
      setRescanning(false);
    }
  };

  const createPlaylist = async () => {
    const name = window.prompt("New playlist name");
    if (!name || !name.trim()) return;
    try {
      const pl = await api.createPlaylist(name.trim());
      loadPlaylists();
      setView({ name: "playlist", id: pl.id });
    } catch (e) {
      alert("Could not create playlist: " + e);
    }
  };

  const deletePlaylist = async (pl: PlaylistSummary) => {
    if (!window.confirm(`Delete playlist “${pl.name}”?`)) return;
    try {
      await api.deletePlaylist(pl.id);
      loadPlaylists();
    } catch (e) {
      alert("Could not delete playlist: " + e);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => setView({ name: "library" })}>
          🎵 My Music
        </div>
        <input
          className="search-box"
          type="search"
          placeholder="Search tracks, albums, artists…"
          value={query}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <div className="topbar-right">
          <button
            className="nav-btn"
            onClick={() => setView({ name: "playlists" })}
          >
            ≣ Playlists
          </button>
          {stats && (
            <span className="stats">
              {stats.tracks} tracks · {stats.albums} albums
            </span>
          )}
          <button onClick={rescan} disabled={rescanning}>
            {rescanning ? "Scanning…" : "↻ Rescan"}
          </button>
        </div>
      </header>

      <main className="content">
        {view.name === "library" && (
          <Library albums={albums} onOpen={(id) => setView({ name: "album", id })} />
        )}
        {view.name === "album" && (
          <Album
            albumId={view.id}
            playlists={playlists}
            onPlaylistsChanged={loadPlaylists}
            onBack={() => setView({ name: "library" })}
          />
        )}
        {view.name === "search" && (
          <Search
            query={query}
            results={results}
            playlists={playlists}
            onPlaylistsChanged={loadPlaylists}
            onOpenAlbum={(id) => setView({ name: "album", id })}
          />
        )}
        {view.name === "playlists" && (
          <Playlists
            playlists={playlists}
            onOpen={(id) => setView({ name: "playlist", id })}
            onCreate={createPlaylist}
            onDelete={deletePlaylist}
          />
        )}
        {view.name === "playlist" && (
          <Playlist
            playlistId={view.id}
            playlists={playlists}
            onChanged={loadPlaylists}
            onBack={() => setView({ name: "playlists" })}
          />
        )}
      </main>

      <Player />
    </div>
  );
}
