import Link from "next/link";

import { DraftNotice } from "@/components/legal/draft-notice";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("terms");

const h2 = "mt-8 text-xl font-semibold text-ink";

export default function Page() {
  return (
    <article className="mx-auto max-w-3xl space-y-4 px-4 py-10 leading-relaxed">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">{ROUTES.terms.title}</h1>
      <DraftNotice />
      <p>Version 2026-09-27.</p>

      <h2 className={h2}>What this site is</h2>
      <p>
        PPR Map shows residential property sales from the Property Price Register on a map, with
        nearby places and price statistics. It is information, not advice: it is not a valuation, a
        survey, or financial or legal advice.
      </p>

      <h2 className={h2}>How accurate it is</h2>
      <ul className="list-disc space-y-2 pl-6">
        <li>
          The register may contain errors and is not a property price index. We show sales as they
          were filed.
        </li>
        <li>
          The register has no map coordinates. We place each sale from its address, and every
          location says how precise it is: the house, the street, or only the town, townland or
          county.
        </li>
        <li>
          Nearby places come from open data (see{" "}
          <Link className="text-accent underline" href={ROUTES.sources.path}>
            data sources
          </Link>
          ), have dates, and may be out of date or incomplete. Distances are straight lines.
        </li>
        <li>Check anything important with the original source before you rely on it.</li>
      </ul>

      <h2 className={h2}>Your account</h2>
      <p>
        You must be 18 or older to create an account. Keep your password to yourself; you are
        responsible for what is done with your account. You can delete it at any time in your{" "}
        <Link className="text-accent underline" href={ROUTES.account.path}>
          settings
        </Link>
        .
      </p>

      <h2 className={h2}>Fair use</h2>
      <ul className="list-disc space-y-2 pl-6">
        <li>Do not try to identify, contact or harass the people who bought or sold a home.</li>
        <li>
          Do not copy the site at scale or overload it; requests are rate-limited. The underlying
          datasets are available from their publishers under their own licences.
        </li>
        <li>Do not try to get into accounts or parts of the service that are not yours.</li>
      </ul>
      <p>We may suspend accounts that break these rules.</p>

      <h2 className={h2}>Data and credits</h2>
      <p>
        Contains Residential Property Price Register data © Property Services Regulatory Authority.
        Map data © OpenStreetMap contributors (ODbL). Other sources and their licences are listed on
        the data sources page.
      </p>

      <h2 className={h2}>Changes and contact</h2>
      <p>
        If these terms change, the version date above changes. The operator&apos;s name and contact
        address will be added here before launch.
      </p>
    </article>
  );
}
