"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { api, type PropertySummary } from "@/lib/api/client";
import { CONFIDENCE_LABEL, formatDate, formatDistance, formatEur } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { FormMessage, messageOf } from "../auth/form";

const ROWS: { label: string; value: (s: PropertySummary) => ReactNode }[] = [
  { label: "Latest sale", value: (s) => (s.latestSale ? formatEur(s.latestSale.priceEur) : "–") },
  { label: "Sold", value: (s) => (s.latestSale ? formatDate(s.latestSale.date) : "–") },
  {
    label: "Type",
    value: (s) => (s.latestSale ? (s.latestSale.isNew ? "New build" : "Second-hand") : "–"),
  },
  { label: "Earlier sales", value: (s) => String(s.previousSales?.length ?? 0) },
  { label: "Location", value: (s) => CONFIDENCE_LABEL[s.confidence] },
  {
    label: "Nearest stop",
    value: (s) =>
      s.vicinity.nearestStop
        ? `${s.vicinity.nearestStop.value.name ?? "Stop"}, ${formatDistance(s.vicinity.nearestStop.value.distanceM)}`
        : "–",
  },
  {
    label: "Nearest primary school",
    value: (s) =>
      s.vicinity.nearestPrimarySchool
        ? formatDistance(s.vicinity.nearestPrimarySchool.value.distanceM)
        : "–",
  },
  {
    label: "Shops within 1 km",
    value: (s) => (s.vicinity.shopsWithin1km ? s.vicinity.shopsWithin1km.value : "–"),
  },
  { label: "Area deprivation", value: (s) => s.vicinity.deprivation?.value ?? "–" },
  {
    label: "Area median, 12 months",
    value: (s) => (s.area?.median12m ? `${formatEur(s.area.median12m)} (${s.area.name})` : "–"),
  },
];

export function Compare() {
  const ids = (useSearchParams().get("ids") ?? "").split(",").filter(Boolean).join(",");
  // Each answer remembers which ids it is for, so a change of ids shows nothing stale.
  const [result, setResult] = useState<{
    ids: string;
    items?: PropertySummary[];
    failed?: string;
  } | null>(null);
  useEffect(() => {
    if (!ids) return;
    const request = new AbortController();
    api
      .compare(ids.split(","), { signal: request.signal })
      .then((items) => {
        if (!request.signal.aborted) setResult({ ids, items });
      })
      .catch((e: unknown) => {
        if (!request.signal.aborted) setResult({ ids, failed: messageOf(e) });
      });
    return () => request.abort();
  }, [ids]);
  const current = result?.ids === ids ? result : null;
  const items = current?.items ?? null;
  const error = ids ? (current?.failed ?? null) : "Choose properties to compare on your wishlist.";
  if (error) {
    return (
      <div className="space-y-3">
        <FormMessage error={error} />
        <Link className="text-accent underline" href={ROUTES.wishlist.path}>
          Back to your wishlist
        </Link>
      </div>
    );
  }
  if (!items) return <p aria-busy>Loading…</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-left text-sm">
        <caption className="sr-only">Saved properties side by side</caption>
        <thead>
          <tr>
            <th className="w-44 py-2" />
            {items.map((s) => (
              <th key={s.id} scope="col" className="py-2 pr-4 align-top font-semibold text-ink">
                <Link className="underline" href={`/property/${s.id}`}>
                  {s.address}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <th scope="row" className="py-2 pr-4 font-medium text-muted">
                {row.label}
              </th>
              {items.map((s) => (
                <td key={s.id} className="py-2 pr-4">
                  {row.value(s)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-muted">Distances are straight lines.</p>
    </div>
  );
}
