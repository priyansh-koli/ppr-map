"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { messageOf } from "@/components/auth/form";
import { api, type ReportIn, STATIC_PREVIEW } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

const TYPES: [ReportIn["requestType"], string, string][] = [
  [
    "suppress_display",
    "Stop showing this address",
    "The sale stays on the official register, which we cannot change, but we stop showing the address on this site.",
  ],
  ["correct_location", "The location on the map is wrong", "Tell us where it should be."],
  ["correct_details", "A detail is wrong", "Tell us what, and what it should be."],
];

/** Correction and removal requests (D-052). No account needed; a hidden field traps bots. */
export function ReportForm() {
  const propertyId = useSearchParams().get("property");
  const [address, setAddress] = useState("");
  const [type, setType] = useState<ReportIn["requestType"]>("suppress_display");
  const [relationship, setRelationship] = useState<ReportIn["relationship"]>("owner");
  const [reason, setReason] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [state, setState] = useState<{ busy?: boolean; error?: string; reference?: string }>({});
  useEffect(() => {
    if (!propertyId || STATIC_PREVIEW) return;
    api
      .summary(propertyId)
      .then((s) => setAddress((a) => a || s.address))
      .catch(() => {});
  }, [propertyId]);
  if (STATIC_PREVIEW) return <p className="text-muted">Requests need the data server.</p>;
  if (state.reference)
    return (
      <div className="space-y-3">
        <p className="font-medium text-ink">Thank you: your request is in.</p>
        <p>
          Its reference is <strong className="font-mono">{state.reference}</strong>. We review every
          request by hand
          {email ? " and will email you when it is decided" : ""}.
        </p>
        <Link className="text-accent underline" href={ROUTES.map.path}>
          Back to the map
        </Link>
      </div>
    );
  return (
    <form
      className="space-y-5 text-sm"
      onSubmit={async (e) => {
        e.preventDefault();
        setState({ busy: true });
        try {
          const { reference } = await api.report({
            propertyId: propertyId || null,
            address: address.trim(),
            requestType: type,
            relationship,
            reason: reason.trim() || null,
            email: email.trim() || null,
            website: website || null,
          });
          setState({ reference });
        } catch (err) {
          setState({ error: messageOf(err) });
        }
      }}
    >
      <fieldset className="space-y-2">
        <legend className="font-medium text-ink">What would you like us to do?</legend>
        {TYPES.map(([value, label, hint]) => (
          <label key={value} className="flex items-start gap-2">
            <input
              type="radio"
              name="type"
              checked={type === value}
              onChange={() => setType(value)}
              className="mt-1"
            />
            <span>
              {label}
              <span className="block text-xs text-muted">{hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <label className="block">
        <span className="font-medium text-ink">The address</span>
        <input
          className="mt-1 w-full px-3 py-2.5"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          minLength={3}
          maxLength={300}
          required
        />
      </label>
      <label className="block">
        <span className="font-medium text-ink">You are</span>
        <select
          className="mt-1 w-full px-3 py-2.5"
          value={relationship}
          onChange={(e) => setRelationship(e.target.value as ReportIn["relationship"])}
        >
          <option value="owner">The owner</option>
          <option value="occupant">Living there</option>
          <option value="other">Someone else</option>
        </select>
      </label>
      <label className="block">
        <span className="font-medium text-ink">Anything we should know</span>{" "}
        <span className="text-muted">(optional)</span>
        <textarea
          className="mt-1 w-full px-3 py-2.5"
          rows={4}
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="font-medium text-ink">Your email</span>{" "}
        <span className="text-muted">(optional: only to tell you the outcome)</span>
        <input
          className="mt-1 w-full px-3 py-2.5"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      {/* Hidden from people, filled in by simple bots. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label>
          Website
          <input
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
        </label>
      </div>
      <p className="text-xs text-muted">
        We keep your email and message until 12 months after the request is decided, then delete
        them. See the{" "}
        <Link className="underline" href={ROUTES.privacy.path}>
          privacy policy
        </Link>
        .
      </p>
      {state.error ? (
        <p role="alert" className="text-ink">
          {state.error}
        </p>
      ) : null}
      <button type="submit" className="btn btn-primary" disabled={state.busy}>
        Send the request
      </button>
    </form>
  );
}
