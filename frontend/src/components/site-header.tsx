import Link from "next/link";

import { AccountMenu } from "@/components/auth/account-menu";
import { MobileMenu, NavLinks } from "@/components/site-nav";
import { StatusPill } from "@/components/status-pill";
import { BrandMark } from "@/components/ui/brand-mark";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ROUTES } from "@/lib/routes";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-[var(--color-glass)] backdrop-blur-md backdrop-saturate-150">
      <div className="relative mx-auto flex h-14 max-w-7xl items-center gap-2 px-4">
        <Link
          href={ROUTES.home.path}
          className="mr-3 flex items-center gap-2 rounded-full pr-2 font-display text-lg font-bold tracking-tight text-ink"
        >
          <BrandMark />
          <span>
            PPR<span className="font-medium text-muted">map</span>
          </span>
        </Link>
        <nav aria-label="Main" className="hidden md:block">
          <NavLinks />
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <StatusPill />
          <ThemeToggle />
          <div className="hidden pl-1 md:block">
            <AccountMenu />
          </div>
          <MobileMenu />
        </div>
      </div>
    </header>
  );
}
