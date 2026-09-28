import Link from "next/link";
import { LoginForm } from "@/components/account/auth-forms";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";
import { AuthShell } from "@/components/ui/page-header";

export const metadata = pageMetadata("login");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.login.title}
      lead="Save properties, compare them side by side, and keep a history of what you looked at."
      windowTitle="account · sign in"
      footnote={
        <>
          Passwords are stored as argon2 hashes, never as text ·{" "}
          <Link className="underline" href={ROUTES.privacy.path}>
            what is kept
          </Link>
        </>
      }
    >
      <LoginForm />
    </AuthShell>
  );
}
