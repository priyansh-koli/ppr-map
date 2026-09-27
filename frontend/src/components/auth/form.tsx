import {
  type InputHTMLAttributes,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { ApiError } from "@/lib/api/client";

export const inputClass = "mt-1 w-full rounded border border-line bg-surface px-3 py-2 text-ink";
export const buttonClass =
  "rounded-md bg-accent px-4 py-2 font-medium text-surface hover:opacity-90 disabled:opacity-60";

export function Field({
  label,
  hint,
  id,
  errorId,
  ...props
}: {
  label: string;
  hint?: ReactNode;
  /** The form message's id, when that message is about this field. */
  errorId?: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  const generated = useId();
  const inputId = id ?? generated;
  // The hint is described-by, not part of the label, so the field's name is just the label.
  const hintId = hint ? `${inputId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="block text-sm">
      <label htmlFor={inputId} className="font-medium text-ink">
        {label}
      </label>
      <input
        id={inputId}
        aria-describedby={describedBy}
        aria-invalid={errorId ? true : undefined}
        className={inputClass}
        {...props}
      />
      {hint ? (
        <p id={hintId} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A form's error or success line. The live region stays mounted and only its text changes, so
 * screen readers announce it; a region inserted with its text already in it is often missed.
 */
export function FormMessage({
  error,
  success,
  id,
}: {
  error?: string | null;
  success?: string | null;
  id?: string;
}) {
  return (
    <p
      id={id}
      role="status"
      aria-live={error ? "assertive" : "polite"}
      aria-atomic="true"
      className="rounded bg-surface-2 px-3 py-2 text-sm text-ink empty:sr-only"
    >
      {error || success || ""}
    </p>
  );
}

/** What replaces a form once it is done; focus moves to it so it is not lost with the form. */
export function FormDone({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div ref={ref} tabIndex={-1} className="space-y-3 focus:outline-none">
      {children}
    </div>
  );
}

/**
 * One submission at a time: `run` ignores calls while one is in flight, and `busy` disables
 * the button. The ref guards the gap before React re-renders the disabled button.
 */
export function useBusy() {
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (task: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await task();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, []);
  return { busy, run };
}

/** An API error's message, or a general one. */
export function messageOf(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "Something went wrong; please try again.";
}

/** The request field an API validation error is about, if it names one. */
export function fieldOf(e: unknown): string | null {
  return e instanceof ApiError ? e.field : null;
}

/** Backslashes and control characters, which browsers rewrite or drop in URLs. */
function unsafeInUrl(s: string): boolean {
  return [...s].some((c) => c === "\\" || c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f);
}

/** Only same-origin paths are followed after sign-in; anything else goes home. */
export function safeNext(next: string | null): string {
  // Browsers read a backslash as "/" and drop tabs and newlines, so "/\evil" and "/<tab>/evil"
  // would become "//evil", another site. Refuse them outright, then let the URL parser decide.
  if (!next || !next.startsWith("/") || unsafeInUrl(next)) return "/";
  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  try {
    const url = new URL(next, origin);
    return url.origin === origin ? url.pathname + url.search + url.hash : "/";
  } catch {
    return "/";
  }
}
