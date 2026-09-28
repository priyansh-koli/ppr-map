import { ForgotPasswordForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";
import { AuthShell } from "@/components/ui/page-header";

export const metadata = pageMetadata("forgotPassword");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.forgotPassword.title}
      lead="We email you a link to choose a new password. It works for one hour."
      windowTitle="account · reset password"
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}
