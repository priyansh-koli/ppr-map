import { Suspense } from "react";
import { VerifyEmail } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";
import { AuthShell } from "@/components/ui/page-header";

export const metadata = pageMetadata("verifyEmail");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.verifyEmail.title}
      lead="One click on the link we sent, and your address is confirmed."
      windowTitle="account · confirm email"
    >
      <Suspense fallback={<p aria-busy>Loading…</p>}>
        <VerifyEmail />
      </Suspense>
    </AuthShell>
  );
}
