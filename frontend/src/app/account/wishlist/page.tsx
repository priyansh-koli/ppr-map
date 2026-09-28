import { Wishlist } from "@/components/account/wishlist";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("wishlist");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="your account"
        title={ROUTES.wishlist.title}
        lead="Properties and areas you saved, with your notes. Only you can see them."
      />
      <Window title="wishlist · saved properties and areas" bodyClassName="p-5 sm:p-8">
        <RequireSignIn>
          <Wishlist />
        </RequireSignIn>
      </Window>
    </div>
  );
}
