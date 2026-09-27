"use client";

import type { ReactNode } from "react";

import { STATIC_PREVIEW } from "@/lib/api/client";

import { useSession } from "./session";
import { SignInLink } from "./sign-in-link";

/** Account pages: their content for a signed-in user, else a way to sign in and come back. */
export function RequireSignIn({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  if (STATIC_PREVIEW) {
    return (
      <p className="text-muted">Accounts need the data server, which this preview does not have.</p>
    );
  }
  if (loading) return <p className="text-muted">Loading…</p>;
  if (!me) {
    return (
      <p>
        <SignInLink className="font-medium text-accent underline">Sign in</SignInLink> to continue.
      </p>
    );
  }
  return <>{children}</>;
}
