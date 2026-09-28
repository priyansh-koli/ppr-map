import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";

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
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-12 sm:py-16">
      <PageHeader eyebrow={detail} title={route.title} lead={route.summary} />
      <Window title={`roadmap · phase ${route.phase}`} bodyClassName="p-5 sm:p-6">
        <p className="font-hand text-2xl leading-snug text-ink">
          Not built yet: this page arrives in Phase {route.phase}.
        </p>
        <dl className="mt-4 flex flex-wrap gap-2 text-sm">
          <div className="chip">
            <dt className="sr-only">Arrives in</dt>
            <dd>Arrives in Phase {route.phase}</dd>
          </div>
          <div className="chip">
            <dt className="sr-only">Access</dt>
            <dd>{ACCESS_LABEL[route.access]}</dd>
          </div>
        </dl>
        <p className="mt-5">
          <Link href={ROUTES.map.path} className="btn btn-secondary btn-sm">
            Meanwhile, open the map
          </Link>
        </p>
      </Window>
    </div>
  );
}
