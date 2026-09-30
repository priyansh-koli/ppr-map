"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/auth/session";
import { searchHref } from "@/components/account/history";
import { type AlertFrequency, api, type SavedSearch } from "@/lib/api/client";
import { describeSearch } from "@/lib/describe";
import { formatDateTime } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { FormMessage, messageOf, useBusy } from "../auth/form";

export const FREQUENCIES: [AlertFrequency, string][] = [
  ["off", "No emails"],
  ["on_data_update", "Email me when the register is updated"],
  ["weekly", "Email me a weekly digest"],
];

function Row({
  item,
  onChange,
  onRemove,
  busy,
  act,
}: {
  item: SavedSearch;
  onChange: (next: SavedSearch) => void;
  onRemove: () => void;
  busy: boolean;
  act: (task: () => Promise<void>, failure: string) => void;
}) {
  const [name, setName] = useState(item.name);
  return (
    <li className="space-y-3 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link className="font-medium text-ink underline" href={searchHref(item.query)}>
            {item.name}
          </Link>
          <p className="text-xs text-muted">{describeSearch(item.query)}</p>
          <p className="text-xs text-muted">
            Saved {formatDateTime(item.createdAt)}
            {item.lastAlertedAt
              ? ` · last alert ${formatDateTime(item.lastAlertedAt)} (${item.lastAlertMatches ?? 0} new)`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn btn-secondary btn-sm" href={api.savedSearchCsvUrl(item.id)} download>
            Download CSV
          </a>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            aria-label={`Delete ${item.name}`}
            onClick={() =>
              act(async () => {
                await api.deleteSavedSearch(item.id);
                onRemove();
              }, `Could not delete ${item.name}`)
            }
          >
            Delete
          </button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act(
              async () => onChange(await api.updateSavedSearch(item.id, { name })),
              "Could not rename it",
            );
          }}
        >
          <label className="flex-1 text-sm">
            <span className="text-muted">Name</span>
            <input
              className="mt-0.5 w-full px-2.5 py-1.5"
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="btn btn-secondary btn-sm"
            disabled={busy || name.trim() === item.name || !name.trim()}
          >
            Rename
          </button>
        </form>
        <label className="text-sm">
          <span className="text-muted">Alert</span>
          <select
            className="mt-0.5 w-full px-2.5 py-1.5"
            value={item.alertFrequency}
            disabled={busy}
            onChange={(e) => {
              const alertFrequency = e.target.value as AlertFrequency;
              act(
                async () => onChange(await api.updateSavedSearch(item.id, { alertFrequency })),
                "Could not change the alert",
              );
            }}
          >
            {FREQUENCIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </li>
  );
}

export function SavedSearches() {
  const { me } = useSession();
  const [items, setItems] = useState<SavedSearch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { busy, run } = useBusy();
  const act = (task: () => Promise<void>, failure: string) =>
    run(async () => {
      setActionError(null);
      try {
        await task();
      } catch (e) {
        setActionError(`${failure}: ${messageOf(e)}`);
      }
    });
  useEffect(() => {
    api
      .savedSearches()
      .then(setItems)
      .catch((e: unknown) => setError(messageOf(e)));
  }, []);
  if (error) return <FormMessage error={error} />;
  if (!items) return <p aria-busy>Loading…</p>;
  const alerting = items.some((i) => i.alertFrequency !== "off");
  return (
    <div className="space-y-4">
      {me && !me.emailVerified && alerting ? (
        <p role="status" className="rounded-[10px] bg-accent-wash px-4 py-3 text-sm text-ink">
          Alerts are not sent until you confirm your email address. Check your inbox, or ask for a
          new link in your{" "}
          <Link className="underline" href={ROUTES.account.path}>
            account settings
          </Link>
          .
        </p>
      ) : null}
      <p className="text-sm text-muted">
        An alert lists sales newly filed on the register that match the search. The register is
        updated about once a month, and sales are filed weeks after they close, so a new sale may be
        months old. Each download holds up to 500 sales, and you can download 10 a day.
      </p>
      <FormMessage error={actionError} />
      {items.length ? (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <Row
              key={item.id}
              item={item}
              busy={busy}
              act={act}
              onChange={(next) =>
                setItems((xs) => xs?.map((x) => (x.id === next.id ? next : x)) ?? null)
              }
              onRemove={() => setItems((xs) => xs?.filter((x) => x.id !== item.id) ?? null)}
            />
          ))}
        </ul>
      ) : (
        <p>
          No saved searches yet.{" "}
          <Link className="text-accent underline" href={ROUTES.search.path}>
            Search the register
          </Link>{" "}
          and choose &ldquo;Save this search&rdquo;.
        </p>
      )}
    </div>
  );
}
