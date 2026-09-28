import Link from "next/link";

import { BrandMark } from "@/components/ui/brand-mark";
import { PSRA_ATTRIBUTION, PSRA_DISCLAIMER } from "@/lib/attribution";
import { ROUTES } from "@/lib/routes";

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-line bg-[var(--color-glass)]">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm md:grid-cols-[1fr_2fr]">
        <div>
          <p className="flex items-center gap-2 font-display text-base font-bold text-ink">
            <BrandMark className="h-6 w-6" />
            PPR<span className="-ml-2 font-medium text-muted">map</span>
          </p>
          <p className="mt-3 max-w-xs text-muted">
            Every sale on the register, placed as precisely as its address allows, and honest about
            how precisely that is.
          </p>
          <nav aria-label="Legal" className="mt-4 flex flex-wrap gap-x-4 gap-y-2">
            <Link className="text-ink-2 underline" href={ROUTES.privacy.path}>
              Privacy
            </Link>
            <Link className="text-ink-2 underline" href={ROUTES.terms.path}>
              Terms
            </Link>
            <Link className="text-ink-2 underline" href={ROUTES.report.path}>
              Report an error or request removal
            </Link>
          </nav>
        </div>
        <div className="space-y-3 text-muted md:border-l md:border-line md:pl-8">
          <p>{PSRA_ATTRIBUTION}</p>
          <p>{PSRA_DISCLAIMER}</p>
          <p>
            Map data © OpenStreetMap contributors (ODbL). Other sources and licences are listed on{" "}
            <Link className="text-ink-2 underline" href={ROUTES.sources.path}>
              Data sources and methodology
            </Link>
            .
          </p>
        </div>
      </div>
    </footer>
  );
}
