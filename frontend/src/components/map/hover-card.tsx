import Link from "next/link";

import { SaveButton } from "@/components/auth/save-button";
import { Window } from "@/components/ui/window";

import type { PropertySummary } from "@/lib/api/client";
import {
  CONFIDENCE_LABEL,
  CONFIDENCE_NOTE,
  formatDate,
  formatDistance,
  formatEur,
  tileDate,
} from "@/lib/format";

import type { SalePoint } from "./layers";

/** What the card shows: a property (fetched summary), several sales drawn on one spot, a
 * stack of approximate sales, or a zoomed-out group. `addresses` fill in once loaded. */
export type CardContent =
  | { kind: "property"; id: string; summary: PropertySummary | null; error?: string }
  | { kind: "spot"; sales: SalePoint[]; addresses: Record<string, string> | null }
  | { kind: "stack"; n: number; median: number; confidence: string }
  | { kind: "cell"; n: number; median: number };

function Flags({ sale }: { sale: NonNullable<PropertySummary["latestSale"]> }) {
  const flags = [
    sale.isNew ? "New build" : null,
    sale.flags.vatExclusive ? "Price excludes VAT" : null,
    sale.flags.notFullMarketPrice ? "Not full market price" : null,
    sale.flags.bulk ? "Part of a bulk sale" : null,
  ].filter(Boolean);
  if (!flags.length) return null;
  return <p className="mt-1 text-xs text-muted">{flags.join(" · ")}</p>;
}

function PropertyCard({
  id,
  summary,
  error,
}: {
  id: string;
  summary: PropertySummary | null;
  error?: string;
}) {
  if (error) return <p>{error}</p>;
  if (!summary) return <p aria-busy>Loading…</p>;
  const sale = summary.latestSale;
  const previous = summary.previousSales ?? [];
  const v = summary.vicinity;
  return (
    <div className="space-y-2">
      <p className="font-semibold leading-snug text-ink">{summary.address}</p>
      {sale ? (
        <div>
          <p className="font-display text-2xl font-bold tracking-tight text-ink">
            {formatEur(sale.priceEur)}
          </p>
          <p className="text-sm text-muted">Sold {formatDate(sale.date)}</p>
          <Flags sale={sale} />
        </div>
      ) : null}
      {previous.length ? (
        <p className="text-sm text-muted">
          Earlier:{" "}
          {previous
            .slice(0, 3)
            .map((s) => `${formatEur(s.priceEur)} (${s.date.slice(0, 4)})`)
            .join(", ")}
          {previous.length > 3 ? "…" : ""}
        </p>
      ) : null}
      <p className="text-xs text-muted">
        <span className="font-medium text-ink">{CONFIDENCE_LABEL[summary.confidence]}.</span>{" "}
        {CONFIDENCE_NOTE[summary.confidence]}
      </p>
      {v.nearestStop || v.nearestPrimarySchool || v.shopsWithin1km ? (
        <ul className="space-y-0.5 text-sm">
          {v.nearestStop ? (
            <li>
              Stop: {v.nearestStop.value.name} ({formatDistance(v.nearestStop.value.distanceM)})
            </li>
          ) : null}
          {v.nearestPrimarySchool ? (
            <li>
              Primary school: {v.nearestPrimarySchool.value.name ?? "unnamed"} (
              {formatDistance(v.nearestPrimarySchool.value.distanceM)})
            </li>
          ) : null}
          {v.shopsWithin1km ? <li>Shops within 1 km: {v.shopsWithin1km.value}</li> : null}
          <li className="text-xs text-muted">Straight-line distances.</li>
        </ul>
      ) : null}
      {summary.area?.median12m ? (
        <p className="text-sm">
          {summary.area.name}: median {formatEur(summary.area.median12m)} over 12 months
          {summary.area.provisional ? " (provisional)" : ""}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link className="text-sm font-medium text-accent underline" href={`/property/${id}`}>
          Full sale history and details
        </Link>
        <SaveButton propertyId={id} />
      </div>
    </div>
  );
}

/** Sales on one spot: a list to pick from once pinned, a count while hovering. */
function SpotCard({
  sales,
  addresses,
  onChoose,
}: {
  sales: SalePoint[];
  addresses: Record<string, string> | null;
  onChoose?: (sale: SalePoint) => void;
}) {
  if (!onChoose) {
    return (
      <div className="space-y-1">
        <p className="font-semibold">{sales.length} sales at this spot</p>
        <p className="text-xs text-muted">Click to choose one.</p>
      </div>
    );
  }
  return (
    <div>
      <p className="font-semibold">{sales.length} sales at this spot</p>
      <ul className="-mx-2 mt-1 max-h-64 divide-y divide-line overflow-y-auto">
        {sales.map((sale) => (
          <li key={sale.id}>
            <button
              type="button"
              onClick={() => onChoose(sale)}
              className="w-full rounded-[10px] px-2 py-1.5 text-left hover:bg-surface-2"
            >
              <span className="block font-medium text-ink">
                {addresses?.[sale.id] ?? (addresses ? "Address not listed" : "Loading address…")}
              </span>
              <span className="block text-muted">
                {formatEur(sale.price)} · {formatDate(tileDate(sale.date))}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const TITLE: Record<CardContent["kind"], string> = {
  property: "sale · details",
  spot: "sales · one spot",
  stack: "sales · grouped",
  cell: "sales · grouped",
};

export function HoverCard({
  content,
  onClose,
  onChoose,
}: {
  content: CardContent;
  onClose?: () => void;
  onChoose?: (sale: SalePoint) => void;
}) {
  return (
    <Window
      as="div"
      lift
      className="w-72 text-sm text-ink"
      bodyClassName="p-3.5"
      title={TITLE[content.kind]}
      meta={
        onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="-mr-1.5 grid h-6 w-6 place-items-center rounded-full text-base leading-none text-muted hover:bg-surface hover:text-ink"
            aria-label="Close details"
          >
            ×
          </button>
        ) : null
      }
    >
      {content.kind === "property" ? (
        <PropertyCard id={content.id} summary={content.summary} error={content.error} />
      ) : content.kind === "spot" ? (
        <SpotCard sales={content.sales} addresses={content.addresses} onChoose={onChoose} />
      ) : content.kind === "stack" ? (
        <div className="space-y-1">
          <p className="font-semibold">
            {content.n} {content.n === 1 ? "sale" : "sales"} at an approximate location
          </p>
          <p>Median {formatEur(content.median)}</p>
          <p className="text-xs text-muted">
            {CONFIDENCE_NOTE[content.confidence]} Each one is in the list of sales in view.
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          <p className="font-semibold">
            {content.n} {content.n === 1 ? "sale" : "sales"} here
          </p>
          <p>Median {formatEur(content.median)}</p>
          <p className="text-xs text-muted">Click to zoom in and see each sale.</p>
        </div>
      )}
    </Window>
  );
}
