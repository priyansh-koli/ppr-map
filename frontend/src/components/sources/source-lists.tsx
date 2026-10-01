import type { Sources } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

/** The link text for a source: its site's name, not a long download URL. */
export function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Sources the site shows data from, each with its licence and the credit it asks for. */
export function InUse({ sources }: { sources: Sources["inUse"] }) {
  return (
    <ul className="divide-y divide-line">
      {sources.map((s) => (
        <li key={s.key} className="space-y-1.5 py-4 first:pt-0 last:pb-0">
          <h3 className="font-medium text-ink">{s.name}</h3>
          {s.attribution ? <p className="text-ink-2">{s.attribution}</p> : null}
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
            <span>Licence: {s.licence}</span>
            {s.cadence ? <span>Refreshed: {s.cadence}</span> : null}
            {s.checkedOn ? <span>Licence checked {formatDate(s.checkedOn)}</span> : null}
            <a className="prose-link" href={s.url} rel="noreferrer">
              {host(s.url)}
            </a>
          </p>
        </li>
      ))}
    </ul>
  );
}

/** Allowed but not loaded yet: named so nobody mistakes them for data on the site. */
export function Planned({ sources }: { sources: Sources["planned"] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-6">
      {sources.map((s) => (
        <li key={s.key}>
          {s.name} <span className="text-muted">(licence: {s.licence})</span>
        </li>
      ))}
    </ul>
  );
}

export function NotUsed({ sources }: { sources: Sources["notUsed"] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-6">
      {sources.map((s) => (
        <li key={s.key}>
          <span className="font-medium text-ink">{s.name}</span>: {s.reason}
        </li>
      ))}
    </ul>
  );
}
