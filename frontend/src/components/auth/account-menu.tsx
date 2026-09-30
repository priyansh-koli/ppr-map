"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ROUTES } from "@/lib/routes";

import { messageOf } from "./form";
import { useSession } from "./session";

const link = "rounded-full px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-fill hover:text-ink";

/** `stacked` lays the links out as a column, for the mobile menu. */
export function AccountMenu({ stacked = false }: { stacked?: boolean }) {
  const { me, signOut } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me) {
    return (
      <Link className="btn btn-secondary btn-sm" href={ROUTES.login.path}>
        Sign in
      </Link>
    );
  }
  return (
    <span className={stacked ? "grid gap-1" : "flex items-center gap-1"}>
      <Link className={link} href={ROUTES.wishlist.path}>
        {ROUTES.wishlist.title}
      </Link>
      <Link className={link} href={ROUTES.account.path}>
        Account
      </Link>
      {me.permissions.includes("admin:audit") ? (
        <Link className={link} href={ROUTES.admin.path}>
          Admin
        </Link>
      ) : null}
      <button
        type="button"
        className={`${link} text-left disabled:opacity-60`}
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
