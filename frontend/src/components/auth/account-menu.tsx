"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ROUTES } from "@/lib/routes";

import { useSession } from "./session";

export function AccountMenu() {
  const { me, signOut } = useSession();
  const router = useRouter();
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
        className="font-medium text-accent hover:underline"
        onClick={async () => {
          await signOut();
          router.push(ROUTES.home.path);
        }}
      >
        Sign out
      </button>
    </span>
  );
}
