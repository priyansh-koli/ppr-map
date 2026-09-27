import { Suspense } from "react";

import { ResetPasswordForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("resetPassword");

export default function Page() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">
        {ROUTES.resetPassword.title}
      </h1>
      <Suspense fallback={<p aria-busy>Loading…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
