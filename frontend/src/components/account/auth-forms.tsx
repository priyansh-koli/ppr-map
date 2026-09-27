"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { useSession } from "@/components/auth/session";
import { api, type Policies, STATIC_PREVIEW } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { buttonClass, Field, FormMessage, messageOf, safeNext } from "../auth/form";

function searchParam(name: string): string | null {
  return typeof window === "undefined"
    ? null
    : new URLSearchParams(window.location.search).get(name);
}

function NeedsServer() {
  return (
    <p className="text-muted">Accounts need the data server, which this preview does not have.</p>
  );
}

export function LoginForm() {
  const { refresh } = useSession();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (STATIC_PREVIEW) return <NeedsServer />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api.login(String(form.get("email")), String(form.get("password")));
      await refresh();
      router.push(safeNext(searchParam("next")));
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      <FormMessage error={error} />
      <Field label="Email" name="email" type="email" autoComplete="email" required />
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
      />
      <button className={buttonClass} disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="text-sm">
        <Link className="text-accent underline" href={ROUTES.forgotPassword.path}>
          Forgot your password?
        </Link>{" "}
        ·{" "}
        <Link className="text-accent underline" href={ROUTES.register.path}>
          Create an account
        </Link>
      </p>
    </form>
  );
}

export function RegisterForm() {
  const [policies, setPolicies] = useState<Policies | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!STATIC_PREVIEW)
      api
        .policies()
        .then(setPolicies)
        .catch((e: unknown) => setError(messageOf(e)));
  }, []);
  if (STATIC_PREVIEW) return <NeedsServer />;
  if (done) return <FormMessage success={done} />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!policies) return;
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const res = await api.register({
        fullName: String(form.get("fullName")),
        email: String(form.get("email")),
        password: String(form.get("password")),
        age18Plus: true,
        acceptTerms: true,
        termsVersion: policies.termsVersion,
        privacyVersion: policies.privacyVersion,
        marketingOptIn: form.get("marketing") === "on",
      });
      setDone(`${res.message} The link works for 24 hours.`);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      <FormMessage error={error} />
      <Field label="Name" name="fullName" autoComplete="name" required maxLength={200} />
      <Field label="Email" name="email" type="email" autoComplete="email" required />
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        hint="At least 10 characters. A few unrelated words is a good password."
      />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="age" required className="mt-1" />
        <span>I am 18 or older.</span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="terms" required className="mt-1" />
        <span>
          I accept the{" "}
          <Link className="text-accent underline" href={ROUTES.terms.path}>
            terms of use
          </Link>{" "}
          and have read the{" "}
          <Link className="text-accent underline" href={ROUTES.privacy.path}>
            privacy policy
          </Link>
          .
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="marketing" className="mt-1" />
        <span>
          Email me occasional news about PPR Map. (Optional; you can change this any time.)
        </span>
      </label>
      <button className={buttonClass} disabled={busy || !policies}>
        {busy ? "Creating…" : "Create account"}
      </button>
      <p className="text-sm">
        Already registered?{" "}
        <Link className="text-accent underline" href={ROUTES.login.path}>
          Sign in
        </Link>
      </p>
    </form>
  );
}

export function VerifyEmail() {
  const { me, refresh } = useSession();
  const [state, setState] = useState<{ error?: string; success?: string } | null>(null);
  const token = useSearchParams().get("token");
  useEffect(() => {
    if (!token || STATIC_PREVIEW) return;
    api
      .verifyEmail(token)
      .then((r) => {
        setState({ success: r.message });
        void refresh();
      })
      .catch((e: unknown) => setState({ error: messageOf(e) }));
  }, [token, refresh]);
  if (STATIC_PREVIEW) return <NeedsServer />;
  if (token) return state ? <FormMessage {...state} /> : <p aria-busy>Confirming…</p>;
  return (
    <div className="space-y-3 text-sm">
      <p>Open the link in the email we sent you to confirm your address.</p>
      {me && !me.emailVerified ? (
        <button
          type="button"
          className={buttonClass}
          onClick={() =>
            api
              .resendVerification()
              .then((r) => setState({ success: r.message }))
              .catch((e: unknown) => setState({ error: messageOf(e) }))
          }
        >
          Send the email again
        </button>
      ) : null}
      {state ? <FormMessage {...state} /> : null}
    </div>
  );
}

export function ForgotPasswordForm() {
  const [message, setMessage] = useState<{ error?: string; success?: string } | null>(null);
  if (STATIC_PREVIEW) return <NeedsServer />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      const r = await api.forgotPassword(String(form.get("email")));
      setMessage({ success: r.message });
    } catch (err) {
      setMessage({ error: messageOf(err) });
    }
  };
  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      {message ? <FormMessage {...message} /> : null}
      <Field label="Email" name="email" type="email" autoComplete="email" required />
      <button className={buttonClass}>Email me a reset link</button>
    </form>
  );
}

export function ResetPasswordForm() {
  const token = useSearchParams().get("token");
  const [message, setMessage] = useState<{ error?: string; success?: string } | null>(null);
  if (STATIC_PREVIEW) return <NeedsServer />;
  if (!token) return <p>This page needs the link from your reset email.</p>;
  if (message?.success) {
    return (
      <div className="space-y-3">
        <FormMessage success={message.success} />
        <Link className="text-accent underline" href={ROUTES.login.path}>
          Sign in
        </Link>
      </div>
    );
  }
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (form.get("password") !== form.get("confirm")) {
      setMessage({ error: "The two passwords are different." });
      return;
    }
    try {
      const r = await api.resetPassword(token, String(form.get("password")));
      setMessage({ success: r.message });
    } catch (err) {
      setMessage({ error: messageOf(err) });
    }
  };
  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      {message ? <FormMessage {...message} /> : null}
      <Field
        label="New password"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
      />
      <Field
        label="New password again"
        name="confirm"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
      />
      <button className={buttonClass}>Set password</button>
    </form>
  );
}
