import Link from "next/link";

import { pageMetadata } from "@/components/placeholder-page";
import { InUse, NotUsed, Planned } from "@/components/sources/source-lists";
import { ConfidenceChip } from "@/components/ui/confidence-chip";
import { PageHeader } from "@/components/ui/page-header";
import { api, type Sources, STATIC_PREVIEW } from "@/lib/api/client";
import { PSRA_DISCLAIMER } from "@/lib/attribution";
import { CONFIDENCE_NOTE } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("sources");

const h2 = "mt-12 font-display text-2xl font-bold text-ink first:mt-0";
const LEVELS = ["exact", "street", "locality", "routing_key", "county", "unmatched"];

/** The list lives in config/sources.yaml and comes through the API (D-055). */
async function load(): Promise<Sources | null> {
  if (STATIC_PREVIEW) return null;
  try {
    return await api.sources({ cache: "no-store" });
  } catch {
    return null;
  }
}

export default async function Page() {
  const sources = await load();
  const unavailable = (
    <p className="text-muted">
      {STATIC_PREVIEW
        ? "This preview has no server behind it, so the list of sources is not shown here."
        : "The list of sources could not be loaded right now. Please try again shortly."}
    </p>
  );
  return (
    <article className="mx-auto max-w-3xl px-4 py-12">
      <PageHeader
        eyebrow="methodology"
        title={ROUTES.sources.title}
        lead={ROUTES.sources.summary}
      />
      <div className="window mt-8 space-y-4 p-6 leading-relaxed text-ink-2 sm:p-10">
        <h2 className={h2}>The register</h2>
        <p>
          Every sale here comes from the Residential Property Price Register, published by the
          Property Services Regulatory Authority (PSRA). For each sale since 2010 it gives the date
          of sale, the price, the address as the filer typed it, the county, whether the home was
          new or second-hand, whether the price was below full market value, and whether a new
          home&rsquo;s price excludes VAT. Since 2021 most sales also carry an Eircode.
        </p>
        <p>{PSRA_DISCLAIMER}</p>

        <h2 className={h2}>How locations are estimated</h2>
        <p>
          The register has no coordinates. We place each address with our own copy of the
          OpenStreetMap geocoder, official townland and town names, and the named estates in the
          Department of Housing&rsquo;s housing surveys. A match must sit in the right county and
          near the right town, or it is rejected. Every sale says how precisely it was placed:
        </p>
        <dl className="space-y-3">
          {LEVELS.map((level) => (
            <div key={level} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <dt>
                <ConfidenceChip confidence={level} />
              </dt>
              <dd>{CONFIDENCE_NOTE[level]}</dd>
            </div>
          ))}
        </dl>
        <p>
          Exact matches are rare outside Dublin, because OpenStreetMap has few house numbers there.
          Looking up each Eircode would place most recent sales exactly, but that needs a paid
          licence we do not have. By default the map shows sales placed to a town, village or
          townland or better; the filters can show the rest. Distances to stops and schools are
          straight lines, and only exact and street locations get them, because a distance from a
          town centre would be invented.
        </p>
        <p>
          Found a home in the wrong place?{" "}
          <Link className="prose-link" href={ROUTES.report.path}>
            Report it
          </Link>
          . A location corrected by hand stays corrected through later updates.
        </p>

        <h2 className={h2}>How prices are counted</h2>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <span className="font-medium">Market sales by default.</span> Sales filed as below full
            market price, and portfolio sales where one price is repeated across many homes, are
            left out of the map, statistics and estimates. The filters let you include them.
          </li>
          <li>
            <span className="font-medium">New homes are filed without VAT.</span> Any price with VAT
            added is labelled as an estimate.
          </li>
          <li>
            <span className="font-medium">Medians, not averages,</span> so a few very large sales do
            not swing the figure. A group of fewer than five sales shows its count but no price.
          </li>
          <li>
            <span className="font-medium">The latest two months are provisional.</span> Sales reach
            the register weeks after the sale, so recent months fill in later. The date shown is the
            date of sale, not the date it was filed.
          </li>
        </ul>

        <h2 className={h2}>The price estimate</h2>
        <p>
          A property page may show what the CSO&rsquo;s Residential Property Price Index implies the
          home is worth today: its last market sale, moved by the index for its region and for
          houses or apartments. The range comes from how homes that sold twice actually moved
          against the index. There is no estimate for a home placed less precisely than its street,
          with no market sale, or sold too recently for the index to add anything. It is
          information, not a valuation.
        </p>

        <h2 className={h2}>What the data cannot tell you</h2>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            The register has no bedrooms, floor area, photos or condition, and does not say whether
            a home is a house or an apartment. We never fill these in from elsewhere.
          </li>
          <li>
            Addresses, counties and Eircodes are as filed, and some are wrong. Where the address is
            vague, the location is too, and the map says so.
          </li>
          <li>
            We never show who bought or sold a home, and never combine the register with anything
            that could identify owners or occupants.
          </li>
          <li>
            Flood maps are not shown: their licence does not allow it. Property pages link to{" "}
            <a className="prose-link" href="https://www.floodinfo.ie" rel="noreferrer">
              floodinfo.ie
            </a>{" "}
            instead.
          </li>
        </ul>

        <h2 className={h2}>Sources in use</h2>
        {sources ? <InUse sources={sources.inUse} /> : unavailable}

        <h2 className={h2}>The map</h2>
        <p>
          The background map is a{" "}
          <a className="prose-link" href="https://protomaps.com" rel="noreferrer">
            Protomaps
          </a>{" "}
          basemap of OpenStreetMap data, © OpenStreetMap contributors (ODbL), served from our own
          server. Hill shading and the 3D view use{" "}
          <a className="prose-link" href="https://mapterhorn.com/attribution" rel="noreferrer">
            Mapterhorn
          </a>{" "}
          elevation tiles: Copernicus DEM © DLR e.V. 2010–2014, © Airbus Defence and Space GmbH
          2014–2018 (EU, ESA).
        </p>

        {sources && sources.planned.length > 0 ? (
          <>
            <h2 className={h2}>Planned</h2>
            <p>
              Approved for later, but nothing from these is on the site yet. Some licences are still
              being confirmed.
            </p>
            <Planned sources={sources.planned} />
          </>
        ) : null}

        {sources && sources.notUsed.length > 0 ? (
          <>
            <h2 className={h2}>Sources we do not use</h2>
            <NotUsed sources={sources.notUsed} />
          </>
        ) : null}
      </div>
    </article>
  );
}
