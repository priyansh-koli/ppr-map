import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AreaTrends, PriceDistribution } from "@/components/area/area-charts";
import { AreaOutline } from "@/components/area/area-outline";
import { SaveButton } from "@/components/auth/save-button";
import { pageMetadata, StaticPreviewPage } from "@/components/placeholder-page";
import { Window } from "@/components/ui/window";
import { type AreaDetail, api, ApiError, STATIC_PREVIEW } from "@/lib/api/client";
import { formatDate, formatEur, formatMonth } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

type Props = { params: Promise<{ slug: string }> };

// The static export (D-034) needs every path at build time. It pre-renders the sample URL
// from `routes.ts` and says it needs the data server; the server build renders any slug.
export function generateStaticParams() {
  return [{ slug: "dublin" }];
}

const KIND_LABEL: Record<string, string> = {
  country: "Country",
  county: "County",
  settlement: "Town or city",
  electoral_division: "Electoral Division",
  small_area: "Small Area",
  townland: "Townland",
};
const CHILD_LABEL: Record<string, string> = {
  county: "Counties",
  settlement: "Towns and cities",
  small_area: "Small Areas",
};

async function load(slug: string): Promise<AreaDetail | "unavailable" | null> {
  try {
    return await api.area(slug, { cache: "no-store" });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    return "unavailable";
  }
}

function areaTitle(a: Pick<AreaDetail, "kind" | "name">): string {
  return a.kind === "small_area" ? `Small Area ${a.name}` : a.name;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  if (STATIC_PREVIEW) return pageMetadata("area");
  const data = await load((await params).slug);
  return data && data !== "unavailable"
    ? {
        title: `${areaTitle(data)}: property prices`,
        description: `Median sale price, sales and price distribution for ${areaTitle(data)}, from the Property Price Register.`,
      }
    : pageMetadata("area");
}

function signedPct(pct: number): string {
  return `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct).toLocaleString("en-IE")}%`;
}

function change(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "no comparison";
  return `${signedPct(pct)} on the year before`;
}

/** The map explorer framed on the area, with only its sales. */
function mapHref(a: AreaDetail): string {
  const [w = -8, s = 53, e = -6, n = 54] = a.bbox;
  const span = Math.max(e - w, (n - s) * 1.6, 0.005);
  const q = new URLSearchParams();
  if (a.kind === "county") q.set("county", a.slug);
  else if (a.kind !== "country") q.set("area", a.slug);
  q.set("lat", ((s + n) / 2).toFixed(5));
  q.set("lng", ((w + e) / 2).toFixed(5));
  q.set("z", Math.min(16, Math.max(6, Math.log2(360 / span) - 0.3)).toFixed(2));
  return `${ROUTES.map.path}?${q.toString()}`;
}

function searchHref(a: AreaDetail): string {
  if (a.kind === "country") return ROUTES.search.path;
  return `${ROUTES.search.path}?${a.kind === "county" ? "county" : "area"}=${a.slug}`;
}

export default async function Page({ params }: Props) {
  const { slug } = await params;
  if (STATIC_PREVIEW) return <StaticPreviewPage routeKey="area" detail={`Area: ${slug}`} />;
  const data = await load(slug);
  if (data === null) notFound();
  if (data === "unavailable") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <h1 className="font-display text-4xl text-ink">{ROUTES.area.title}</h1>
        <p className="mt-4 text-muted">
          This area could not be loaded right now. Please try again shortly.
        </p>
      </div>
    );
  }
  const h = data.headline;
  const nat = data.national;
  const title = areaTitle(data);
  return (
    <article className="mx-auto max-w-5xl space-y-6 px-4 py-12">
      <header className="grid gap-6 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <nav aria-label="Area" className="eyebrow">
            {[...data.parents].reverse().map((p) => (
              <span key={p.slug}>
                <Link className="hover:underline" href={`/area/${p.slug}`}>
                  {areaTitle(p)}
                </Link>{" "}
                ·{" "}
              </span>
            ))}
            {KIND_LABEL[data.kind] ?? data.kind}
          </nav>
          <h1 className="mt-2 font-display text-4xl font-semibold leading-[1.02] tracking-[-0.015em] text-ink sm:text-5xl">
            {title}
          </h1>
          {data.nameGa && data.nameGa !== data.name ? (
            <p className="mt-1 text-lg italic text-ink-2" lang="ga">
              {data.nameGa}
            </p>
          ) : null}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Link className="btn btn-primary btn-sm" href={mapHref(data)}>
              Sales on the map
            </Link>
            <Link className="btn btn-secondary btn-sm" href={searchHref(data)}>
              Search sales here
            </Link>
            {data.kind !== "country" ? <SaveButton areaSlug={data.slug} /> : null}
          </div>
        </div>
        <AreaOutline geometry={data.geometry} bbox={data.bbox} label={title} />
      </header>

      <Window
        title={`area · latest complete ${h && data.periodKinds.includes("rolling_12m") ? "12 months" : "year"}`}
        bodyClassName="p-5 sm:p-7"
      >
        {h && h.median !== null && h.median !== undefined ? (
          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <p className="text-sm font-medium text-ink-2">
                Median sale price, {formatMonth(h.windowStart)} to {formatMonth(h.windowEnd)}
              </p>
              <p className="text-5xl font-semibold tracking-[-0.02em] text-ink tabular-nums">
                {formatEur(h.median)}
              </p>
              <p className="mt-1 text-sm text-muted">
                {h.n.toLocaleString("en-IE")} market sales · {change(h.changePct)}
                {h.p25 != null && h.p75 != null
                  ? ` · the middle half sold for ${formatEur(h.p25)} to ${formatEur(h.p75)}`
                  : ""}
              </p>
            </div>
            {nat && nat.median != null ? (
              <div className="rounded-[10px] bg-surface-2 p-4">
                <p className="text-sm text-muted">Ireland, same months</p>
                <p className="text-2xl font-semibold text-ink tabular-nums">
                  {formatEur(nat.median)}
                </p>
                <p className="text-sm text-muted">
                  {change(nat.changePct)}. {title} is{" "}
                  <strong className="font-semibold text-ink">
                    {Math.abs(Math.round((h.median / nat.median - 1) * 100))}%{" "}
                    {h.median >= nat.median ? "above" : "below"}
                  </strong>{" "}
                  the national median.
                </p>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted">
            {h ? `${h.n} market ${h.n === 1 ? "sale" : "sales"}` : "No market sales"} in the latest
            complete period: prices are not shown for fewer than 5 sales.
          </p>
        )}
        {data.priceIndex ? (
          <p className="mt-4 rounded-[10px] bg-surface-2 px-4 py-3 text-sm text-ink-2">
            <span className="font-medium text-ink">CSO price index</span>, {data.priceIndex.label}:{" "}
            <strong className="font-semibold text-ink">
              {signedPct(data.priceIndex.change12mPct)}
            </strong>{" "}
            in the 12 months to {formatMonth(data.priceIndex.month)}
            {h?.changePct != null ? `, against ${signedPct(h.changePct)} for the median here` : ""}.
            The index allows for the mix of homes sold; a median does not, so the two can differ
            when different homes happen to sell.
            <span className="mt-1 block font-mono text-[0.7rem] text-muted">
              {data.priceIndex.source}
            </span>
          </p>
        ) : null}
        <p className="mt-4 text-xs text-muted">
          Market sales only: not those filed as below full market price, bulk or portfolio sales, or
          possible repeat filings. The latest two months are provisional and left out here.
          {data.pointBased
            ? " Only sales placed at their house or street can be counted in a Small Area or Electoral Division, so these figures leave out sales located less precisely."
            : ""}
          {data.kind === "townland" || data.kind === "settlement"
            ? " A sale counts here when its address was placed in this area."
            : ""}
        </p>
      </Window>

      {data.attributes.length ? (
        <Window title="area · with sources" bodyClassName="p-5 sm:p-7">
          <h2 className="font-display text-2xl text-ink">What else is known</h2>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            {data.attributes.map((a) => (
              <div key={a.label} className="rounded-[10px] bg-surface-2 px-4 py-3">
                <dt className="text-muted">{a.label}</dt>
                <dd className="mt-0.5 font-medium text-ink">
                  {a.value}
                  <span className="mt-1 block font-mono text-[0.7rem] font-normal text-muted">
                    {a.source}, {formatDate(a.asOf)}, {a.licence}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        </Window>
      ) : null}

      <Window title="area · prices over time" labelledBy="trend-heading" bodyClassName="p-5 sm:p-7">
        <h2 id="trend-heading" className="font-display text-2xl text-ink">
          Prices and sales over time
        </h2>
        <div className="mt-4">
          <AreaTrends slug={data.slug} name={title} periodKinds={data.periodKinds} />
        </div>
      </Window>

      <Window
        title="area · price distribution"
        labelledBy="dist-heading"
        bodyClassName="p-5 sm:p-7"
      >
        <h2 id="dist-heading" className="font-display text-2xl text-ink">
          What homes sold for
        </h2>
        <div className="mt-4">
          <PriceDistribution slug={data.slug} name={title} />
        </div>
      </Window>

      {data.children.length && data.childrenKind ? (
        <Window
          title={`area · ${(CHILD_LABEL[data.childrenKind] ?? "areas").toLowerCase()}`}
          bodyClassName="p-5 sm:p-7"
        >
          <h2 className="font-display text-2xl text-ink">
            {CHILD_LABEL[data.childrenKind] ?? "Areas"} in {title}
          </h2>
          <p className="mt-1 text-sm text-muted">
            The busiest, by market sales in the same period.
          </p>
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th scope="col" className="py-1.5 font-medium">
                  {KIND_LABEL[data.childrenKind] ?? "Area"}
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Sales
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Median
                </th>
              </tr>
            </thead>
            <tbody>
              {data.children.map((c) => (
                <tr key={c.slug} className="border-t border-line">
                  <td className="py-1.5">
                    <Link
                      className="text-ink underline decoration-line underline-offset-2 hover:decoration-ink"
                      href={`/area/${c.slug}`}
                    >
                      {areaTitle(c)}
                    </Link>
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{c.n.toLocaleString("en-IE")}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    {c.median != null ? formatEur(c.median) : "fewer than 5"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Window>
      ) : null}

      <p className="font-mono text-xs text-muted">
        Boundary: {data.source} · data version {data.dataVersion}
      </p>
    </article>
  );
}
