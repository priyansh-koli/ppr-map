import Link from "next/link";

import { PSRA_ATTRIBUTION, PSRA_DISCLAIMER } from "@/lib/attribution";
import { ROUTES } from "@/lib/routes";

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-line bg-surface-2">
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8 text-sm text-muted">
        <p>{PSRA_ATTRIBUTION}</p>
        <p>{PSRA_DISCLAIMER}</p>
        <p>
          Map data © OpenStreetMap contributors (ODbL). Other sources and licences are listed on{" "}
          <Link className="underline" href={ROUTES.sources.path}>
            Data sources and methodology
          </Link>
          .
        </p>
        <nav aria-label="Legal" className="flex gap-4 pt-2">
          <Link className="underline" href={ROUTES.privacy.path}>
            Privacy
          </Link>
          <Link className="underline" href={ROUTES.terms.path}>
            Terms
          </Link>
          <Link className="underline" href={ROUTES.report.path}>
            Report an error or request removal
          </Link>
        </nav>
      </div>
    </footer>
  );
}
