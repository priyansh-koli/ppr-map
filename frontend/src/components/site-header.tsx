import Link from "next/link";

import { FreshnessBanner } from "@/components/freshness-banner";

import { PRIMARY_NAV, ROUTES } from "@/lib/routes";

export function SiteHeader() {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link href={ROUTES.home.path} className="text-lg font-semibold text-ink">
          PPR Map
        </Link>
        <nav aria-label="Main">
          <ul className="flex flex-wrap gap-4 text-sm">
            {PRIMARY_NAV.map((key) => (
              <li key={key}>
                <Link className="text-ink hover:underline" href={ROUTES[key].path}>
                  {ROUTES[key].title}
                </Link>
              </li>
            ))}
            <li>
              <Link className="font-medium text-accent hover:underline" href={ROUTES.login.path}>
                Sign in
              </Link>
            </li>
          </ul>
        </nav>
      </div>
      <FreshnessBanner />
    </header>
  );
}
