import { CONFIDENCE_LABEL, formatDate, formatEur } from "@/lib/format";

import type { ListState } from "./map-explorer";

/**
 * The list view synced with the map: the same sales, in text, reachable by keyboard.
 * Focusing or hovering an item highlights its marker; Enter opens its details.
 */
export function SalesList({
  state,
  onFocusItem,
  onOpenItem,
}: {
  state: ListState;
  onFocusItem: (id: string | null) => void;
  onOpenItem: (id: string) => void;
}) {
  return (
    <section aria-labelledby="list-heading" className="text-sm">
      <h2 id="list-heading" className="font-semibold text-ink">
        Sales in view
      </h2>
      <div aria-live="polite" className="mt-1 text-muted">
        {state.status === "zoom" && "Zoom in to a town or neighbourhood to list its sales."}
        {state.status === "loading" && "Loading…"}
        {state.status === "error" && state.message}
        {state.status === "ok" &&
          (state.data.total === 0
            ? "No sales match these filters here."
            : state.data.total > state.data.items.length
              ? `The ${state.data.items.length} most recent of ${state.data.total.toLocaleString("en-IE")}. Zoom in or filter to narrow.`
              : `${state.data.total.toLocaleString("en-IE")} ${state.data.total === 1 ? "sale" : "sales"}.`)}
      </div>
      {state.status === "ok" && state.data.items.length ? (
        <ul className="mt-2 divide-y divide-line" onMouseLeave={() => onFocusItem(null)}>
          {state.data.items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="w-full py-2 text-left hover:bg-surface-2"
                onMouseEnter={() => onFocusItem(item.id)}
                onFocus={() => onFocusItem(item.id)}
                onBlur={() => onFocusItem(null)}
                onClick={() => onOpenItem(item.id)}
              >
                <span className="block font-medium text-ink">{item.address}</span>
                <span className="block text-ink">
                  {formatEur(item.latestSale.priceEur)} · {formatDate(item.latestSale.date)}
                  {item.latestSale.isNew ? " · new" : ""}
                </span>
                <span className="block text-xs text-muted">
                  {CONFIDENCE_LABEL[item.confidence]}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
