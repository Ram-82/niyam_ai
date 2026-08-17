import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Base({ size = 20, children, strokeWidth = 1.5, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const LayoutDashboardIcon = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Base>
);

export const CalendarCheckIcon = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="4" width="18" height="17" rx="2" />
    <path d="M16 2v4M8 2v4M3 10h18" />
    <path d="m9 16 2 2 4-4" />
  </Base>
);

export const UsersIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
  </Base>
);

export const FileTextIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M8 13h8M8 17h5" />
  </Base>
);

export const FolderOpenIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 20a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2z" />
  </Base>
);

export const SparklesIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="m18.5 15.5.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" />
  </Base>
);

export const BarChart3Icon = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 20h18" />
    <path d="M6 20v-6M11 20V8M16 20v-9M21 20V5" />
  </Base>
);

export const SettingsIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 7h9M19 7h1M4 17h5M15 17h5" />
    <circle cx="16" cy="7" r="2.5" />
    <circle cx="12" cy="17" r="2.5" />
  </Base>
);

export const ChevronsUpDownIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="m8 9 4-4 4 4M8 15l4 4 4-4" />
  </Base>
);

export const SearchIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.6-3.6" />
  </Base>
);

export const BellIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 9a6 6 0 1 1 12 0c0 4.5 1.8 5.6 1.8 5.6H4.2S6 13.5 6 9" />
    <path d="M10.4 19a2 2 0 0 0 3.2 0" />
  </Base>
);

export const SunIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Base>
);

export const MoonIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
  </Base>
);

export const ArrowUpIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Base>
);

export const ClockIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5.2l3 1.8" />
  </Base>
);

export const CalendarIcon = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="4" width="18" height="17" rx="2" />
    <path d="M16 2v4M8 2v4M3 10h18" />
  </Base>
);

export const PlusIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 1.75}>
    <path d="M12 5v14M5 12h14" />
  </Base>
);

export const ChevronLeftIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="m15 18-6-6 6-6" />
  </Base>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="m9 18 6-6-6-6" />
  </Base>
);

export const ChevronDownIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="m6 9 6 6 6-6" />
  </Base>
);

export const ArrowUpDownIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="M8 5v14M5 8l3-3 3 3M16 19V5M13 16l3 3 3-3" />
  </Base>
);

export const FilterIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 5h18l-7 8v6l-4 2v-8z" />
  </Base>
);

export const DownloadIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3v12" />
    <path d="m7.5 11 4.5 4.5 4.5-4.5" />
    <path d="M4 20h16" />
  </Base>
);

export const MoreHorizontalIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...rest}>
    <circle cx="5" cy="12" r="1.6" />
    <circle cx="12" cy="12" r="1.6" />
    <circle cx="19" cy="12" r="1.6" />
  </svg>
);

export const CheckCircleIcon = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12.5 2.4 2.4 4.6-5.2" />
  </Base>
);

export const UploadIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 16V4" />
    <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
    <path d="M4 16v3a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-3" />
  </Base>
);

export const AlertTriangleIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M10.3 4 2.6 17.5A1.6 1.6 0 0 0 4 20h16a1.6 1.6 0 0 0 1.4-2.5L13.7 4a1.6 1.6 0 0 0-2.8 0" />
    <path d="M12 9.5v4M12 17h.01" />
  </Base>
);

export const MessageSquareIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M21 14.5a2 2 0 0 1-2 2H8l-4 3.5V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
  </Base>
);

export const PackageOpenIcon = (p: IconProps) => (
  <Base {...p}>
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.5 5h13l3.5 7v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z" />
  </Base>
);

export const XIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 2}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Base>
);

export const ArrowUpRightIcon = (p: IconProps) => (
  <Base {...p} strokeWidth={p.strokeWidth ?? 1.75}>
    <path d="M7 17 17 7M8 7h9v9" />
  </Base>
);
