import type { Metadata } from "next";

import { ROUTES, type RouteKey } from "@/lib/routes";

export function pageMetadata(key: RouteKey): Metadata {
  const route = ROUTES[key];
  // The home page sits in the root layout's segment, where `title.template` is not applied.
  const title = key === "home" ? { absolute: `${route.title} · PPR Map` } : route.title;
  return { title, description: route.summary };
}

const ACCESS_LABEL = {
  public: "Public",
  user: "Signed-in users",
  admin: "Admins only",
} as const;

export function PlaceholderPage({ routeKey, detail }: { routeKey: RouteKey; detail?: string }) {
  const route = ROUTES[routeKey];
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">{route.title}</h1>
      {detail ? <p className="mt-1 text-sm text-muted">{detail}</p> : null}
      <p className="mt-4 text-lg text-ink">{route.summary}</p>
      <dl className="mt-6 flex flex-wrap gap-3 text-sm">
        <div className="rounded-full bg-surface-2 px-3 py-1">
          <dt className="sr-only">Arrives in</dt>
          <dd>Arrives in Phase {route.phase}</dd>
        </div>
        <div className="rounded-full bg-surface-2 px-3 py-1">
          <dt className="sr-only">Access</dt>
          <dd>{ACCESS_LABEL[route.access]}</dd>
        </div>
      </dl>
    </div>
  );
}
