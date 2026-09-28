/** The mark: a map pin whose head is a gabled house. Decorative; the name sits beside it. */
export function BrandMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <path
        d="M16 30c-.5 0-1-.3-1.3-.7C11.4 24.8 5 17.3 5 12.2 5 6 9.9 2 16 2s11 4 11 10.2c0 5.1-6.4 12.6-9.7 17.1-.3.4-.8.7-1.3.7Z"
        className="fill-accent"
      />
      <path d="M10.5 13.2 16 8.4l5.5 4.8V19h-11v-5.8Z" className="fill-[var(--color-on-accent)]" />
      <rect x="14.2" y="14.6" width="3.6" height="4.4" rx=".6" className="fill-accent" />
    </svg>
  );
}
