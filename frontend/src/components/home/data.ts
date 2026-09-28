"use client";

import { useEffect, useState } from "react";

import { api, type Overview, type PropertyListItem, STATIC_PREVIEW } from "@/lib/api/client";

/** One request for every home-page section that shows the national overview. */
let overview: Promise<Overview> | null = null;

export function useOverview(): { data: Overview | null; failed: boolean } {
  const [data, setData] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(STATIC_PREVIEW);
  useEffect(() => {
    if (STATIC_PREVIEW) return;
    let live = true;
    overview ??= api.overview();
    overview.then(
      (d) => live && setData(d),
      () => {
        overview = null;
        if (live) setFailed(true);
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return { data, failed };
}

export interface Town {
  name: string;
  /** west,south,east,north: small enough for the list endpoint (0.6° × 0.4° at most). */
  bbox: string;
}

/** The newest market sale in each box, as the map's list would show it. None is invented. */
export function useLatestSales(towns: Town[]): (PropertyListItem | null)[] | null {
  const [items, setItems] = useState<(PropertyListItem | null)[] | null>(null);
  useEffect(() => {
    if (STATIC_PREVIEW) return;
    const controller = new AbortController();
    Promise.all(
      towns.map((t) =>
        api
          .list(new URLSearchParams({ bbox: t.bbox, sort: "-date", pageSize: "1" }), {
            signal: controller.signal,
          })
          .then((r) => r.items[0] ?? null)
          .catch(() => null),
      ),
    ).then((found) => {
      if (!controller.signal.aborted) setItems(found);
    });
    return () => controller.abort();
  }, [towns]);
  return items;
}
