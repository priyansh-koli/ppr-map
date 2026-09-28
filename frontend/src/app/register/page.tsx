import { RegisterForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";
import { AuthShell } from "@/components/ui/page-header";

export const metadata = pageMetadata("register");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.register.title}
      lead="Free. Your saved properties, notes and history stay private to your account."
      windowTitle="account · new"
      wide
    >
      <RegisterForm />
    </AuthShell>
  );
}
