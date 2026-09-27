import Link from "next/link";

import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("home");

const POINTS = [
  {
    title: "Every sale since 2010",
    text: "All residential sales on the Property Price Register, on one map, with each property's full sale history.",
  },
  {
    title: "Honest locations",
    text: "The register has no coordinates. Every point says how precisely its address was found: the house, the street, or only the town.",
  },
  {
    title: "What is nearby",
    text: "Stops, schools, shops and the area's price trend, each with its source and date. Nothing is invented: no bedrooms, sizes or photos.",
  },
];

export default function Page() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-ink">
        {ROUTES.home.title}
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-muted">{ROUTES.home.summary}</p>
      <p className="mt-8">
        <Link
          href={ROUTES.map.path}
          className="inline-block rounded-md bg-accent px-5 py-3 font-medium text-surface hover:opacity-90"
        >
          Explore the map
        </Link>
      </p>
      <ul className="mt-12 grid gap-8 sm:grid-cols-3">
        {POINTS.map((p) => (
          <li key={p.title}>
            <h2 className="font-semibold text-ink">{p.title}</h2>
            <p className="mt-2 text-muted">{p.text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
