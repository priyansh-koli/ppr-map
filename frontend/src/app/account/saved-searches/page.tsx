import { SavedSearches } from "@/components/account/saved-searches";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("savedSearches");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="your account"
        title={ROUTES.savedSearches.title}
        lead={ROUTES.savedSearches.summary}
      />
      <Window title="saved searches · alerts" bodyClassName="p-5 sm:p-8">
        <RequireSignIn>
          <SavedSearches />
        </RequireSignIn>
      </Window>
    </div>
  );
}
