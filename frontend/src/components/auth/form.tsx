import { type InputHTMLAttributes, type ReactNode, useId } from "react";

export const inputClass = "mt-1 w-full rounded border border-line bg-surface px-3 py-2 text-ink";
export const buttonClass =
  "rounded-md bg-accent px-4 py-2 font-medium text-surface hover:opacity-90 disabled:opacity-60";

export function Field({
  label,
  hint,
  id,
  ...props
}: { label: string; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const generated = useId();
  const inputId = id ?? generated;
  // The hint is described-by, not part of the label, so the field's name is just the label.
  const hintId = hint ? `${inputId}-hint` : undefined;
  return (
    <div className="block text-sm">
      <label htmlFor={inputId} className="font-medium text-ink">
        {label}
      </label>
      <input id={inputId} aria-describedby={hintId} className={inputClass} {...props} />
      {hint ? (
        <p id={hintId} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FormMessage({
  error,
  success,
}: {
  error?: string | null;
  success?: string | null;
}) {
  if (error) {
    return (
      <p role="alert" className="rounded bg-surface-2 px-3 py-2 text-sm text-ink">
        {error}
      </p>
    );
  }
  if (success) {
    return (
      <p role="status" className="rounded bg-surface-2 px-3 py-2 text-sm text-ink">
        {success}
      </p>
    );
  }
  return null;
}

/** An API error's message, or a general one. */
export function messageOf(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "Something went wrong; please try again.";
}

/** Only same-site paths are followed after sign-in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
