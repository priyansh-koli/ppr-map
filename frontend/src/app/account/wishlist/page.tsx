import { Wishlist } from "@/components/account/wishlist";
import { RequireSignIn } from "@/components/auth/require-sign-in";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("wishlist");

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink">{ROUTES.wishlist.title}</h1>
      <RequireSignIn>
        <Wishlist />
      </RequireSignIn>
    </div>
  );
}
