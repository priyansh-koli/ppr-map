import { Suspense } from "react";
import { ResetPasswordForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";
import { AuthShell } from "@/components/ui/page-header";

export const metadata = pageMetadata("resetPassword");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.resetPassword.title}
      lead="Choose a new password. Every other device is signed out."
      windowTitle="account · new password"
    >
      <Suspense fallback={<p aria-busy>Loading…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
