import { PRICE_BANDS, SUPPRESSED_COLOR } from "@/lib/price-bands";

export function Legend({ showHexes }: { showHexes: boolean }) {
  return (
    <section aria-labelledby="legend-heading" className="space-y-3 text-sm">
      <h2
        id="legend-heading"
        className="font-mono text-xs font-semibold uppercase tracking-[0.08em] text-muted"
      >
        Key
      </h2>
      <div>
        <p className="text-muted">
          {showHexes ? "Median price, last 12 months" : "Price of the latest sale"}
        </p>
        <ul className="mt-1 space-y-1">
          {PRICE_BANDS.map((band) => (
            <li key={band.label} className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-3 w-5 rounded-sm"
                style={{ background: band.color }}
              />
              {band.label}
            </li>
          ))}
          {showHexes ? (
            <li className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-3 w-5 rounded-sm opacity-60"
                style={{ background: SUPPRESSED_COLOR }}
              />
              Fewer than 5 sales: no median shown
            </li>
          ) : null}
        </ul>
      </div>
      {showHexes ? null : (
        <ul className="space-y-1">
          <li className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-full bg-[#1c5cab] ring-2 ring-white"
            />
            A sale at its address or street (zoom in to see them)
          </li>
          <li className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-full border-[3px] border-[#1c5cab] bg-white"
            />
            Sales placed only at a town, townland or Eircode area, with their count
          </li>
          <li className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-full bg-[#2a78d6] opacity-70"
            />
            Zoomed out: sales grouped, sized by count
          </li>
        </ul>
      )}
    </section>
  );
}
