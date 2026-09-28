import type { ReactNode } from "react";

/**
 * A record window (D-043): a white card with a title bar in the mono face. The bar's label says
 * what is inside (`register · 49 South Circular Road`), and `meta` holds a chip on the right,
 * such as how precisely a sale was placed. `lift` gives the floating hero cards more depth.
 */
export function Window({
  title,
  meta,
  children,
  className = "",
  bodyClassName = "p-5",
  lift = false,
  as: Tag = "section",
  labelledBy,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  lift?: boolean;
  as?: "section" | "div" | "article" | "aside";
  labelledBy?: string;
}) {
  return (
    <Tag
      className={`window ${lift ? "shadow-lift" : ""} ${className}`}
      aria-labelledby={labelledBy}
    >
      <div className="window-bar">
        <WindowGlyph />
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {meta}
      </div>
      <div className={bodyClassName}>{children}</div>
    </Tag>
  );
}

/** A small map pin: every window here holds something from the register or the map. */
function WindowGlyph() {
  return (
    <svg viewBox="0 0 12 14" aria-hidden="true" className="h-3.5 w-3 shrink-0 text-accent">
      <path
        d="M6 13.2C3.9 10.5 1.2 7.6 1.2 5a4.8 4.8 0 0 1 9.6 0c0 2.6-2.7 5.5-4.8 8.2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <circle cx="6" cy="5" r="1.6" fill="currentColor" />
    </svg>
  );
}
