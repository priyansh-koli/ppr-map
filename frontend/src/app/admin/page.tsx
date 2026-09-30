import { AdminNav, RequireAdmin } from "@/components/admin/common";
import { Overview } from "@/components/admin/panels";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("admin");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-12">
      <PageHeader eyebrow="admin" title={ROUTES.admin.title} lead={ROUTES.admin.summary} />
      <AdminNav current={ROUTES.admin.path} />
      <Window title={`admin · ${ROUTES.admin.title.toLowerCase()}`} bodyClassName="p-5 sm:p-7">
        <RequireAdmin perm="admin:audit">
          <Overview />
        </RequireAdmin>
      </Window>
    </div>
  );
}
