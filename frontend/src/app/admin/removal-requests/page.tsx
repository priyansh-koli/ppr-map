import { AdminNav, RequireAdmin } from "@/components/admin/common";
import { RemovalRequests } from "@/components/admin/panels";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("adminRemovals");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-12">
      <PageHeader
        eyebrow="admin"
        title={ROUTES.adminRemovals.title}
        lead={ROUTES.adminRemovals.summary}
      />
      <AdminNav current={ROUTES.adminRemovals.path} />
      <Window
        title={`admin · ${ROUTES.adminRemovals.title.toLowerCase()}`}
        bodyClassName="p-5 sm:p-7"
      >
        <RequireAdmin perm="admin:removals">
          <RemovalRequests />
        </RequireAdmin>
      </Window>
    </div>
  );
}
