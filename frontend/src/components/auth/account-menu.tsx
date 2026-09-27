"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ROUTES } from "@/lib/routes";

import { messageOf } from "./form";
import { useSession } from "./session";

export function AccountMenu() {
  const { me, signOut } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me) {
    return (
      <Link className="font-medium text-accent hover:underline" href={ROUTES.login.path}>
        Sign in
      </Link>
    );
  }
  return (
    <span className="flex flex-wrap gap-4">
      <Link className="text-ink hover:underline" href={ROUTES.wishlist.path}>
        {ROUTES.wishlist.title}
      </Link>
      <Link className="text-ink hover:underline" href={ROUTES.account.path}>
        Account
      </Link>
      <button
        type="button"
        className="font-medium text-accent hover:underline disabled:opacity-60"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await signOut();
            router.push(ROUTES.home.path);
          } catch (e) {
            setError(`Could not sign out: ${messageOf(e)}`);
          } finally {
            setBusy(false);
          }
        }}
      >
        Sign out
      </button>
      <span role="status" aria-live="assertive" className="text-sm text-ink empty:sr-only">
        {error ?? ""}
      </span>
    </span>
  );
}
