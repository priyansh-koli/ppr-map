import Link from "next/link";

import { ConfidenceChip } from "@/components/ui/confidence-chip";
import type { Comparables } from "@/lib/api/client";
import { formatDate, formatDistance, formatEur } from "@/lib/format";

/** Two homes placed at the same street point have no distance between them that means much. */
function distance(metres: number): string {
  return metres === 0 ? "same map point" : formatDistance(metres);
}

/**
 * Market sales of other homes on the same street or estate, then the nearest (D-053). Only
 * homes placed at their house or street take part, so every distance is between two real
 * points on the map.
 */
export function ComparableSales({
  comparables: c,
  searchHref,
}: {
  comparables: Comparables;
  searchHref: string;
}) {
  if (!c.available) {
    return <p className="mt-2 text-sm text-muted">{c.reason}</p>;
  }
  const radius = formatDistance(c.radiusM);
  if (c.total === 0) {
    return (
      <p className="mt-2 text-sm text-muted">
        No market sales of homes placed within {radius} in the last {c.months} months of the
        register.
      </p>
    );
  }
  return (
    <>
      <p className="mt-2 text-sm text-ink-2">
        {c.total.toLocaleString("en-IE")} market {c.total === 1 ? "sale" : "sales"} within {radius}{" "}
        in the last {c.months} months of the register
        {c.medianEur != null ? (
          <>
            , median <strong className="font-semibold text-ink">{formatEur(c.medianEur)}</strong>
            {c.medianN < c.total ? ` of the ${c.medianN} filed with VAT` : null}
          </>
        ) : null}
        . Same street or estate first, then the nearest.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <caption className="sr-only">Comparable sales near this property</caption>
          <thead>
            <tr className="text-muted">
              <th scope="col" className="py-2 pr-4 font-medium">
                Address
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Sold
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Price
              </th>
              <th scope="col" className="py-2 text-right font-medium">
                Distance
              </th>
            </tr>
          </thead>
          <tbody>
            {c.items.map((s) => (
              <tr key={s.id} className="border-t border-line align-top">
                <td className="py-2.5 pr-4">
                  <Link
                    className="text-ink underline decoration-line underline-offset-2"
                    href={`/property/${s.id}`}
                  >
                    {s.address}
                  </Link>
                  <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <ConfidenceChip confidence={s.confidence} />
                    {s.sameStreet ? <span>same street or place</span> : null}
                    {s.isNew ? <span>new build</span> : null}
                  </span>
                </td>
                <td className="py-2.5 pr-4 whitespace-nowrap">{formatDate(s.date)}</td>
                <td className="py-2.5 pr-4 text-right font-semibold whitespace-nowrap text-ink">
                  {formatEur(s.priceEur)}
                  {s.vatExclusive ? (
                    <span className="block text-xs font-normal text-muted">excludes VAT</span>
                  ) : null}
                </td>
                <td className="py-2.5 text-right whitespace-nowrap text-ink-2">
                  {distance(s.distanceM)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted">
        Straight-line distances. The register does not record size or bedrooms, so these are sales
        nearby, not like-for-like homes. The median leaves out prices filed without VAT, and needs
        at least 5 sales.{" "}
        {c.total > c.items.length ? (
          <Link className="text-accent underline" href={searchHref}>
            All sales within {radius}
          </Link>
        ) : null}
      </p>
    </>
  );
}
