import { Suspense } from "react";

import { UnsubscribeAlert } from "@/components/account/unsubscribe";
import { pageMetadata } from "@/components/placeholder-page";
import { AuthShell } from "@/components/ui/page-header";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("unsubscribe");

export default function Page() {
  return (
    <AuthShell title={ROUTES.unsubscribe.title} windowTitle="alerts · unsubscribe">
      <Suspense fallback={<p>Loading…</p>}>
        <UnsubscribeAlert />
      </Suspense>
    </AuthShell>
  );
}
