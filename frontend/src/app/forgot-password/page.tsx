import { ForgotPasswordForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("forgotPassword");

export default function Page() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">
        {ROUTES.forgotPassword.title}
      </h1>
      <ForgotPasswordForm />
    </div>
  );
}
