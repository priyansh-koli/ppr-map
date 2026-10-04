"use client";

import { useEffect, useId, useRef, useState } from "react";

import { api, type Suggestion } from "@/lib/api/client";

const KIND_LABEL: Record<Suggestion["kind"], string> = {
  county: "County",
  settlement: "Town",
  electoral_division: "Electoral Division",
  townland: "Townland",
  routing_key: "Eircode area",
  property: "Address",
};
const DEBOUNCE_MS = 200;

/**
 * Type a town, townland, county, Eircode routing key (or "Dublin 8"), or an address, and
 * choose one: an ARIA combobox (arrow keys, Enter, Escape). Suggestions come from our own
 * database (D-006); nothing is sent anywhere else.
 */
export function PlaceSearch({
  onSelect,
  label = "Search a place or address",
  placeholder = "Town, townland, county, Eircode area (D08) or address",
  size = "md",
}: {
  onSelect: (s: Suggestion) => void;
  label?: string;
  placeholder?: string;
  size?: "md" | "lg";
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  // The text the suggestions shown answer: until the next answer arrives they are for what
  // was typed before, and Enter must not pick one of them (P1 #27).
  const [itemsFor, setItemsFor] = useState("");
  const request = useRef<AbortController | null>(null);
  // Enter pressed before the current text's suggestions came: take the first when they do.
  const enterPending = useRef(false);
  const chooseRef = useRef<(s: Suggestion) => void>(() => {});

  useEffect(() => {
    const q = text.trim();
    if (q.length < 2) {
      request.current?.abort();
      return;
    }
    const t = setTimeout(() => {
      request.current?.abort();
      const r = new AbortController();
      request.current = r;
      setStatus("loading");
      api
        .autocomplete(q, { signal: r.signal })
        .then((found) => {
          if (r.signal.aborted) return;
          if (enterPending.current) {
            enterPending.current = false;
            if (found[0]) {
              chooseRef.current(found[0]);
              return;
            }
          }
          setItems(found);
          setItemsFor(q);
          setActive(found.length ? 0 : -1);
          setStatus("idle");
        })
        .catch(() => {
          if (!r.signal.aborted) setStatus("error");
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => () => request.current?.abort(), []);

  const choose = (s: Suggestion) => {
    enterPending.current = false;
    onSelect(s);
    setText("");
    setItems([]);
    setItemsFor("");
    setOpen(false);
  };
  useEffect(() => {
    chooseRef.current = choose;
  });

  const listId = `${id}-list`;
  const optionId = (i: number) => `${id}-opt-${i}`;
  const showList = open && text.trim().length >= 2;
  return (
    <div className="relative">
      <label htmlFor={`${id}-input`} className="sr-only">
        {label}
      </label>
      <input
        id={`${id}-input`}
        type="search"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={showList && items.length > 0}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
        placeholder={placeholder}
        className={`w-full ${size === "lg" ? "px-4 py-3 text-base" : "px-3 py-2"}`}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          enterPending.current = false;
          setOpen(true);
          if (e.target.value.trim().length < 2) {
            setItems([]);
            setStatus("idle");
          }
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && items.length) {
            e.preventDefault();
            setOpen(true);
            setActive((a) => (a + 1) % items.length);
          } else if (e.key === "ArrowUp" && items.length) {
            e.preventDefault();
            setActive((a) => (a <= 0 ? items.length - 1 : a - 1));
          } else if (e.key === "Enter") {
            if (text.trim().length < 2) return;
            e.preventDefault();
            const pick = items[active >= 0 ? active : 0];
            if (itemsFor === text.trim() && pick) choose(pick);
            else if (itemsFor !== text.trim()) enterPending.current = true;
          } else if (e.key === "Escape") {
            enterPending.current = false;
            setOpen(false);
          }
        }}
      />
      <div aria-live="polite" className="sr-only">
        {showList && status === "idle" && text.trim().length >= 2
          ? `${items.length} ${items.length === 1 ? "suggestion" : "suggestions"}`
          : ""}
      </div>
      {showList ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Suggestions"
          className="window absolute inset-x-0 top-full z-30 mt-1 max-h-80 overflow-y-auto p-1 text-left text-sm"
        >
          {status === "error" ? (
            <li className="px-3 py-2 text-muted">Suggestions could not be loaded.</li>
          ) : null}
          {status !== "error" && items.length === 0 ? (
            <li className="px-3 py-2 text-muted">
              {status === "loading" ? "Looking…" : "No place or address matches that."}
            </li>
          ) : null}
          {items.map((s, i) => (
            <li
              key={`${s.kind}:${s.slug ?? s.propertyId ?? s.routingKey}`}
              id={optionId(i)}
              role="option"
              aria-selected={i === active}
              className="flex cursor-pointer items-baseline justify-between gap-3 rounded-[8px] px-3 py-2 aria-selected:bg-surface-2"
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(s)}
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-ink">{s.label}</span>
                {s.detail ? (
                  <span className="block truncate text-xs text-muted">{s.detail}</span>
                ) : null}
              </span>
              <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                {KIND_LABEL[s.kind]}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
