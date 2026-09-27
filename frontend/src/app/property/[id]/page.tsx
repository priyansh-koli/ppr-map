import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { RecordView } from "@/components/auth/record-view";
import { SaveButton } from "@/components/auth/save-button";
import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";
import { AreaTrend } from "@/components/property/area-trend";
import { api, ApiError, type PropertyDetail, STATIC_PREVIEW } from "@/lib/api/client";
import {
  CONFIDENCE_LABEL,
  CONFIDENCE_NOTE,
  formatDate,
  formatDistance,
  formatEur,
} from "@/lib/format";
import { ROUTES } from "@/lib/routes";

type Props = { params: Promise<{ id: string }> };

// The static export (D-034) needs every path at build time; it only has the sample URL from
// `routes.ts` and shows the placeholder. The server build renders any id on request.
export function generateStaticParams() {
  return [{ id: "example" }];
}

async function load(id: string): Promise<PropertyDetail | "unavailable" | null> {
  try {
    return await api.property(id, { cache: "no-store" });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  if (STATIC_PREVIEW) return pageMetadata("property");
  const data = await load((await params).id);
  return data && data !== "unavailable"
    ? { title: data.address, description: `Sale history for ${data.address}.` }
    : pageMetadata("property");
}

const KIND_LABEL: Record<string, string> = {
  small_area: "Small Area",
  electoral_division: "Electoral Division",
  townland: "Townland",
  settlement: "Town or city",
  county: "County",
};

function SaleFlags({ sale }: { sale: PropertyDetail["sales"][number] }) {
  const flags = [
    sale.isNew ? "New build" : "Second-hand",
    sale.vatExclusive ? "price excludes VAT" : null,
    sale.notFullMarketPrice ? "not full market price" : null,
    sale.bulkGroupSize ? `bulk sale of ${sale.bulkGroupSize}` : null,
    sale.possibleDuplicate ? "possible repeat filing" : null,
  ].filter(Boolean);
  return <>{flags.join(", ")}</>;
}

function Sourced({
  label,
  value,
  source,
  asOf,
}: {
  label: string;
  value: string;
  source: string;
  asOf?: string | null;
}) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="text-ink">
        {value}
        <span className="block text-xs text-muted">
          {source}
          {asOf ? `, ${asOf}` : ""}
        </span>
      </dd>
    </div>
  );
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  if (STATIC_PREVIEW) return <PlaceholderPage routeKey="property" detail={`ID: ${id}`} />;
  const data = await load(id);
  if (data === null) notFound();
  if (data === "unavailable") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">{ROUTES.property.title}</h1>
        <p className="mt-4 text-muted">
          This property could not be loaded right now. Please try again shortly.
        </p>
      </div>
    );
  }
  const v = data.vicinity;
  const loc = data.location;
  return (
    <article className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header className="space-y-2">
        <p className="text-sm text-muted">
          {ROUTES.property.title} · County{" "}
          {data.county.charAt(0).toUpperCase() + data.county.slice(1)}
          {data.routingKey ? ` · Eircode area ${data.routingKey}` : ""}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">{data.address}</h1>
        <RecordView propertyId={data.id} />
        <SaveButton propertyId={data.id} />
        <p className="text-sm">
          <span className="font-medium text-ink">
            Location: {CONFIDENCE_LABEL[loc.confidence]}.
          </span>{" "}
          <span className="text-muted">{CONFIDENCE_NOTE[loc.confidence]}</span>{" "}
          <Link
            className="text-accent underline"
            href={`${ROUTES.map.path}?lat=${loc.lat.toFixed(5)}&lng=${loc.lng.toFixed(5)}&z=${loc.confidence === "exact" || loc.confidence === "street" ? 17 : 14}`}
          >
            Show on the map
          </Link>
        </p>
      </header>

      <section aria-labelledby="sales-heading">
        <h2 id="sales-heading" className="text-xl font-semibold text-ink">
          Sales
        </h2>
        <table className="mt-3 w-full text-left text-sm">
          <caption className="sr-only">Every sale of this property on the register</caption>
          <thead>
            <tr className="text-muted">
              <th className="py-2 font-medium">Date</th>
              <th className="py-2 font-medium">Price</th>
              <th className="py-2 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {/* Repeat filings share a date and price, so the row's position is part of its key. */}
            {data.sales.map((sale, i) => (
              <tr
                key={`${i}-${sale.date}-${sale.priceEur}`}
                className="border-t border-line align-top"
              >
                <td className="py-2">{formatDate(sale.date)}</td>
                <td className="py-2 font-medium text-ink">{formatEur(sale.priceEur)}</td>
                <td className="py-2 text-muted">
                  <SaleFlags sale={sale} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {data.caveats.length ? (
        <section aria-labelledby="caveats-heading" className="rounded-lg bg-surface-2 p-4 text-sm">
          <h2 id="caveats-heading" className="font-semibold text-ink">
            Worth knowing
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {data.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="vicinity-heading">
        <h2 id="vicinity-heading" className="text-xl font-semibold text-ink">
          Nearby
        </h2>
        {v.nearestStop || v.nearestPrimarySchool || v.shopsWithin1km || v.deprivation ? (
          <>
            <dl className="mt-3 grid gap-4 text-sm sm:grid-cols-2">
              {v.nearestStop ? (
                <Sourced
                  label="Nearest public transport stop"
                  value={`${v.nearestStop.value.name ?? "Unnamed stop"}, ${formatDistance(v.nearestStop.value.distanceM)}`}
                  source={v.nearestStop.source}
                  asOf={v.nearestStop.asOf}
                />
              ) : null}
              {v.nearestPrimarySchool ? (
                <Sourced
                  label="Nearest primary school"
                  value={`${v.nearestPrimarySchool.value.name ?? "Unnamed school"}, ${formatDistance(v.nearestPrimarySchool.value.distanceM)}`}
                  source={v.nearestPrimarySchool.source}
                  asOf={v.nearestPrimarySchool.asOf}
                />
              ) : null}
              {v.nearestPostPrimarySchool ? (
                <Sourced
                  label="Nearest post-primary school"
                  value={`${v.nearestPostPrimarySchool.value.name ?? "Unnamed school"}, ${formatDistance(v.nearestPostPrimarySchool.value.distanceM)}`}
                  source={v.nearestPostPrimarySchool.source}
                  asOf={v.nearestPostPrimarySchool.asOf}
                />
              ) : null}
              {v.shopsWithin1km ? (
                <Sourced
                  label="Shops within 1 km"
                  value={String(v.shopsWithin1km.value)}
                  source={v.shopsWithin1km.source}
                  asOf={v.shopsWithin1km.asOf}
                />
              ) : null}
              {v.deprivation ? (
                <Sourced
                  label="Area deprivation index"
                  value={v.deprivation.value}
                  source={v.deprivation.source}
                  asOf={v.deprivation.asOf}
                />
              ) : null}
            </dl>
            <p className="mt-3 text-xs text-muted">
              Distances are straight lines, not walking routes. Schools come from OpenStreetMap and
              may be incomplete.
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            Nearby places are only shown when the address itself or its street was found.
          </p>
        )}
        <p className="mt-3 text-sm">
          Flood risk:{" "}
          <a className="text-accent underline" href={v.flood.link}>
            {v.flood.note}
          </a>
          .
        </p>
      </section>

      {data.areaSeries ? (
        <section aria-labelledby="trend-heading">
          <h2 id="trend-heading" className="text-xl font-semibold text-ink">
            Prices in {data.areaSeries.area.name}
          </h2>
          <div className="mt-3">
            <AreaTrend series={data.areaSeries} />
          </div>
        </section>
      ) : null}

      <section aria-labelledby="areas-heading" className="text-sm">
        <h2 id="areas-heading" className="text-xl font-semibold text-ink">
          Areas
        </h2>
        <ul className="mt-2 space-y-1">
          {data.areas.map((a) => (
            <li key={`${a.kind}-${a.slug}`}>
              <span className="text-muted">{KIND_LABEL[a.kind] ?? a.kind}:</span> {a.name}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">Data version {data.dataVersion}.</p>
      </section>
    </article>
  );
}
