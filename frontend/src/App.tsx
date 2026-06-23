import { useCallback, useEffect, useRef, useState } from "react";
import { AlbumSummary, SearchResults, Stats, api } from "./api";
import { Library } from "./views/Library";
import { Album } from "./views/Album";
import { Search } from "./views/Search";
import { Player } from "./components/Player";

type View = { name: "library" } | { name: "album"; id: number } | { name: "search" };

export default function App() {
  const [albums, setAlbums] = useState<AlbumSummary[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [view, setView] = useState<View>({ name: "library" });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [rescanning, setRescanning] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);

  const loadLibrary = useCallback(() => {
    api.albums().then(setAlbums).catch(() => undefined);
    api.stats().then(setStats).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadLibrary();
  }, [loadLibrary]);

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
      loadLibrary();
    } catch (e) {
      alert("Rescan failed: " + e);
    } finally {
      setRescanning(false);
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
          <Album albumId={view.id} onBack={() => setView({ name: "library" })} />
        )}
        {view.name === "search" && (
          <Search
            query={query}
            results={results}
            onOpenAlbum={(id) => setView({ name: "album", id })}
          />
        )}
      </main>

      <Player />
    </div>
  );
}
