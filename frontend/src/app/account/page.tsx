import { AccountSettings } from "@/components/account/settings";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("account");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="your account"
        title={ROUTES.account.title}
        lead="Your details, what you are looking for, and your data."
      />
      <Window title="account · settings" bodyClassName="p-5 sm:p-8">
        <RequireSignIn>
          <AccountSettings />
        </RequireSignIn>
      </Window>
    </div>
  );
}
