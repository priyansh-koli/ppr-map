import Link from "next/link";

import { Window } from "@/components/ui/window";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16 text-center sm:py-24">
      <p className="font-mono text-sm text-muted">404</p>
      <h1 className="mt-2 font-display text-5xl font-semibold tracking-[-0.015em] text-ink">
        Not on the <span className="hl">register.</span>
      </h1>
      <Window title="lookup · no match" className="mt-8 text-left" bodyClassName="p-6">
        <p className="text-ink-2">
          This page does not exist, or the property was withdrawn from the site.
        </p>
        <p className="mt-5 flex flex-wrap gap-3">
          <Link className="btn btn-primary btn-sm" href="/map">
            Open the map
          </Link>
          <Link className="btn btn-secondary btn-sm" href="/">
            Back to the home page
          </Link>
        </p>
      </Window>
    </div>
  );
}
