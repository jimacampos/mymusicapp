import { Track } from "../api";
import { usePlayer } from "../player";
import { formatTime } from "../format";

interface Props {
  tracks: Track[];
  showAlbum?: boolean;
}

export function TrackList({ tracks, showAlbum }: Props) {
  const p = usePlayer();

  return (
    <table className="tracklist">
      <thead>
        <tr>
          <th className="num">#</th>
          <th>Title</th>
          {showAlbum && <th>Album</th>}
          <th className="dur">Time</th>
        </tr>
      </thead>
      <tbody>
        {tracks.map((t, i) => {
          const isCurrent = p.current?.id === t.id;
          return (
            <tr
              key={t.id}
              className={isCurrent ? "current" : ""}
              onDoubleClick={() => p.playQueue(tracks, i)}
              onClick={() => p.playQueue(tracks, i)}
            >
              <td className="num">
                {isCurrent && p.isPlaying ? "♪" : t.track_no ?? i + 1}
              </td>
              <td>
                <div className="t-title">{t.title}</div>
                <div className="t-artist">{t.artist}</div>
              </td>
              {showAlbum && <td className="t-album">{t.album}</td>}
              <td className="dur">{formatTime(t.duration)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
