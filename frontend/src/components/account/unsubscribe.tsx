"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { messageOf } from "../auth/form";

/** The link in an alert email. It asks first, so a mail scanner opening it changes nothing. */
export function UnsubscribeAlert() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<{ done?: string; error?: string; busy?: boolean }>({});
  if (!token) return <p>This link is incomplete. Manage your alerts from your account instead.</p>;
  if (state.done)
    return (
      <p>
        Alerts for &ldquo;{state.done}&rdquo; are off. The search is still saved:{" "}
        <Link className="text-accent underline" href={ROUTES.savedSearches.path}>
          manage your saved searches
        </Link>
        .
      </p>
    );
  return (
    <div className="space-y-4">
      <p>Stop the email alerts for this saved search? The search itself stays saved.</p>
      {state.error ? <p role="alert">{state.error}</p> : null}
      <button
        type="button"
        className="btn btn-primary"
        disabled={state.busy}
        onClick={async () => {
          setState({ busy: true });
          try {
            setState({ done: (await api.unsubscribe(token)).name });
          } catch (e) {
            setState({ error: messageOf(e) });
          }
        }}
      >
        Stop these alerts
      </button>
    </div>
  );
}
