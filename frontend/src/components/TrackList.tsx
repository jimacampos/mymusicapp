import { useState } from "react";
import { PlaylistSummary, Track } from "../api";
import { usePlayer } from "../player";
import { formatTime } from "../format";
import { AddToPlaylistMenu } from "./AddToPlaylistMenu";

interface Props {
  tracks: Track[];
  showAlbum?: boolean;
  playlists?: PlaylistSummary[];
  onPlaylistsChanged?: () => void;
  onRemove?: (track: Track) => void;
  onMove?: (index: number, dir: -1 | 1) => void;
}

export function TrackList({
  tracks,
  showAlbum,
  playlists,
  onPlaylistsChanged,
  onRemove,
  onMove,
}: Props) {
  const p = usePlayer();
  const [menuTrackId, setMenuTrackId] = useState<number | null>(null);
  const hasActions = !!playlists || !!onRemove || !!onMove;

  return (
    <table className="tracklist">
      <thead>
        <tr>
          <th className="num">#</th>
          <th>Title</th>
          {showAlbum && <th>Album</th>}
          <th className="dur">Time</th>
          {hasActions && <th className="actions" />}
        </tr>
      </thead>
      <tbody>
        {tracks.map((t, i) => {
          const isCurrent = p.current?.id === t.id;
          return (
            <tr key={t.id} className={isCurrent ? "current" : ""}>
              <td className="num" onClick={() => p.playQueue(tracks, i)}>
                {isCurrent && p.isPlaying ? "♪" : t.track_no ?? i + 1}
              </td>
              <td onClick={() => p.playQueue(tracks, i)}>
                <div className="t-title">{t.title}</div>
                <div className="t-artist">{t.artist}</div>
              </td>
              {showAlbum && (
                <td className="t-album" onClick={() => p.playQueue(tracks, i)}>
                  {t.album}
                </td>
              )}
              <td className="dur" onClick={() => p.playQueue(tracks, i)}>
                {formatTime(t.duration)}
              </td>
              {hasActions && (
                <td className="actions">
                  <div className="row-actions">
                    {onMove && (
                      <>
                        <button
                          className="icon-btn"
                          title="Move up"
                          disabled={i === 0}
                          onClick={() => onMove(i, -1)}
                        >
                          ↑
                        </button>
                        <button
                          className="icon-btn"
                          title="Move down"
                          disabled={i === tracks.length - 1}
                          onClick={() => onMove(i, 1)}
                        >
                          ↓
                        </button>
                      </>
                    )}
                    {onRemove && (
                      <button
                        className="icon-btn"
                        title="Remove from playlist"
                        onClick={() => onRemove(t)}
                      >
                        ✕
                      </button>
                    )}
                    {playlists && (
                      <div className="ctx-wrap">
                        <button
                          className="icon-btn"
                          title="Add to playlist"
                          aria-haspopup="menu"
                          onClick={() =>
                            setMenuTrackId(menuTrackId === t.id ? null : t.id)
                          }
                        >
                          ⋯
                        </button>
                        {menuTrackId === t.id && (
                          <AddToPlaylistMenu
                            track={t}
                            playlists={playlists}
                            onClose={() => setMenuTrackId(null)}
                            onChanged={() => onPlaylistsChanged?.()}
                          />
                        )}
                      </div>
                    )}
                  </div>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
