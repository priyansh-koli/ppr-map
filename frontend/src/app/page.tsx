import Link from "next/link";

import { Counties } from "@/components/home/counties";
import { Hero } from "@/components/home/hero";
import { MonthlyChart } from "@/components/home/monthly-chart";
import { pageMetadata } from "@/components/placeholder-page";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("home");

const STEPS = [
  {
    title: "The register lists the sale",
    text: "A price, a date and an address as it was typed in. No coordinates, no bedrooms, no photos. We keep the raw text next to everything we derive from it.",
  },
  {
    title: "We place the address, and say how sure we are",
    text: "At the house, on the street, or only in the town or townland. The map draws each kind differently, so a guess never looks like a fact.",
  },
  {
    title: "We add what is nearby, with its source",
    text: "Stops, schools, shops and the area's price trend, each with where it came from and when. Nothing on the way to your screen asks a third party.",
  },
];

const PRECISION = [
  {
    mark: <span className="h-3.5 w-3.5 rounded-full bg-[#1c5cab] ring-2 ring-surface" />,
    label: "Exact address",
    text: "Matched to the house number.",
  },
  {
    mark: <span className="h-3.5 w-3.5 rounded-full bg-[#1c5cab] ring-2 ring-surface" />,
    label: "Street or estate",
    text: "Drawn like an exact sale; the page says it is the street.",
  },
  {
    mark: <span className="h-3.5 w-3.5 rounded-full border-[3px] border-[#1c5cab] bg-surface" />,
    label: "Town, townland or Eircode area",
    text: "Stacked at its centre, with a count.",
  },
];

const NEVER = [
  "Bedrooms",
  "Floor area",
  "Photos",
  "Asking prices",
  "Owners' names",
  "Invented locations",
];

export default function Page() {
  return (
    <>
      <Hero />

      <section
        aria-labelledby="how-heading"
        className="mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 lg:grid-cols-2"
      >
        <div>
          <h2
            id="how-heading"
            className="font-display text-4xl font-semibold tracking-[-0.015em] text-ink sm:text-5xl"
          >
            A price, a date, an address. We do the rest.
          </h2>
          <ol className="mt-8 space-y-6 border-t border-line pt-6">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ink font-mono text-sm font-semibold text-desk"
                >
                  {i + 1}
                </span>
                <div>
                  <h3 className="text-lg font-semibold text-ink">{step.title}</h3>
                  <p className="mt-1 text-ink-2">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <Window title="map · how precisely each sale is placed" lift>
          <ul className="divide-y divide-line">
            {PRECISION.map((p) => (
              <li key={p.label} className="flex items-center gap-4 py-4 first:pt-1 last:pb-1">
                <span
                  aria-hidden="true"
                  className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-[#e8e4da]"
                >
                  {p.mark}
                </span>
                <div>
                  <p className="font-semibold text-ink">{p.label}</p>
                  <p className="text-sm text-muted">{p.text}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-4 rounded-[10px] bg-accent-wash px-4 py-3 text-sm text-ink">
            Every property page repeats this, in words, next to the sale.
          </p>
        </Window>
      </section>

      <section aria-labelledby="activity-heading" className="mx-auto max-w-5xl px-4 py-12">
        <h2 id="activity-heading" className="sr-only">
          Sales per month
        </h2>
        <MonthlyChart />
      </section>

      <Counties />

      <section aria-labelledby="never-heading" className="mx-auto max-w-7xl px-4 py-16">
        <div className="grid items-center gap-10 rounded-[20px] bg-band px-6 py-12 text-on-band outline outline-1 -outline-offset-1 outline-line sm:px-12 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <h2
              id="never-heading"
              className="font-display text-4xl font-semibold tracking-[-0.015em] sm:text-5xl"
            >
              What you will not find here.
            </h2>
            <p className="mt-4 max-w-lg text-lg opacity-80">
              The register does not record them, so we do not guess them. Where the data stops, the
              page says so.
            </p>
            <Link href={ROUTES.sources.path} className="mt-6 inline-block font-semibold underline">
              How the data is sourced and checked
            </Link>
          </div>
          <ul className="flex flex-wrap gap-3">
            {NEVER.map((item) => (
              <li
                key={item}
                className="rounded-full border border-current/25 px-4 py-2 text-lg font-medium line-through decoration-sign decoration-2"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-4 py-16 text-center">
        <h2 className="font-display text-4xl font-semibold tracking-[-0.015em] text-ink sm:text-5xl">
          Start with your own street.
        </h2>
        <p className="mt-3 text-lg text-ink-2">
          Every sale on it since 2010, and what each one sold for.
        </p>
        <Link href={ROUTES.map.path} className="btn btn-primary mt-8 px-7 text-base">
          Open the map
        </Link>
      </section>
    </>
  );
}
