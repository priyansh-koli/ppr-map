"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { STATIC_PREVIEW } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { useSession } from "./session";

/** Account pages: their content for a signed-in user, else a way to sign in and come back. */
export function RequireSignIn({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  const path = usePathname();
  if (STATIC_PREVIEW) {
    return (
      <p className="text-muted">Accounts need the data server, which this preview does not have.</p>
    );
  }
  if (loading) return <p className="text-muted">Loading…</p>;
  if (!me) {
    return (
      <p>
        <Link
          className="font-medium text-accent underline"
          href={`${ROUTES.login.path}?next=${encodeURIComponent(path)}`}
        >
          Sign in
        </Link>{" "}
        to continue.
      </p>
    );
  }
  return <>{children}</>;
}
