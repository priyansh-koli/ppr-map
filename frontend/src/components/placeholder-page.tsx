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

/**
 * A page made from register data, in the static preview (D-034, D-056): there is no API to
 * render it from, so it shows its header and says why the rest is missing.
 */
export function StaticPreviewPage({ routeKey, detail }: { routeKey: RouteKey; detail?: string }) {
  const route = ROUTES[routeKey];
  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-12 sm:py-16">
      <PageHeader eyebrow={detail} title={route.title} lead={route.summary} />
      <Window title="layout preview" bodyClassName="p-5 sm:p-6">
        <p className="font-display text-2xl italic leading-snug text-ink">
          This page is made from the register data, and the data server is not part of this preview.
        </p>
        <p className="mt-5">
          <Link href={ROUTES.sources.path} className="btn btn-secondary btn-sm">
            Read where the data comes from
          </Link>
        </p>
      </Window>
    </div>
  );
}
