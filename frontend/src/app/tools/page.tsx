import Link from "next/link";

import { pageMetadata } from "@/components/placeholder-page";
import { ToolsRules } from "@/components/tools/calculators";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("tools");

const TOOLS = [
  {
    route: ROUTES.stampDuty,
    text: "Stamp duty on a home, band by band, with VAT taken out of a new home's price first.",
  },
  {
    route: ROUTES.affordability,
    text: "What the Central Bank's income and deposit limits let you borrow, and the repayment at a rate you were quoted.",
  },
];

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="Tools"
        title={ROUTES.tools.title}
        lead="Two calculators built on the official rules. Every rate names its source and the day we last checked it."
      />
      <ul className="grid gap-4 sm:grid-cols-2">
        {TOOLS.map(({ route, text }) => (
          <li key={route.path}>
            <Window title={`tool · ${route.title.toLowerCase()}`} bodyClassName="space-y-3 p-5">
              <h2 className="font-display text-2xl text-ink">{route.title}</h2>
              <p className="text-sm text-ink-2">{text}</p>
              <Link href={route.path} className="btn btn-primary btn-sm">
                Open the calculator
              </Link>
            </Window>
          </li>
        ))}
      </ul>
      <ToolsRules />
    </div>
  );
}
