import { Suspense } from "react";

import { Compare } from "@/components/account/compare";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("compare");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="your account"
        title={ROUTES.compare.title}
        lead="Up to four saved properties, side by side."
      />
      <Window title="wishlist · side by side" bodyClassName="p-5 sm:p-8">
        <RequireSignIn>
          <Suspense fallback={<p aria-busy>Loading…</p>}>
            <Compare />
          </Suspense>
        </RequireSignIn>
      </Window>
    </div>
  );
}
