"use client";

import { useEffect, useId, useState } from "react";

import { Window } from "@/components/ui/window";
import { api, ApiError, type Rules, STATIC_PREVIEW } from "@/lib/api/client";
import { formatDate, formatEur, formatEurCents, formatRate } from "@/lib/format";

const DEBOUNCE_MS = 300;
const input = "mt-1 w-full px-3 py-2";

type Answer<T> = { key: string; data?: T; error?: string };

/** Fetch `load(query)` a moment after the inputs settle; the answer says which query it is for. */
function useCalculation<T>(
  query: URLSearchParams | null,
  load: (q: URLSearchParams, init: RequestInit) => Promise<T>,
) {
  const key = query?.toString() ?? "";
  const [answer, setAnswer] = useState<Answer<T>>({ key: "" });
  useEffect(() => {
    if (!key || STATIC_PREVIEW) return;
    const request = new AbortController();
    const t = setTimeout(() => {
      load(new URLSearchParams(key), { signal: request.signal })
        .then((data) => setAnswer({ key, data }))
        .catch((e: unknown) => {
          if (request.signal.aborted) return;
          setAnswer({
            key,
            error:
              e instanceof ApiError && e.status === 503
                ? "The rates are not available right now, so nothing is calculated."
                : e instanceof ApiError && e.status === 422
                  ? "Check the figures you entered."
                  : "The calculator could not be reached.",
          });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(t);
      request.abort();
    };
  }, [key, load]);
  return { ...answer, stale: answer.key !== key };
}

function Euros({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 mt-0.5 -translate-y-1/2 text-muted">
          €
        </span>
        <input
          id={id}
          className={`${input} pl-7 tabular-nums`}
          inputMode="numeric"
          type="number"
          min={0}
          step={1000}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={hint ? `${id}-hint` : undefined}
        />
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

const amount = (v: string) => (v.trim() !== "" && Number(v) >= 0 ? String(Number(v)) : null);

/** Where the figures come from and when they were last checked. */
export function RulesNote({ rules }: { rules: Rules }) {
  return (
    <div className="space-y-2 text-xs text-muted">
      <p>{rules.note}</p>
      <ul className="space-y-1">
        {rules.sources.map((s) => (
          <li key={s.url + s.name}>
            <a className="prose-link" href={s.url} rel="noreferrer">
              {s.name}
            </a>
            , checked {formatDate(s.verifiedOn)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Status({ stale, error }: { stale: boolean; error?: string }) {
  if (error && !stale)
    return (
      <p role="alert" className="text-sm text-ink">
        {error}
      </p>
    );
  return null;
}

export function StampDutyCalculator() {
  const [price, setPrice] = useState("400000");
  const [isNew, setIsNew] = useState(false);
  const [vatInclusive, setVatInclusive] = useState(true);
  const [apartment, setApartment] = useState(false);
  const p = amount(price);
  const query =
    p && Number(p) > 0
      ? new URLSearchParams({
          price: p,
          isNew: String(isNew),
          vatInclusive: String(vatInclusive),
          qualifyingApartment: String(isNew && apartment),
        })
      : null;
  const { data, error, stale } = useCalculation(query, api.stampDuty);
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
      <Window title="stamp duty · your purchase" bodyClassName="space-y-4 p-5 sm:p-6">
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <Euros label="Price" value={price} onChange={setPrice} />
          <fieldset className="space-y-2 text-sm">
            <legend className="font-medium text-ink">The home is</legend>
            <label className="flex items-center gap-2">
              <input type="radio" name="new" checked={!isNew} onChange={() => setIsNew(false)} />
              Second-hand
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="new" checked={isNew} onChange={() => setIsNew(true)} />
              New, bought from a builder or developer
            </label>
          </fieldset>
          {isNew ? (
            <fieldset className="space-y-2 text-sm">
              <legend className="font-medium text-ink">For a new home</legend>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={vatInclusive}
                  onChange={(e) => setVatInclusive(e.target.checked)}
                />
                The price includes VAT (stamp duty is charged on the price without it)
              </label>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={apartment}
                  onChange={(e) => setApartment(e.target.checked)}
                  disabled={!vatInclusive}
                />
                An apartment in a block of three or more with a shared entrance (9% VAT since 8
                October 2025)
              </label>
            </fieldset>
          ) : null}
        </form>
      </Window>
      <Window
        title="stamp duty · result"
        bodyClassName="space-y-4 p-5 sm:p-6"
        className={stale && data ? "opacity-70" : undefined}
      >
        <Status stale={stale} error={error} />
        {!query ? <p className="text-sm text-muted">Enter a price above zero.</p> : null}
        {data ? (
          <>
            <div aria-live="polite">
              <p className="text-sm text-ink-2">Stamp duty</p>
              <p className="text-5xl font-semibold tracking-[-0.02em] text-ink tabular-nums">
                {formatEurCents(data.dutyEur)}
              </p>
              <p className="mt-1 text-sm text-muted">
                {formatRate(data.effectiveRate)} of {formatEur(data.considerationEur)}
                {data.vatRate !== null && data.vatRate !== undefined
                  ? `, the price without ${formatRate(data.vatRate)} VAT (${formatEur(data.vatEur)})`
                  : ""}
              </p>
            </div>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">How the duty is made up</caption>
              <thead>
                <tr className="text-muted">
                  <th scope="col" className="py-1.5 font-medium">
                    Part of the price
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Rate
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Duty
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.bands.map((b) => (
                  <tr key={b.fromEur} className="border-t border-line">
                    <td className="py-1.5">
                      {b.toEur === null || b.toEur === undefined
                        ? `Over ${formatEur(b.fromEur)}`
                        : `${formatEur(b.fromEur)} to ${formatEur(b.toEur)}`}
                    </td>
                    <td className="py-1.5 text-right">{formatRate(b.rate)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatEurCents(b.dutyEur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-muted">Not covered: {data.notCovered}</p>
            <RulesNote rules={data} />
          </>
        ) : null}
      </Window>
    </div>
  );
}

type Buyer = "first_time_buyer" | "second_and_subsequent" | "buy_to_let";
const BUYERS: [Buyer, string][] = [
  ["first_time_buyer", "First-time buyer"],
  ["second_and_subsequent", "Moving home (second and subsequent buyer)"],
  ["buy_to_let", "Buying to let"],
];

export function AffordabilityCalculator() {
  const [income, setIncome] = useState("60000");
  const [second, setSecond] = useState("");
  const [deposit, setDeposit] = useState("40000");
  const [buyer, setBuyer] = useState<Buyer>("first_time_buyer");
  const [term, setTerm] = useState("30");
  const [rate, setRate] = useState("");
  const g = amount(income);
  const d = amount(deposit);
  const query =
    g !== null && d !== null
      ? new URLSearchParams({
          grossIncome: g,
          deposit: d,
          buyer,
          termYears: term,
          ...(amount(second) ? { secondIncome: amount(second) as string } : {}),
          ...(rate.trim() && Number(rate) >= 0 && Number(rate) <= 20 ? { ratePct: rate } : {}),
        })
      : null;
  const { data, error, stale } = useCalculation(query, api.affordability);
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
      <Window title="affordability · your figures" bodyClassName="p-5 sm:p-6">
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <fieldset className="space-y-2 text-sm">
            <legend className="font-medium text-ink">You are</legend>
            {BUYERS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="buyer"
                  checked={buyer === value}
                  onChange={() => setBuyer(value)}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <Euros
            label="Gross yearly income"
            value={income}
            onChange={setIncome}
            hint="Before tax."
          />
          <Euros
            label="Second applicant's gross income"
            value={second}
            onChange={setSecond}
            hint="Optional: leave empty for a single applicant."
          />
          <Euros label="Deposit you have saved" value={deposit} onChange={setDeposit} />
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium text-ink">
              Term (years)
              <input
                className={input}
                type="number"
                min={5}
                max={35}
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
            </label>
            <label className="block text-sm font-medium text-ink">
              Interest rate (%)
              <input
                className={input}
                type="number"
                min={0}
                max={20}
                step={0.05}
                placeholder="Your quote"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            </label>
          </div>
          <p className="text-xs text-muted">
            We do not suggest an interest rate: enter one a lender quoted you to see a monthly
            repayment.
          </p>
        </form>
      </Window>
      <Window
        title="affordability · Central Bank limits"
        bodyClassName="space-y-4 p-5 sm:p-6"
        className={stale && data ? "opacity-70" : undefined}
      >
        <Status stale={stale} error={error} />
        {data ? (
          <>
            <div aria-live="polite">
              <p className="text-sm text-ink-2">The most the rules allow you to spend</p>
              <p className="text-5xl font-semibold tracking-[-0.02em] text-ink tabular-nums">
                {formatEur(data.maxPriceEur)}
              </p>
              <p className="mt-1 text-sm text-muted">
                A mortgage of {formatEur(data.loanEur)} plus your {formatEur(data.depositEur)}{" "}
                deposit, limited by your{" "}
                <strong className="font-semibold text-ink">{data.limitedBy}</strong>.
              </p>
            </div>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="rounded-[10px] bg-surface-2 px-4 py-3">
                <dt className="text-muted">Income limit</dt>
                <dd className="mt-0.5 font-medium text-ink">
                  {data.maxLoanByIncomeEur !== null && data.maxLoanByIncomeEur !== undefined
                    ? `${formatEur(data.maxLoanByIncomeEur)} (${data.loanToIncome} × ${formatEur(data.incomeEur)})`
                    : "Buy-to-let loans have no income limit"}
                </dd>
              </div>
              <div className="rounded-[10px] bg-surface-2 px-4 py-3">
                <dt className="text-muted">Deposit limit</dt>
                <dd className="mt-0.5 font-medium text-ink">
                  Price up to {formatEur(data.maxPriceByDepositEur)} (loan at most{" "}
                  {formatRate(data.loanToValue)} of the price)
                </dd>
              </div>
              <div className="rounded-[10px] bg-surface-2 px-4 py-3">
                <dt className="text-muted">Monthly repayment</dt>
                <dd className="mt-0.5 font-medium text-ink">
                  {data.monthlyRepaymentEur !== null && data.monthlyRepaymentEur !== undefined
                    ? `${formatEur(data.monthlyRepaymentEur)} over ${term} years`
                    : "Enter your quoted rate"}
                </dd>
              </div>
              <div className="rounded-[10px] bg-surface-2 px-4 py-3">
                <dt className="text-muted">Stamp duty at that price</dt>
                <dd className="mt-0.5 font-medium text-ink">
                  {formatEur(data.stampDutyEur)} (second-hand home)
                </dd>
              </div>
            </dl>
            <p className="text-xs text-muted">
              Lenders may lend less, and each may lend above these limits to{" "}
              {formatRate(data.allowance)} of its borrowers in a year. {data.measuresNote}
            </p>
            <RulesNote rules={data} />
          </>
        ) : null}
      </Window>
    </div>
  );
}

/** The tools index: what each calculator uses, and when it was checked. */
export function ToolsRules() {
  const [rules, setRules] = useState<Rules | null>(null);
  useEffect(() => {
    if (STATIC_PREVIEW) return;
    api
      .rules()
      .then(setRules)
      .catch(() => {});
  }, []);
  return rules ? <RulesNote rules={rules} /> : null;
}
