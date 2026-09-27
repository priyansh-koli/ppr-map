"use client";

import { useEffect, useState } from "react";

import { api, type Meta, STATIC_PREVIEW } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

/** "PPR data up to 18 Sep 2026", with the provisional window (ARCHITECTURE.md). */
export function FreshnessBanner() {
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

  let text = "Checking how recent the data is…";
  if (meta) {
    text = `Property Price Register data up to ${formatDate(meta.pprMaxSaleDate)}. Sales since ${formatDate(meta.provisionalFrom)} are provisional: late filings still arrive.`;
  } else if (failed) {
    text = STATIC_PREVIEW
      ? "Preview of the page layout: the data server is not part of this preview."
      : "Data freshness is unavailable right now.";
  }
  return <p className="bg-surface-2 px-4 py-1 text-center text-xs text-muted">{text}</p>;
}
