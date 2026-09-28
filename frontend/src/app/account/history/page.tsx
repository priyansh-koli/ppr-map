import { History } from "@/components/account/history";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("history");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="your account"
        title={ROUTES.history.title}
        lead="Property pages you opened in the last 12 months. You can turn this off."
      />
      <Window title="history · last 12 months" bodyClassName="p-5 sm:p-8">
        <RequireSignIn>
          <History />
        </RequireSignIn>
      </Window>
    </div>
  );
}
