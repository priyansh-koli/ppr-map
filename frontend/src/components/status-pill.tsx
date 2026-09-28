"use client";

import { useEffect, useState } from "react";

import { api, type Meta, STATIC_PREVIEW } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

/**
 * How recent the register is, in the header ("PPR data up to 18 Sep 2026"), with the
 * provisional window one tap away (ARCHITECTURE.md, data freshness).
 */
export function StatusPill() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState(STATIC_PREVIEW);

  useEffect(() => {
    if (STATIC_PREVIEW) return;
    const controller = new AbortController();
    api
      .meta({ signal: controller.signal })
      .then(setMeta)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, []);

  let short = "Checking the register…";
  let detail = "Checking how recent the data is…";
  if (meta) {
    short = `Data to ${formatDate(meta.pprMaxSaleDate)}`;
    detail = `Property Price Register data up to ${formatDate(meta.pprMaxSaleDate)}. Sales since ${formatDate(meta.provisionalFrom)} are provisional: late filings still arrive.`;
  } else if (failed) {
    short = STATIC_PREVIEW ? "Layout preview" : "Data date unavailable";
    detail = STATIC_PREVIEW
      ? "Preview of the page layout: the data server is not part of this preview."
      : "Data freshness is unavailable right now.";
  }
  return (
    <details className="group relative">
      <summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-full px-3 text-sm font-medium text-ink hover:bg-fill [&::-webkit-details-marker]:hidden">
        {/* A register page, not a live beacon: the data changes once a month. */}
        <svg
          viewBox="0 0 16 16"
          aria-hidden="true"
          className={`h-4 w-4 ${meta ? "text-accent" : "text-muted"}`}
        >
          <path
            d="M4 1.75h5.5L12.25 4.5v9.75H4Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
          <path
            d="M6 7.5h4.25M6 10h4.25"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
        <span className="hidden sm:inline">{short}</span>
        <span className="sr-only sm:hidden">{short}</span>
      </summary>
      <p className="window absolute right-0 top-11 z-50 w-72 p-4 text-sm text-ink-2 sm:w-80">
        {detail}
      </p>
    </details>
  );
}
