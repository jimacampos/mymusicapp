interface IconProps {
  size?: number;
}

function Svg({ size = 20, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function PlayIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M8 5v14l11-7z" />
    </Svg>
  );
}

export function PauseIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
    </Svg>
  );
}

export function PrevIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M7 6h2v12H7zM20 6l-9 6 9 6z" />
    </Svg>
  );
}

export function NextIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M15 6h2v12h-2zM4 6l9 6-9 6z" />
    </Svg>
  );
}

export function VolumeIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3a4.5 4.5 0 00-2.5-4.03v8.05A4.5 4.5 0 0016.5 12zM14 3.23v2.06a7 7 0 010 13.42v2.06a9 9 0 000-17.54z" />
    </Svg>
  );
}
