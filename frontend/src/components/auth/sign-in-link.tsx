"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useSyncExternalStore } from "react";

import { ROUTES } from "@/lib/routes";

function onHistory(change: () => void): () => void {
  window.addEventListener("popstate", change);
  return () => window.removeEventListener("popstate", change);
}

/**
 * The sign-in page, coming back here afterwards with the query string (map filters, compare
 * ids) intact. The query is read from `window.location` rather than useSearchParams, which
 * would need a Suspense boundary on every statically exported page; the server render has none.
 */
export function SignInLink({ className, children }: { className?: string; children: ReactNode }) {
  const path = usePathname();
  const search = useSyncExternalStore(
    onHistory,
    () => window.location.search,
    () => "",
  );
  return (
    <Link
      className={className}
      href={`${ROUTES.login.path}?next=${encodeURIComponent(path + search)}`}
    >
      {children}
    </Link>
  );
}
