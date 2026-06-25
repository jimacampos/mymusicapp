import { PlaylistSummary, SearchResults, api } from "../api";
import { TrackList } from "../components/TrackList";

interface Props {
  query: string;
  results: SearchResults | null;
  playlists: PlaylistSummary[];
  onPlaylistsChanged: () => void;
  onOpenAlbum: (id: number) => void;
}

export function Search({
  query,
  results,
  playlists,
  onPlaylistsChanged,
  onOpenAlbum,
}: Props) {
  if (!query.trim()) {
    return <div className="empty">Type to search your library.</div>;
  }
  if (!results) return <div className="empty">Searching…</div>;

  const empty =
    results.tracks.length === 0 &&
    results.albums.length === 0 &&
    results.artists.length === 0;
  if (empty) {
    return <div className="empty">No results for “{query}”.</div>;
  }

  return (
    <div className="search-results">
      {results.albums.length > 0 && (
        <section>
          <h2>Albums</h2>
          <div className="album-grid">
            {results.albums.map((a) => (
              <button
                key={a.id}
                className="album-card"
                onClick={() => onOpenAlbum(a.id)}
              >
                <div className="cover-wrap">
                  {a.has_cover ? (
                    <img src={api.coverUrl(a.id)} alt={a.title} loading="lazy" />
                  ) : (
                    <div className="cover placeholder">♪</div>
                  )}
                </div>
                <div className="album-title">{a.title}</div>
                <div className="album-artist">{a.artist}</div>
              </button>
            ))}
          </div>
        </section>
      )}

      {results.artists.length > 0 && (
        <section>
          <h2>Artists</h2>
          <ul className="artist-list">
            {results.artists.map((ar) => (
              <li key={ar.id}>{ar.name}</li>
            ))}
          </ul>
        </section>
      )}

      {results.tracks.length > 0 && (
        <section>
          <h2>Tracks</h2>
          <TrackList
            tracks={results.tracks}
            showAlbum
            playlists={playlists}
            onPlaylistsChanged={onPlaylistsChanged}
          />
        </section>
      )}
    </div>
  );
}
