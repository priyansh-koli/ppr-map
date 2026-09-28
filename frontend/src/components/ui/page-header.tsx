import type { ReactNode } from "react";

import { Window } from "./window";

/** The top of an inner page: a mono eyebrow, a display heading, an optional lead. */
export function PageHeader({
  eyebrow,
  title,
  lead,
  center = false,
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  center?: boolean;
}) {
  return (
    <header className={center ? "text-center" : undefined}>
      {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
      <h1 className="mt-2 font-display text-4xl font-extrabold tracking-[-0.03em] text-ink sm:text-5xl">
        {title}
      </h1>
      {lead ? (
        <p className={`mt-3 max-w-2xl text-lg text-ink-2 ${center ? "mx-auto" : ""}`}>{lead}</p>
      ) : null}
    </header>
  );
}

/** Sign-in, registration and the email-link pages: a heading, then the form in a window. */
export function AuthShell({
  title,
  lead,
  windowTitle,
  footnote,
  children,
  wide = false,
}: {
  title: string;
  lead?: ReactNode;
  windowTitle: string;
  footnote?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`mx-auto px-4 py-12 sm:py-16 ${wide ? "max-w-2xl" : "max-w-lg"}`}>
      <PageHeader title={title} lead={lead} center />
      <Window title={windowTitle} className="mt-8" bodyClassName="p-6 sm:p-8">
        {children}
      </Window>
      {footnote ? (
        <p className="mt-5 text-center font-mono text-xs text-muted">{footnote}</p>
      ) : null}
    </div>
  );
}
