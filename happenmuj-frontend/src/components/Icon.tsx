import type { SVGProps } from 'react';

// One icon set, drawn on a 24px grid with a 1.75 stroke. Icons sit beside text and stay small.
const PATHS = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" /></>,
  moon: <path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" />,
  bookmark: <path d="M6 4h12v17l-6-4-6 4z" />,
  calendar: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 1.5" /></>,
  pin: <><path d="M12 21s6-5.5 6-11a6 6 0 10-12 0c0 5.5 6 11 6 11z" /><circle cx="12" cy="10" r="2" /></>,
  users: <><circle cx="9" cy="9" r="3" /><path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" /><circle cx="17" cy="10" r="2.2" /><path d="M17 14.2c2.4 0 4 1.5 4 3.8" /></>,
  tag: <><path d="M4 12V5h7l9 9-7 7z" /><circle cx="8" cy="9" r="1" /></>,
  left: <path d="M15 5l-7 7 7 7" />,
  right: <path d="M9 5l7 7-7 7" />,
  down: <path d="M6 9l6 6 6-6" />,
  up: <path d="M6 15l6-6 6 6" />,
  external: <path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" /></>,
  home: <><path d="M4 11l8-7 8 7v9H4z" /><path d="M10 20v-6h4v6" /></>,
  compass: <><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5z" /></>,
  message: <path d="M4 5h16v11H9l-5 4z" />,
  thumb: <path d="M7 11v9H4v-9zM7 11l4-7c1.6 0 2.6 1.1 2.3 2.6L12.6 10H19a1.5 1.5 0 011.5 1.8l-1.2 6A2 2 0 0117.300 19H7" />,
  bulb: <path d="M9 18h6M10 21h4M12 3a6 6 0 00-3.500 10.900c.6.5 1 1.200 1 2.100h5c0-.9.4-1.600 1-2.100A6 6 0 0012 3z" />,
  trash: <path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" />,
  edit: <path d="M4 20h4L19 9l-4-4L4 16z" />,
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.01" /></>,
  alert: <><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17v.01" /></>,
  logout: <path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9" />,
  shield: <path d="M12 3l8 3v6c0 5-3.500 8-8 9-4.500-1-8-4-8-9V6z" />,
  grid: <><rect x="4" y="4" width="7" height="7" rx="1" /><rect x="13" y="4" width="7" height="7" rx="1" /><rect x="4" y="13" width="7" height="7" rx="1" /><rect x="13" y="13" width="7" height="7" rx="1" /></>,
  list: <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 00-1-1H5a1 1 0 00-1 1v10a1 1 0 001 1h3" /></>,
} as const;

export type IconName = keyof typeof PATHS | 'bookmark-fill' | 'verified';

interface Props extends Omit<SVGProps<SVGSVGElement>, 'name'> { name: IconName; size?: number }

export function Icon({ name, size = 20, ...rest }: Props) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', 'aria-hidden': true, focusable: false } as const;
  if (name === 'verified') {
    return (
      <svg {...common} {...rest}>
        <circle cx="12" cy="12" r="10" fill="currentColor" />
        <path d="M7.800 12.300l2.800 2.800 5.600-5.800" fill="none" stroke="var(--verified-ink)" strokeWidth="2.200" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === 'bookmark-fill') {
    return (
      <svg {...common} {...rest}>
        <path d="M6 4h12v17l-6-4-6 4z" fill="currentColor" stroke="currentColor" strokeWidth="1.750" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.750" strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {PATHS[name]}
    </svg>
  );
}
