import Link from "next/link";

export const PSRA_ATTRIBUTION =
  "Contains Residential Property Price Register data © Property Services Regulatory Authority (propertypriceregister.ie).";

export const PSRA_DISCLAIMER =
  "The register may contain errors and is not a property price index. Locations on this site are estimates; each one shows how precise it is.";

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-line bg-surface-2">
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8 text-sm text-muted">
        <p>{PSRA_ATTRIBUTION}</p>
        <p>{PSRA_DISCLAIMER}</p>
        <p>
          Map data © OpenStreetMap contributors (ODbL). Other sources and licences are listed on{" "}
          <Link className="underline" href="/sources">
            Data sources and methodology
          </Link>
          .
        </p>
        <nav aria-label="Legal" className="flex gap-4 pt-2">
          <Link className="underline" href="/privacy">
            Privacy
          </Link>
          <Link className="underline" href="/terms">
            Terms
          </Link>
          <Link className="underline" href="/report">
            Report an error or request removal
          </Link>
        </nav>
      </div>
    </footer>
  );
}
