"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { api, ApiError } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { useSession } from "./session";

/** Save a property to the wishlist; signed-out users get a way to sign in first. */
export function SaveButton({ propertyId }: { propertyId: string }) {
  const { me } = useSession();
  const path = usePathname();
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  if (!me) {
    return (
      <Link
        className="text-sm text-accent underline"
        href={`${ROUTES.login.path}?next=${encodeURIComponent(path)}`}
      >
        Sign in to save
      </Link>
    );
  }
  if (state === "saved") {
    return (
      <span className="text-sm">
        Saved.{" "}
        <Link className="text-accent underline" href={ROUTES.wishlist.path}>
          Open your wishlist
        </Link>
      </span>
    );
  }
  return (
    <button
      type="button"
      disabled={state === "saving"}
      className="rounded border border-line px-3 py-1 text-sm font-medium text-ink hover:bg-surface-2"
      onClick={async () => {
        setState("saving");
        try {
          await api.saveProperty(propertyId);
          setState("saved");
        } catch (e) {
          setState(e instanceof ApiError ? "error" : "error");
        }
      }}
    >
      {state === "error" ? "Could not save; try again" : "Save to wishlist"}
    </button>
  );
}
