"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/auth/session";
import { api, type View } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { FormMessage, messageOf, useBusy } from "../auth/form";

export function History() {
  const { me } = useSession();
  const [views, setViews] = useState<View[] | null>(null);
  const [error, setError] = useState<string | null>(null);
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
  useEffect(() => {
    api
      .views()
      .then(setViews)
      .catch((e: unknown) => setError(messageOf(e)));
  }, []);
  if (error) return <FormMessage error={error} />;
  if (!views) return <p aria-busy>Loading…</p>;
  return (
    <div className="space-y-4">
      {me && !me.historyEnabled ? (
        <p className="text-sm">
          History is switched off, so nothing new is added.{" "}
          <Link className="text-accent underline" href={ROUTES.account.path}>
            Change this in your settings
          </Link>
          .
        </p>
      ) : (
        <p className="text-sm text-muted">
          Properties you opened in the last 12 months. Only you can see this.
        </p>
      )}
      <FormMessage error={actionError} />
      {views.length ? (
        <>
          <button
            type="button"
            className="text-sm text-accent underline disabled:opacity-60"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.clearViews();
                setViews([]);
              }, "Could not clear your history")
            }
          >
            Clear all
          </button>
          <ul className="divide-y divide-line">
            {views.map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-3 py-3">
                <span>
                  <Link
                    className="font-medium text-ink underline"
                    href={`/property/${v.propertyId}`}
                  >
                    {v.address}
                  </Link>
                  <span className="block text-xs text-muted">{formatDateTime(v.viewedAt)}</span>
                </span>
                <button
                  type="button"
                  className="text-sm text-accent underline disabled:opacity-60"
                  aria-label={`Remove ${v.address} from history`}
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      await api.deleteView(v.id);
                      setViews((xs) => xs?.filter((x) => x.id !== v.id) ?? null);
                    }, `Could not remove ${v.address}`)
                  }
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>Nothing here yet.</p>
      )}
    </div>
  );
}
