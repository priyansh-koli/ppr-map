"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { messageOf } from "@/components/auth/form";
import { ConfidenceChip } from "@/components/ui/confidence-chip";
import {
  type AdminJob,
  type AdminOverview,
  type AdminUser,
  api,
  type IngestRun,
  type IngestRunDetail,
  type QueueItem,
  type RemovalRequest,
} from "@/lib/api/client";
import { COUNTIES, countyName } from "@/lib/filters";
import { formatDate, formatDateTime } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { Pager, td, th, usePage } from "./common";

function Problem({ text }: { text?: string | null }) {
  return text ? (
    <p role="alert" className="rounded-[10px] bg-accent-wash px-3 py-2 text-sm text-ink">
      {text}
    </p>
  ) : null;
}

function duration(run: IngestRun): string {
  if (!run.finishedAt) return run.status === "running" ? "running" : "–";
  const s = (Date.parse(run.finishedAt) - Date.parse(run.startedAt)) / 1000;
  return s < 90
    ? `${Math.round(s)} s`
    : s < 5400
      ? `${Math.round(s / 60)} min`
      : `${(s / 3600).toFixed(1)} h`;
}

// --- overview ------------------------------------------------------------------------------

export function Overview() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.admin
      .overview()
      .then(setData)
      .catch((e: unknown) => setError(messageOf(e)));
  }, []);
  if (error) return <Problem text={error} />;
  if (!data) return <p aria-busy>Loading…</p>;
  const tiles: [string, number, string][] = [
    ["Open removal and correction requests", data.openRequests, ROUTES.adminRemovals.path],
    ["Routing-key conflicts to check", data.routingKeyConflicts, `${ROUTES.adminGeocode.path}`],
    [
      "Properties placed only by routing key or county",
      data.lowConfidenceProperties,
      ROUTES.adminGeocode.path,
    ],
    ["Accounts", data.users, ROUTES.adminUsers.path],
    ["Accounts with an unconfirmed email", data.unverifiedUsers, ROUTES.adminUsers.path],
  ];
  return (
    <div className="space-y-6">
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map(([label, n, href]) => (
          <li key={label}>
            <Link href={href} className="block rounded-[12px] bg-surface-2 p-4 hover:bg-fill">
              <span className="block text-sm text-muted">{label}</span>
              <span className="text-3xl font-semibold text-ink tabular-nums">
                {n.toLocaleString("en-IE")}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <section>
        <h2 className="font-display text-xl text-ink">Latest run of each step</h2>
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr>
              <th className={th}>Step</th>
              <th className={th}>Run</th>
              <th className={th}>Status</th>
              <th className={th}>Started</th>
            </tr>
          </thead>
          <tbody>
            {data.lastRuns.map((r) => (
              <tr key={String(r.kind)} className="border-t border-line">
                <td className={td}>{String(r.kind)}</td>
                <td className={td}>{String(r.id)}</td>
                <td className={td}>{String(r.status)}</td>
                <td className={td}>{formatDateTime(String(r.started_at))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 font-mono text-xs text-muted">
          data version {data.dataVersion ?? "none"}
        </p>
      </section>
    </div>
  );
}

// --- ingest runs ---------------------------------------------------------------------------

const STEPS: [string, string][] = [
  ["aggregate", "Rebuild aggregates (2 min)"],
  ["enrich", "Reload stops, amenities and deprivation"],
  ["benchmarks", "Load the CSO price index (for estimates)"],
  ["gazetteer", "Rebuild the street gazetteer (8 min)"],
  ["geocode", "Geocode new properties (needs the geocoder)"],
  ["ppr", "Download and load the register"],
  ["monthly", "The whole monthly run, in order"],
];

function RunDetail({ id }: { id: number }) {
  const [data, setData] = useState<IngestRunDetail | null>(null);
  useEffect(() => {
    api.admin
      .run(id)
      .then(setData)
      .catch(() => {});
  }, [id]);
  if (!data)
    return (
      <p aria-busy className="text-muted">
        Loading…
      </p>
    );
  const confidence = data.stats.confidence as Record<string, number> | undefined;
  const totalPlaced = confidence ? Object.values(confidence).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="space-y-3 rounded-[10px] bg-surface-2 p-4 text-sm">
      {data.sourceUrl ? (
        <p className="break-all text-xs text-muted">Source: {data.sourceUrl}</p>
      ) : null}
      {confidence ? (
        <table>
          <caption className="text-left font-medium text-ink">
            Locations by precision after this run
          </caption>
          <tbody>
            {Object.entries(confidence).map(([k, n]) => (
              <tr key={k}>
                <td className="pr-4">{k.replace("_", " ")}</td>
                <td className="pr-4 text-right tabular-nums">{n.toLocaleString("en-IE")}</td>
                <td className="text-right tabular-nums text-muted">
                  {((n / totalPlaced) * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <details>
        <summary className="cursor-pointer text-accent">All statistics</summary>
        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs">
          {JSON.stringify(data.stats, null, 2)}
        </pre>
      </details>
      {data.rowErrors.length ? (
        <details open>
          <summary className="cursor-pointer text-accent">
            {data.rowErrors.length} rows that failed
          </summary>
          <ul className="mt-2 max-h-72 space-y-1 overflow-auto text-xs">
            {data.rowErrors.map((e) => (
              <li key={e.lineNo}>
                Line {e.lineNo}: {e.error} <code className="text-muted">{e.rawLine}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

export function IngestRuns() {
  const [kind, setKind] = useState("");
  const load = useCallback((page: number) => api.admin.runs(page, kind || undefined), [kind]);
  const runs = usePage(load, kind);
  const [open, setOpen] = useState<number | null>(null);
  const [step, setStep] = useState("aggregate");
  const [jobs, setJobs] = useState<AdminJob[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const refreshJobs = useCallback(() => {
    api.admin
      .jobs()
      .then(setJobs)
      .catch((e: unknown) => setMessage(`Jobs: ${messageOf(e)}`));
  }, []);
  useEffect(refreshJobs, [refreshJobs]);
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h2 className="font-display text-xl text-ink">Start a run</h2>
        <form
          className="flex flex-wrap items-end gap-2 text-sm"
          onSubmit={async (e) => {
            e.preventDefault();
            setMessage(null);
            try {
              const job = await api.admin.startRun(step);
              setMessage(`Queued: ${job.description ?? step}. The worker runs it next.`);
              refreshJobs();
            } catch (err) {
              setMessage(`Could not queue it: ${messageOf(err)}`);
            }
          }}
        >
          <label>
            <span className="block text-muted">Step</span>
            <select
              className="mt-0.5 px-2.5 py-1.5"
              value={step}
              onChange={(e) => setStep(e.target.value)}
            >
              {STEPS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary btn-sm">
            Queue
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refreshJobs}>
            Refresh jobs
          </button>
        </form>
        <p role="status" className="text-sm empty:hidden">
          {message ?? ""}
        </p>
        {jobs?.length ? (
          <ul className="space-y-1 text-sm">
            {jobs.map((j) => (
              <li key={j.id}>
                <span className="chip mr-2">{j.status}</span>
                {j.description} · queued {j.enqueuedAt ? formatDateTime(j.enqueuedAt) : "–"}
                {j.endedAt ? ` · ended ${formatDateTime(j.endedAt)}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="font-display text-xl text-ink">Runs</h2>
          <label className="text-sm">
            <span className="text-muted">Kind </span>
            <select
              className="px-2.5 py-1.5"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="">All</option>
              {["ppr", "geocode", "osm", "gtfs", "pobal", "boundaries", "aggregate"].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
        </div>
        <Problem text={runs.error} />
        {runs.data ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr>
                  <th className={th}>Run</th>
                  <th className={th}>Kind</th>
                  <th className={th}>Status</th>
                  <th className={th}>Started</th>
                  <th className={th}>Took</th>
                  <th className={th}>Read / loaded / failed</th>
                  <th className={th}>By</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.flatMap((r) => [
                  <tr key={r.id} className="border-t border-line">
                    <td className={td}>
                      <button
                        type="button"
                        className="text-accent underline"
                        aria-expanded={open === r.id}
                        onClick={() => setOpen(open === r.id ? null : r.id)}
                      >
                        {r.id}
                      </button>
                    </td>
                    <td className={td}>{r.kind}</td>
                    <td className={td}>{r.status}</td>
                    <td className={td}>{formatDateTime(r.startedAt)}</td>
                    <td className={td}>{duration(r)}</td>
                    <td className={`${td} tabular-nums`}>
                      {r.rowsRead.toLocaleString("en-IE")} /{" "}
                      {r.rowsInserted.toLocaleString("en-IE")} /{" "}
                      {r.rowsFailed.toLocaleString("en-IE")}
                    </td>
                    <td className={td}>{r.triggeredBy ?? "schedule or command"}</td>
                  </tr>,
                  open === r.id ? (
                    <tr key={`${r.id}-detail`}>
                      <td colSpan={7} className="pb-3">
                        <RunDetail id={r.id} />
                      </td>
                    </tr>
                  ) : null,
                ])}
              </tbody>
            </table>
            <Pager
              page={runs.page}
              total={runs.data.total}
              pageSize={runs.data.pageSize}
              onPage={runs.setPage}
            />
          </div>
        ) : (
          <p aria-busy className="text-muted">
            Loading…
          </p>
        )}
      </section>
    </div>
  );
}

// --- geocode review ------------------------------------------------------------------------

const QUEUES: [string, string][] = [
  ["conflict", "Far from their Eircode area"],
  ["low", "Only routing key or county"],
  ["locality", "Town or townland only"],
  ["locked", "Corrected by hand"],
];

function FixForm({ item, onDone }: { item: QueueItem; onDone: (text: string) => void }) {
  const [lat, setLat] = useState(item.lat?.toFixed(6) ?? "");
  const [lng, setLng] = useState(item.lng?.toFixed(6) ?? "");
  const [confidence, setConfidence] = useState<"exact" | "street" | "locality">("exact");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="grid gap-2 rounded-[10px] bg-surface-2 p-3 text-sm sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          const done = await api.admin.fixGeocode(item.id, {
            lat: Number(lat),
            lng: Number(lng),
            confidence,
            note,
          });
          onDone(
            `${item.address}: placed at ${confidence} precision and locked` +
              (done.inReportedCounty
                ? "."
                : ", but outside Co. " + countyName(item.county) + ": check it."),
          );
        } catch (err) {
          setError(messageOf(err));
        }
      }}
    >
      <label>
        Latitude
        <input
          className="mt-0.5 w-full px-2 py-1"
          inputMode="decimal"
          value={lat}
          onChange={(e) => setLat(e.target.value)}
          required
        />
      </label>
      <label>
        Longitude
        <input
          className="mt-0.5 w-full px-2 py-1"
          inputMode="decimal"
          value={lng}
          onChange={(e) => setLng(e.target.value)}
          required
        />
      </label>
      <label>
        Precision
        <select
          className="mt-0.5 w-full px-2 py-1"
          value={confidence}
          onChange={(e) => setConfidence(e.target.value as typeof confidence)}
        >
          <option value="exact">The house itself</option>
          <option value="street">Its street or estate</option>
          <option value="locality">Its town or townland</option>
        </select>
      </label>
      <label>
        Why (kept in the audit log)
        <input
          className="mt-0.5 w-full px-2 py-1"
          value={note}
          minLength={3}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
          required
        />
      </label>
      <p className="text-xs text-muted sm:col-span-2">
        Find the point on the{" "}
        <a
          className="underline"
          href={`${ROUTES.map.path}?lat=${lat}&lng=${lng}&z=17`}
          target="_blank"
          rel="noreferrer"
        >
          map
        </a>{" "}
        (its address bar shows lat and lng) or an official map. Never use a paid or restricted
        source.
      </p>
      {error ? (
        <p role="alert" className="sm:col-span-2">
          {error}
        </p>
      ) : null}
      <button type="submit" className="btn btn-primary btn-sm justify-self-start">
        Save and lock
      </button>
    </form>
  );
}

export function GeocodeQueue() {
  const [kind, setKind] = useState("conflict");
  const [county, setCounty] = useState("");
  const load = useCallback(
    (page: number) => api.admin.geocodeQueue(kind, page, county || undefined),
    [kind, county],
  );
  const list = usePage(load, `${kind}|${county}`);
  const [open, setOpen] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <fieldset className="flex flex-wrap gap-1">
          <legend className="sr-only">Queue</legend>
          {QUEUES.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className="rounded-full px-3 py-1.5 hover:bg-fill aria-pressed:bg-ink aria-pressed:text-surface"
            >
              {label}
            </button>
          ))}
        </fieldset>
        <label>
          <span className="text-muted">County </span>
          <select
            className="px-2.5 py-1.5"
            value={county}
            onChange={(e) => setCounty(e.target.value)}
          >
            <option value="">All</option>
            {COUNTIES.map((c) => (
              <option key={c} value={c}>
                {countyName(c)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p role="status" className="text-sm empty:hidden">
        {done ?? ""}
      </p>
      <p className="text-xs text-muted">
        A correction shows at once on the property page and hover card; the map and distances follow
        at the next aggregate and enrich runs.
      </p>
      <Problem text={list.error} />
      {list.data ? (
        <>
          <p className="text-sm text-muted">
            {list.data.total.toLocaleString("en-IE")} properties, most recently sold first.
          </p>
          <ul className="divide-y divide-line">
            {list.data.items.map((i) => (
              <li key={i.id} className="space-y-2 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 text-sm">
                    <Link className="font-medium text-ink underline" href={`/property/${i.id}`}>
                      {i.address}
                    </Link>
                    <p className="text-xs text-muted">
                      Co. {countyName(i.county)} · {i.method ?? "not placed"} · last sold{" "}
                      {i.latestSale ? formatDate(i.latestSale) : "–"} · {i.nSales} sales
                      {i.conflictM
                        ? ` · ${(i.conflictM / 1000).toFixed(1)} km from its Eircode area`
                        : ""}
                    </p>
                  </div>
                  <span className="flex items-center gap-2">
                    <ConfidenceChip confidence={i.confidence} />
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      aria-expanded={open === i.id}
                      onClick={() => setOpen(open === i.id ? null : i.id)}
                    >
                      Correct
                    </button>
                  </span>
                </div>
                {open === i.id ? (
                  <FixForm
                    item={i}
                    onDone={(text) => {
                      setDone(text);
                      setOpen(null);
                      list.reload();
                    }}
                  />
                ) : null}
              </li>
            ))}
          </ul>
          <Pager
            page={list.page}
            total={list.data.total}
            pageSize={list.data.pageSize}
            onPage={list.setPage}
          />
        </>
      ) : (
        <p aria-busy className="text-muted">
          Loading…
        </p>
      )}
    </div>
  );
}

// --- removal and correction requests -------------------------------------------------------

const REQUEST_LABEL: Record<string, string> = {
  suppress_display: "Stop showing the address",
  correct_location: "Correct the location",
  correct_details: "Correct a detail",
};

function Decide({ item, onDone }: { item: RemovalRequest; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const act = async (status: string) => {
    setError(null);
    try {
      await api.admin.decide(item.id, status, note || undefined);
      onDone();
    } catch (e) {
      setError(messageOf(e));
    }
  };
  return (
    <div className="space-y-2 text-sm">
      <label className="block">
        Note to the requester (emailed if they gave an address)
        <textarea
          className="mt-0.5 w-full px-2 py-1"
          rows={2}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        {item.status === "new" ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => act("in_review")}
          >
            Take into review
          </button>
        ) : null}
        <button type="button" className="btn btn-primary btn-sm" onClick={() => act("approved")}>
          {item.requestType === "suppress_display" && item.propertyId
            ? "Approve and hide the address"
            : "Approve"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => act("rejected")}>
          Reject
        </button>
      </div>
      {item.requestType === "correct_location" && item.propertyId ? (
        <p className="text-xs text-muted">
          Correct the location in{" "}
          <Link className="underline" href={ROUTES.adminGeocode.path}>
            geocode review
          </Link>
          , then approve.
        </p>
      ) : null}
    </div>
  );
}

export function RemovalRequests() {
  const [status, setStatus] = useState("open");
  const load = useCallback((page: number) => api.admin.removals(status, page), [status]);
  const list = usePage(load, status);
  return (
    <div className="space-y-4">
      <label className="text-sm">
        <span className="text-muted">Show </span>
        <select
          className="px-2.5 py-1.5"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="open">Open (new and in review)</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </label>
      <Problem text={list.error} />
      {list.data ? (
        list.data.items.length ? (
          <ul className="divide-y divide-line">
            {list.data.items.map((r) => (
              <li key={r.id} className="grid gap-3 py-4 sm:grid-cols-[1fr_18rem]">
                <div className="space-y-1 text-sm">
                  <p className="font-mono text-xs text-muted">
                    {r.reference} · {formatDateTime(r.createdAt)} · {r.status.replace("_", " ")}
                  </p>
                  <p className="font-medium text-ink">
                    {REQUEST_LABEL[r.requestType] ?? r.requestType}
                  </p>
                  <p>
                    {r.propertyId ? (
                      <Link className="underline" href={`/property/${r.propertyId}`}>
                        {r.propertyAddress}
                      </Link>
                    ) : (
                      r.submittedAddress
                    )}
                    {r.propertySuppressed ? " (hidden)" : ""}
                  </p>
                  <p className="text-muted">
                    From the {r.relationship}
                    {r.requesterEmail ? ` · ${r.requesterEmail}` : " · no email given"}
                  </p>
                  {r.reason ? <p className="whitespace-pre-line">{r.reason}</p> : null}
                  {r.decidedBy ? (
                    <p className="text-muted">
                      Decided by {r.decidedBy} {r.decidedAt ? formatDateTime(r.decidedAt) : ""}
                      {r.decisionNote ? `: ${r.decisionNote}` : ""}
                    </p>
                  ) : null}
                </div>
                {r.status === "new" || r.status === "in_review" ? (
                  <Decide item={r} onDone={list.reload} />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p>No requests here.</p>
        )
      ) : (
        <p aria-busy className="text-muted">
          Loading…
        </p>
      )}
      {list.data ? (
        <Pager
          page={list.page}
          total={list.data.total}
          pageSize={list.data.pageSize}
          onPage={list.setPage}
        />
      ) : null}
    </div>
  );
}

// --- users ---------------------------------------------------------------------------------

function RolesForm({ user, onDone }: { user: AdminUser; onDone: (u: AdminUser) => void }) {
  const [roles, setRoles] = useState<string[]>(user.roles.filter((r) => r !== "user"));
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-[10px] bg-surface-2 p-3 text-sm"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          onDone(await api.admin.changeUser(user.id, { roles: ["user", ...roles], password }));
        } catch (err) {
          setError(messageOf(err));
        }
      }}
    >
      {["pro", "admin"].map((r) => (
        <label key={r} className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={roles.includes(r)}
            onChange={(e) =>
              setRoles((xs) => (e.target.checked ? [...xs, r] : xs.filter((x) => x !== r)))
            }
          />
          {r}
        </label>
      ))}
      <label>
        Your password
        <input
          className="mt-0.5 block px-2 py-1"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      <button type="submit" className="btn btn-primary btn-sm">
        Change roles
      </button>
      {error ? (
        <p role="alert" className="w-full">
          {error}
        </p>
      ) : null}
    </form>
  );
}

export function Users() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const load = useCallback((page: number) => api.admin.users(query, page), [query]);
  const list = usePage(load, query);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState<Record<string, AdminUser>>({});
  return (
    <div className="space-y-4">
      <form
        className="flex gap-2"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <label className="sr-only" htmlFor="user-q">
          Email or name
        </label>
        <input
          id="user-q"
          className="w-72 px-2.5 py-1.5"
          placeholder="Email or name"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button type="submit" className="btn btn-secondary btn-sm">
          Find
        </button>
      </form>
      <Problem text={list.error ?? error} />
      {list.data ? (
        <>
          <ul className="divide-y divide-line">
            {list.data.items.map((u0) => {
              const u = changed[u0.id] ?? u0;
              return (
                <li key={u.id} className="space-y-2 py-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-ink">
                        {u.fullName} <span className="font-normal text-muted">{u.email}</span>
                      </p>
                      <p className="text-xs text-muted">
                        {u.roles.join(", ")} ·{" "}
                        {u.emailVerified ? "email confirmed" : "email not confirmed"} ·{" "}
                        {u.closedAt
                          ? `closed ${formatDate(u.closedAt.slice(0, 10))}`
                          : u.isActive
                            ? "active"
                            : "deactivated"}{" "}
                        · joined {formatDate(u.createdAt.slice(0, 10))}
                        {u.lastLoginAt ? ` · last sign-in ${formatDateTime(u.lastLoginAt)}` : ""}
                      </p>
                    </div>
                    <span className="flex gap-2">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={async () => {
                          setError(null);
                          try {
                            const next = await api.admin.changeUser(u.id, {
                              isActive: !u.isActive,
                            });
                            setChanged((c) => ({ ...c, [u.id]: next }));
                          } catch (e) {
                            setError(messageOf(e));
                          }
                        }}
                      >
                        {u.isActive ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        aria-expanded={open === u.id}
                        onClick={() => setOpen(open === u.id ? null : u.id)}
                      >
                        Roles
                      </button>
                    </span>
                  </div>
                  {open === u.id ? (
                    <RolesForm
                      user={u}
                      onDone={(next) => {
                        setChanged((c) => ({ ...c, [u.id]: next }));
                        setOpen(null);
                      }}
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
          <Pager
            page={list.page}
            total={list.data.total}
            pageSize={list.data.pageSize}
            onPage={list.setPage}
          />
        </>
      ) : (
        <p aria-busy className="text-muted">
          Loading…
        </p>
      )}
    </div>
  );
}

// --- audit log -----------------------------------------------------------------------------

export function AuditLog() {
  const [actor, setActor] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const key = JSON.stringify(filters);
  const load = useCallback(
    (page: number) => api.admin.audit(page, JSON.parse(key) as Record<string, string>),
    [key],
  );
  const list = usePage(load, key);
  return (
    <div className="space-y-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(actor.trim() ? { actor: actor.trim() } : {});
        }}
      >
        <label className="sr-only" htmlFor="audit-actor">
          Actor email
        </label>
        <input
          id="audit-actor"
          className="w-72 px-2.5 py-1.5"
          placeholder="Actor email"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
        <button type="submit" className="btn btn-secondary btn-sm">
          Filter
        </button>
      </form>
      <Problem text={list.error} />
      {list.data ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr>
                <th className={th}>When</th>
                <th className={th}>Who</th>
                <th className={th}>Action</th>
                <th className={th}>Target</th>
                <th className={th}>Change</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((a) => (
                <tr key={a.id} className="border-t border-line">
                  <td className={td}>{formatDateTime(a.createdAt)}</td>
                  <td className={td}>{a.actor ?? "command line or removed account"}</td>
                  <td className={td}>{a.action}</td>
                  <td className={`${td} break-all`}>
                    {a.targetKind} {a.targetId}
                  </td>
                  <td className={`${td} font-mono text-xs`}>
                    {a.before ? `${JSON.stringify(a.before)} → ` : ""}
                    {a.after ? JSON.stringify(a.after) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            page={list.page}
            total={list.data.total}
            pageSize={list.data.pageSize}
            onPage={list.setPage}
          />
        </div>
      ) : (
        <p aria-busy className="text-muted">
          Loading…
        </p>
      )}
    </div>
  );
}
