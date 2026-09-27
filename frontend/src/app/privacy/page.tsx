import Link from "next/link";

import { DraftNotice } from "@/components/legal/draft-notice";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("privacy");

const h2 = "mt-8 text-xl font-semibold text-ink";

export default function Page() {
  return (
    <article className="mx-auto max-w-3xl space-y-4 px-4 py-10 leading-relaxed">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">{ROUTES.privacy.title}</h1>
      <DraftNotice />
      <p>Version 2026-09-27.</p>

      <h2 className={h2}>Using the map without an account</h2>
      <p>
        You can use the map, property pages and area pages without an account. We set no tracking or
        advertising cookies and load no third-party analytics or ad scripts. The map, its background
        and its fonts are served from our own servers.
      </p>
      <p>
        Two cookies are strictly necessary and are always set: <code>ppr_csrf</code>, which protects
        forms from being submitted by other websites, and, only when you sign in, a session cookie
        that keeps you signed in.
      </p>
      <p>
        To limit abuse (for example repeated sign-in attempts), we count requests per IP address.
        The address is stored only as a salted hash, for at most an hour.
      </p>

      <h2 className={h2}>Your account</h2>
      <ul className="list-disc space-y-2 pl-6">
        <li>
          <span className="font-medium">What we keep:</span> your name, email address, a secure hash
          of your password (never the password itself), and anything you choose to add: your profile
          (what you are looking for and your budget), saved properties and notes, and your history.
        </li>
        <li>
          <span className="font-medium">Consent records:</span> when you accepted these terms and
          this policy, confirmed you are 18 or older, and chose whether to get news by email, with a
          hashed IP address and browser description as evidence.
        </li>
        <li>
          <span className="font-medium">Sessions:</span> for each device you sign in on, when it was
          last used, its browser description and a hashed IP address, so you can end sessions and we
          can spot misuse. A session ends after 14 days without use, after 90 days in all, or when
          you sign out.
        </li>
        <li>
          <span className="font-medium">History:</span> the properties you open, kept for 12 months.
          You can clear it, remove single entries, or switch it off in your settings.
        </li>
        <li>
          <span className="font-medium">Emails:</span> we send only what you need (confirming your
          address, resetting your password, a notice when your password changes) and news only if
          you opt in.
        </li>
      </ul>
      <p>
        We use this information only to run the service for you. We do not sell it or share it with
        advertisers.
      </p>

      <h2 className={h2}>Your rights</h2>
      <ul className="list-disc space-y-2 pl-6">
        <li>
          <span className="font-medium">See your data:</span> download everything stored about your
          account from your{" "}
          <Link className="text-accent underline" href={ROUTES.account.path}>
            account settings
          </Link>
          .
        </li>
        <li>
          <span className="font-medium">Correct it:</span> change your details and preferences in
          your settings.
        </li>
        <li>
          <span className="font-medium">Delete it:</span> delete your account in your settings. It
          closes at once, and everything in it is deleted after 30 days.
        </li>
        <li>
          <span className="font-medium">Complain:</span> you can complain to the Data Protection
          Commission (dataprotection.ie).
        </li>
      </ul>

      <h2 className={h2}>The sales data</h2>
      <p>
        Sale addresses and prices come from the Residential Property Price Register, which the
        Property Services Regulatory Authority publishes by law. We never combine it with any data
        that could identify who bought or sold a home. If an address should not be shown, you can
        ask us to correct or remove it.
      </p>

      <h2 className={h2}>Contact</h2>
      <p>The operator&apos;s name and contact address will be added here before launch.</p>
    </article>
  );
}
