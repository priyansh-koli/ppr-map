"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type WishlistItem } from "@/lib/api/client";
import { formatDate, formatEur } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { FormMessage, inputClass, messageOf, useBusy } from "../auth/form";

const MAX_COMPARE = 4;

function Note({ item }: { item: WishlistItem }) {
  const [note, setNote] = useState(item.note ?? "");
  const [saved, setSaved] = useState(item.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const { busy, run } = useBusy();
  const errorId = `note-${item.id}-error`;
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          setError(null);
          try {
            const next = await api.noteWishlistItem(item.id, note.trim() || null);
            setSaved(next.note ?? "");
          } catch (err) {
            setError(`Could not save the note: ${messageOf(err)}`);
          }
        });
      }}
    >
      <div className="flex gap-2">
        <label className="sr-only" htmlFor={`note-${item.id}`}>
          Note for {item.title}
        </label>
        <input
          id={`note-${item.id}`}
          className={`${inputClass} mt-0 text-sm`}
          value={note}
          maxLength={2000}
          placeholder="Add a note"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => setNote(e.target.value)}
        />
        {note !== saved ? (
          <button className="text-sm text-accent underline disabled:opacity-60" disabled={busy}>
            {busy ? "Saving…" : "Save note"}
          </button>
        ) : null}
      </div>
      <FormMessage id={errorId} error={error} />
    </form>
  );
}

export function Wishlist() {
  const [items, setItems] = useState<WishlistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [removing, setRemoving] = useState<number[]>([]);
  const [removeError, setRemoveError] = useState<string | null>(null);
  useEffect(() => {
    api
      .wishlist()
      .then(setItems)
      .catch((e: unknown) => setError(messageOf(e)));
  }, []);
  if (error) return <FormMessage error={error} />;
  if (!items) return <p aria-busy>Loading…</p>;
  if (!items.length) {
    return (
      <p>
        Nothing saved yet. Use <span className="font-medium">Save to wishlist</span> on a property
        from the{" "}
        <Link className="text-accent underline" href={ROUTES.map.path}>
          map
        </Link>
        .
      </p>
    );
  }
  const toggle = (id: string) =>
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : s.length < MAX_COMPARE ? [...s, id] : s,
    );
  const remove = async (item: WishlistItem) => {
    if (removing.includes(item.id)) return;
    setRemoving((r) => [...r, item.id]);
    setRemoveError(null);
    try {
      await api.removeWishlistItem(item.id);
      setItems((xs) => xs?.filter((x) => x.id !== item.id) ?? null);
      setSelected((s) => s.filter((x) => x !== item.propertyId));
    } catch (e) {
      setRemoveError(`Could not remove ${item.title}: ${messageOf(e)}`);
    } finally {
      setRemoving((r) => r.filter((x) => x !== item.id));
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Tick up to {MAX_COMPARE} properties to compare them side by side.
      </p>
      <FormMessage error={removeError} />
      {selected.length >= 2 ? (
        <Link className="btn btn-primary" href={`${ROUTES.compare.path}?ids=${selected.join(",")}`}>
          Compare {selected.length}
        </Link>
      ) : null}
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <li key={item.id} className="py-4">
            <div className="flex items-start gap-3">
              {item.propertyId ? (
                <input
                  type="checkbox"
                  className="mt-1.5"
                  aria-label={`Compare ${item.title}`}
                  checked={selected.includes(item.propertyId)}
                  disabled={!selected.includes(item.propertyId) && selected.length >= MAX_COMPARE}
                  onChange={() => item.propertyId && toggle(item.propertyId)}
                />
              ) : null}
              <div className="flex-1">
                <Link
                  className="font-medium text-ink underline"
                  href={item.propertyId ? `/property/${item.propertyId}` : `/area/${item.areaSlug}`}
                >
                  {item.title}
                </Link>
                <p className="text-sm text-muted">
                  {item.latestPriceEur && item.latestSaleDate
                    ? `${formatEur(item.latestPriceEur)} · sold ${formatDate(item.latestSaleDate)}`
                    : item.kind === "area"
                      ? "Area"
                      : ""}
                </p>
                <Note item={item} />
              </div>
              <button
                type="button"
                className="text-sm text-accent underline disabled:opacity-60"
                aria-label={`Remove ${item.title}`}
                disabled={removing.includes(item.id)}
                onClick={() => void remove(item)}
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
