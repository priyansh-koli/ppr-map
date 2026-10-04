"use client";

import Link from "next/link";
import { useState } from "react";

import { FREQUENCIES } from "@/components/account/saved-searches";
import { messageOf } from "@/components/auth/form";
import { useSession } from "@/components/auth/session";
import { SignInLink } from "@/components/auth/sign-in-link";
import { type AlertFrequency, api } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

/** "Save this search", with an optional alert. Signed-out users are offered sign-in. */
export function SaveSearch({
  query,
  suggestedName,
  geolocated,
}: {
  query: Record<string, string>;
  suggestedName: string;
  geolocated: boolean;
}) {
  const { me, loading } = useSession();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [frequency, setFrequency] = useState<AlertFrequency>("on_data_update");
  const [saving, setSaving] = useState(false);
  // The search that was saved: "Saved." holds for that search only, so a new search can be
  // saved without a reload (P1 #33).
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = new URLSearchParams(
    Object.entries(query).sort(([a], [b]) => a.localeCompare(b)),
  ).toString();
  if (loading) return null;
  if (!me)
    return (
      <SignInLink className="text-sm text-accent underline">Sign in to save this search</SignInLink>
    );
  if (savedKey === key)
    return (
      <span className="text-sm">
        Saved.{" "}
        <Link className="text-accent underline" href={ROUTES.savedSearches.path}>
          Your saved searches
        </Link>
      </span>
    );
  if (!open)
    return (
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => {
          setName(suggestedName.slice(0, 100));
          setOpen(true);
        }}
      >
        Save this search
      </button>
    );
  return (
    <form
      className="window w-full space-y-3 p-4 text-sm sm:w-96"
      aria-label="Save this search"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        try {
          await api.saveSearch(name.trim(), query, frequency);
          setSavedKey(key);
          setOpen(false);
        } catch (err) {
          setError(`Could not save: ${messageOf(err)}`);
        } finally {
          setSaving(false);
        }
      }}
    >
      {geolocated ? (
        <p className="text-muted">
          This search is near your location: saving it keeps that point, so its alerts can cover it.
        </p>
      ) : null}
      <label className="block">
        <span className="text-muted">Name</span>
        <input
          className="mt-0.5 w-full px-2.5 py-1.5"
          value={name}
          required
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="text-muted">Alert</span>
        <select
          className="mt-0.5 w-full px-2.5 py-1.5"
          value={frequency}
          onChange={(e) => setFrequency(e.target.value as AlertFrequency)}
        >
          {FREQUENCIES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {!me.emailVerified && frequency !== "off" ? (
        <p className="text-muted">Alerts start once you confirm your email address.</p>
      ) : null}
      {error ? (
        <p role="alert" className="text-ink">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary btn-sm" disabled={saving || !name.trim()}>
          Save
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
