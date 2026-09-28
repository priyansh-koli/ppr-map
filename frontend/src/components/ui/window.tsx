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

/** Three survey marks where a desktop window has its buttons: ours are not buttons. */
function WindowGlyph() {
  return (
    <span aria-hidden="true" className="flex shrink-0 items-center gap-1">
      <span className="h-2 w-2 rounded-[2px] bg-accent" />
      <span className="h-2 w-2 rounded-[2px] bg-marker" />
      <span className="h-2 w-2 rounded-[2px] bg-line-strong" />
    </span>
  );
}
