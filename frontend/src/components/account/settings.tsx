"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";

import { useSession } from "@/components/auth/session";
import { api, ApiError, type Me } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import {
  buttonClass,
  Field,
  fieldOf,
  FormMessage,
  inputClass,
  messageOf,
  useBusy,
} from "../auth/form";

type Msg = { error?: string; success?: string; field?: string | null } | null;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-line pt-6">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}

function Details({ me, onSaved }: { me: Me; onSaved: () => void }) {
  const [msg, setMsg] = useState<Msg>(null);
  const { busy, run } = useBusy();
  const messageId = useId();
  const errorFor = (field: string) => (msg?.field === field ? messageId : undefined);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const budgetMin = String(f.get("budgetMin") ?? "");
    const budgetMax = String(f.get("budgetMax") ?? "");
    void run(async () => {
      setMsg(null);
      try {
        await api.updateMe({
          fullName: String(f.get("fullName")),
          historyEnabled: f.get("history") === "on",
          marketingOptIn: f.get("marketing") === "on",
          profile: {
            userType: (String(f.get("userType")) || null) as Me["profile"]["userType"],
            propertyInterest: (String(f.get("interest")) ||
              null) as Me["profile"]["propertyInterest"],
            budgetMin: budgetMin ? Number(budgetMin) : null,
            budgetMax: budgetMax ? Number(budgetMax) : null,
            counties: me.profile.counties ?? null,
          },
        });
        setMsg({ success: "Saved." });
        onSaved();
      } catch (err) {
        setMsg({ error: messageOf(err), field: fieldOf(err) });
      }
    });
  };
  return (
    <form onSubmit={submit} className="max-w-md space-y-4">
      <FormMessage id={messageId} error={msg?.error} success={msg?.success} />
      <Field
        label="Name"
        name="fullName"
        defaultValue={me.fullName}
        required
        maxLength={200}
        errorId={errorFor("fullName")}
      />
      <label className="block text-sm">
        <span className="font-medium text-ink">I am</span>
        <select name="userType" defaultValue={me.profile.userType ?? ""} className={inputClass}>
          <option value="">Rather not say</option>
          <option value="first_time_buyer">Buying for the first time</option>
          <option value="mover">Moving home</option>
          <option value="investor">Investing</option>
          <option value="agent">An estate agent</option>
          <option value="researcher">Researching</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="font-medium text-ink">Interested in</span>
        <select
          name="interest"
          defaultValue={me.profile.propertyInterest ?? ""}
          className={inputClass}
        >
          <option value="">Either</option>
          <option value="new">New builds</option>
          <option value="second_hand">Second-hand homes</option>
          <option value="both">Both</option>
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Budget from (€)"
          name="budgetMin"
          type="number"
          min={0}
          step={10000}
          defaultValue={me.profile.budgetMin ?? ""}
          errorId={errorFor("budgetMin")}
        />
        <Field
          label="Budget to (€)"
          name="budgetMax"
          type="number"
          min={0}
          step={10000}
          defaultValue={me.profile.budgetMax ?? ""}
          errorId={errorFor("budgetMax")}
        />
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="history" defaultChecked={me.historyEnabled} className="mt-1" />
        <span>
          Keep a history of the properties I look at (for 12 months). Switching this off stops new
          entries.
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          name="marketing"
          defaultChecked={me.marketingOptIn}
          className="mt-1"
        />
        <span>Email me occasional news about PPR Map.</span>
      </label>
      <button className={buttonClass} disabled={busy}>
        {busy ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

/** Which field a password-change error is about: the API names the new one on a 422. */
function passwordField(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  if (err.status === 403) return "current";
  return err.status === 422 ? "next" : null;
}

function ChangePassword() {
  const [msg, setMsg] = useState<Msg>(null);
  const { busy, run } = useBusy();
  const messageId = useId();
  const errorFor = (field: string) => (msg?.field === field ? messageId : undefined);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    void run(async () => {
      setMsg(null);
      try {
        await api.changePassword(String(f.get("current")), String(f.get("next")));
        setMsg({ success: "Password changed. You were signed out everywhere else." });
        form.reset();
      } catch (err) {
        setMsg({ error: messageOf(err), field: passwordField(err) });
      }
    });
  };
  return (
    <form onSubmit={submit} className="max-w-md space-y-4">
      <FormMessage id={messageId} error={msg?.error} success={msg?.success} />
      <Field
        label="Current password"
        name="current"
        type="password"
        autoComplete="current-password"
        required
        errorId={errorFor("current")}
      />
      <Field
        label="New password"
        name="next"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        errorId={errorFor("next")}
      />
      <button className={buttonClass} disabled={busy}>
        {busy ? "Changing…" : "Change password"}
      </button>
    </form>
  );
}

function DeleteAccount() {
  const { refresh } = useSession();
  const router = useRouter();
  const [msg, setMsg] = useState<Msg>(null);
  const [closed, setClosed] = useState(false);
  const { busy, run } = useBusy();
  const messageId = useId();
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    void run(async () => {
      setMsg(null);
      try {
        await api.deleteMe(String(f.get("password")));
      } catch (err) {
        setMsg({ error: messageOf(err), field: "password" });
        return;
      }
      // Closed: the button stays disabled while the session clears and the page moves on.
      setClosed(true);
      await refresh();
      router.push(ROUTES.home.path);
    });
  };
  return (
    <form onSubmit={submit} className="max-w-md space-y-4">
      <p className="text-sm text-muted">
        Your account closes at once and everything in it is deleted after 30 days. This cannot be
        undone.
      </p>
      <FormMessage id={messageId} error={msg?.error} />
      <Field
        label="Your password, to confirm"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        errorId={msg?.field === "password" ? messageId : undefined}
      />
      <button
        className="rounded-md border border-line px-4 py-2 font-medium text-ink hover:bg-surface-2 disabled:opacity-60"
        disabled={busy || closed}
      >
        {busy ? "Deleting…" : "Delete my account"}
      </button>
    </form>
  );
}

export function AccountSettings() {
  const { me, refresh, signOut } = useSession();
  const router = useRouter();
  const [msg, setMsg] = useState<Msg>(null);
  const resend = useBusy();
  const everywhere = useBusy();
  if (!me) return null;
  return (
    <div className="space-y-8">
      <p className="text-sm">
        Signed in as <span className="font-medium">{me.email}</span>.{" "}
        {me.emailVerified ? (
          "Your email is confirmed."
        ) : (
          <>
            Your email is not confirmed yet.{" "}
            <button
              type="button"
              className="text-accent underline disabled:opacity-60"
              disabled={resend.busy}
              onClick={() =>
                resend.run(async () => {
                  try {
                    setMsg({ success: (await api.resendVerification()).message });
                  } catch (e) {
                    setMsg({ error: messageOf(e) });
                  }
                })
              }
            >
              Send the email again
            </button>
          </>
        )}
      </p>
      <FormMessage error={msg?.error} success={msg?.success} />
      <Section title="Details and preferences">
        <Details me={me} onSaved={() => void refresh()} />
      </Section>
      <Section title="Password">
        <ChangePassword />
      </Section>
      <Section title="Your data">
        <p className="text-sm">
          <a className="text-accent underline" href="/api/v1/me/export" download>
            Download everything stored about your account
          </a>{" "}
          (JSON).
        </p>
        <button
          type="button"
          className="text-sm text-accent underline disabled:opacity-60"
          disabled={everywhere.busy}
          onClick={() =>
            everywhere.run(async () => {
              setMsg(null);
              try {
                await api.logoutAll();
              } catch (e) {
                // 401: this session had already ended. Otherwise nothing may have been signed
                // out, so say so and show what the server now says.
                if (!(e instanceof ApiError && e.status === 401)) {
                  setMsg({ error: `Could not sign out everywhere: ${messageOf(e)}` });
                  await refresh();
                  return;
                }
              }
              // Every session is gone, this one included; clear it here too.
              await signOut().catch(() => refresh());
              router.push(ROUTES.login.path);
            })
          }
        >
          Sign out on every device
        </button>
      </Section>
      <Section title="Delete account">
        <DeleteAccount />
      </Section>
    </div>
  );
}
