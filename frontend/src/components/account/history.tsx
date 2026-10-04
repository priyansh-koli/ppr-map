"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/auth/session";
import { api, type SearchHistoryItem, type View } from "@/lib/api/client";
import { describeSearch } from "@/lib/describe";
import { formatDateTime } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { FormMessage, messageOf, useBusy } from "../auth/form";

interface PageOf<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** A list read a page at a time, newest first, with "Show more" for the next page. */
export function usePaged<T extends { id: number }>(load: (page: number) => Promise<PageOf<T>>) {
  const [items, setItems] = useState<T[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(1);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    load(1)
      .then((p) => {
        setItems(p.items);
        setTotal(p.total);
        setPageSize(Math.max(p.pageSize, 1));
      })
      .catch((e: unknown) => setError(messageOf(e)));
  }, [load]);
  const more = async () => {
    // The page holding the first entry not shown yet, counted from what is shown rather than
    // from the pages read: a Remove moves every later entry up by one, so "page + 1" skipped
    // one, and "Show more" then never went away (P1 #30). The overlap is dropped.
    const next = await load(Math.floor((items?.length ?? 0) / pageSize) + 1);
    setTotal(next.total);
    setItems((xs) => [...(xs ?? []), ...next.items.filter((n) => !xs?.some((x) => x.id === n.id))]);
  };
  const remove = (id: number) => {
    setItems((xs) => xs?.filter((x) => x.id !== id) ?? null);
    setTotal((t) => t - 1);
  };
  const clear = () => {
    setItems([]);
    setTotal(0);
  };
  return { items, total, error, more, remove, clear };
}

function Section<T extends { id: number }>({
  heading,
  intro,
  list,
  empty,
  clearAll,
  label,
  render,
  removeOne,
}: {
  heading: string;
  intro: string;
  list: ReturnType<typeof usePaged<T>>;
  empty: string;
  clearAll: () => Promise<void>;
  label: (item: T) => string;
  render: (item: T) => React.ReactNode;
  removeOne: (item: T) => Promise<void>;
}) {
  const [actionError, setActionError] = useState<string | null>(null);
  const { busy, run } = useBusy();
  // One change at a time: a Remove racing Clear all would leave the list out of step.
  const act = (task: () => Promise<void>, failure: string) =>
    run(async () => {
      setActionError(null);
      try {
        await task();
      } catch (e) {
        setActionError(`${failure}: ${messageOf(e)}`);
      }
    });
  const { items } = list;
  return (
    <section aria-labelledby={`${heading}-heading`} className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={`${heading}-heading`} className="font-display text-2xl text-ink">
          {heading}
        </h2>
        {items?.length ? (
          <button
            type="button"
            className="text-sm text-accent underline disabled:opacity-60"
            disabled={busy}
            aria-label={`Clear all ${heading.toLowerCase()}`}
            onClick={() =>
              act(async () => {
                await clearAll();
                list.clear();
              }, `Could not clear your ${heading.toLowerCase()}`)
            }
          >
            Clear all
          </button>
        ) : null}
      </div>
      <p className="text-sm text-muted">{intro}</p>
      <FormMessage error={list.error ?? actionError} />
      {!items && !list.error ? <p aria-busy>Loading…</p> : null}
      {items && items.length === 0 ? <p>{empty}</p> : null}
      {items?.length ? (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 py-3">
              <span className="min-w-0">{render(item)}</span>
              <button
                type="button"
                className="shrink-0 text-sm text-accent underline disabled:opacity-60"
                aria-label={`Remove ${label(item)} from history`}
                disabled={busy}
                onClick={() =>
                  act(
                    async () => {
                      await removeOne(item);
                      list.remove(item.id);
                    },
                    `Could not remove ${label(item)}`,
                  )
                }
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {items && items.length < list.total ? (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy}
          onClick={() => act(list.more, "Could not load more")}
        >
          Show more ({(list.total - items.length).toLocaleString("en-IE")} older)
        </button>
      ) : null}
    </section>
  );
}

export function searchHref(query: Record<string, string>): string {
  const params = new URLSearchParams(query);
  // "Near my location" was not stored; the search opens without the point.
  if (params.get("near") === "my-location") {
    params.delete("near");
    params.delete("radiusM");
  }
  const qs = params.toString();
  return `${ROUTES.search.path}${qs ? `?${qs}` : ""}`;
}

export function History() {
  const { me } = useSession();
  const views = usePaged<View>(useCallback((page: number) => api.views(page), []));
  const searches = usePaged<SearchHistoryItem>(
    useCallback((page: number) => api.searches(page), []),
  );
  return (
    <div className="space-y-10">
      {me && !me.historyEnabled ? (
        <p className="text-sm">
          History is switched off, so nothing new is added.{" "}
          <Link className="text-accent underline" href={ROUTES.account.path}>
            Change this in your settings
          </Link>
          .
        </p>
      ) : null}
      <Section<View>
        heading="Viewed properties"
        intro="Properties you opened in the last 12 months. Only you can see this."
        list={views}
        empty="Nothing here yet."
        clearAll={api.clearViews}
        label={(v) => v.address}
        removeOne={(v) => api.deleteView(v.id)}
        render={(v) => (
          <>
            <Link className="font-medium text-ink underline" href={`/property/${v.propertyId}`}>
              {v.address}
            </Link>
            <span className="block text-xs text-muted">{formatDateTime(v.viewedAt)}</span>
          </>
        )}
      />
      <Section<SearchHistoryItem>
        heading="Past searches"
        intro="Searches you ran in the last 12 months. A search near your location is kept without the location."
        list={searches}
        empty="No searches yet."
        clearAll={api.clearSearches}
        label={(s) => s.label ?? describeSearch(s.query)}
        removeOne={(s) => api.deleteSearch(s.id)}
        render={(s) => (
          <>
            <Link className="font-medium text-ink underline" href={searchHref(s.query)}>
              {s.label ?? describeSearch(s.query)}
            </Link>
            <span className="block text-xs text-muted">
              {s.label ? `${describeSearch(s.query)} · ` : ""}
              {formatDateTime(s.searchedAt)}
            </span>
          </>
        )}
      />
    </div>
  );
}
