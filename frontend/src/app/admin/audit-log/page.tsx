import { AdminNav, RequireAdmin } from "@/components/admin/common";
import { AuditLog } from "@/components/admin/panels";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("adminAudit");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-12">
      <PageHeader
        eyebrow="admin"
        title={ROUTES.adminAudit.title}
        lead={ROUTES.adminAudit.summary}
      />
      <AdminNav current={ROUTES.adminAudit.path} />
      <Window title={`admin · ${ROUTES.adminAudit.title.toLowerCase()}`} bodyClassName="p-5 sm:p-7">
        <RequireAdmin perm="admin:audit">
          <AuditLog />
        </RequireAdmin>
      </Window>
    </div>
  );
}
