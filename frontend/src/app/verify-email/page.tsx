import { Suspense } from "react";

import { VerifyEmail } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("verifyEmail");

export default function Page() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">{ROUTES.verifyEmail.title}</h1>
      <Suspense fallback={<p aria-busy>Loading…</p>}>
        <VerifyEmail />
      </Suspense>
    </div>
  );
}
