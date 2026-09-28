"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AccountMenu } from "@/components/auth/account-menu";
import { PRIMARY_NAV, ROUTES } from "@/lib/routes";

/** Shorter names for the header; the pages keep their full titles. */
const NAV_LABEL: Partial<Record<(typeof PRIMARY_NAV)[number], string>> = {
  map: "Map",
  search: "Search",
  sources: "Sources",
};

function useActive(): (path: string) => boolean {
  const pathname = usePathname();
  return (path) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
}

export function NavLinks() {
  const active = useActive();
  return (
    <ul className="flex items-center gap-1 text-sm">
      {PRIMARY_NAV.map((key) => {
        const route = ROUTES[key];
        const current = active(route.path);
        return (
          <li key={key}>
            <Link
              href={route.path}
              aria-current={current ? "page" : undefined}
              className={`rounded-full px-3 py-1.5 font-medium transition-colors ${
                current ? "bg-ink text-desk" : "text-ink-2 hover:bg-fill hover:text-ink"
              }`}
            >
              {NAV_LABEL[key] ?? route.title}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Below `md`, the nav and account links fold into a sheet under the header. */
export function MobileMenu() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const button = useRef<HTMLButtonElement>(null);
  const active = useActive();
  // eslint-disable-next-line react-hooks/set-state-in-effect -- close after navigating
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls="mobile-menu"
        onClick={() => setOpen((o) => !o)}
        className="grid h-9 w-9 place-items-center rounded-full text-ink hover:bg-fill"
      >
        <span className="sr-only">Menu</span>
        <svg viewBox="0 0 20 20" className="h-5 w-5" aria-hidden="true">
          <path
            d={open ? "M5 5l10 10M15 5L5 15" : "M3 6h14M3 10h14M3 14h14"}
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>
      {open ? (
        <div
          id="mobile-menu"
          className="absolute inset-x-0 top-full border-b border-line bg-desk px-4 pb-5 pt-3 shadow-window"
        >
          <nav aria-label="Main">
            <ul className="grid gap-1">
              {PRIMARY_NAV.map((key) => (
                <li key={key}>
                  <Link
                    href={ROUTES[key].path}
                    aria-current={active(ROUTES[key].path) ? "page" : undefined}
                    className="block rounded-[10px] px-3 py-2.5 text-base font-medium text-ink hover:bg-fill aria-[current=page]:bg-fill"
                  >
                    {ROUTES[key].title}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="mt-3 border-t border-line pt-3">
            <AccountMenu stacked />
          </div>
        </div>
      ) : null}
    </div>
  );
}
