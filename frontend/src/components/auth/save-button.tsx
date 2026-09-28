"use client";

import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { messageOf } from "./form";
import { useSession } from "./session";
import { SignInLink } from "./sign-in-link";

const buttonClass = "btn btn-secondary btn-sm";

/** Save a property to the wishlist; signed-out users get a way to sign in first. */
export function SaveButton({ propertyId }: { propertyId: string }) {
  const { me, loading } = useSession();
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  // Until the session check answers, nobody is known to be signed out.
  if (loading) {
    return (
      <button type="button" disabled aria-busy className={buttonClass}>
        Save to wishlist
      </button>
    );
  }
  if (!me) {
    return <SignInLink className="text-sm text-accent underline">Sign in to save</SignInLink>;
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
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={state === "saving"}
        className={buttonClass}
        onClick={async () => {
          setState("saving");
          setError(null);
          try {
            await api.saveProperty(propertyId);
            setState("saved");
          } catch (e) {
            // The API says why (a full wishlist is a 409), so show that.
            setError(`Could not save: ${messageOf(e)}`);
            setState("idle");
          }
        }}
      >
        Save to wishlist
      </button>
      <span role="status" aria-live="assertive" className="text-sm text-ink empty:sr-only">
        {error ?? ""}
      </span>
    </span>
  );
}
