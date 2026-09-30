import { Suspense } from "react";

import { pageMetadata } from "@/components/placeholder-page";
import { SearchPage } from "@/components/search/search-page";

export const metadata = pageMetadata("search");

export default function Page() {
  // The search lives in the URL; reading it needs a Suspense boundary for the static build.
  return (
    <Suspense fallback={<p className="mx-auto max-w-7xl px-4 py-10 text-muted">Loading search…</p>}>
      <SearchPage />
    </Suspense>
  );
}
