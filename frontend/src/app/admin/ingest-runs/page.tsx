import { AdminNav, RequireAdmin } from "@/components/admin/common";
import { IngestRuns } from "@/components/admin/panels";
import { pageMetadata } from "@/components/placeholder-page";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("adminIngestRuns");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-12">
      <PageHeader
        eyebrow="admin"
        title={ROUTES.adminIngestRuns.title}
        lead={ROUTES.adminIngestRuns.summary}
      />
      <AdminNav current={ROUTES.adminIngestRuns.path} />
      <Window
        title={`admin · ${ROUTES.adminIngestRuns.title.toLowerCase()}`}
        bodyClassName="p-5 sm:p-7"
      >
        <RequireAdmin perm="admin:ingest">
          <IngestRuns />
        </RequireAdmin>
      </Window>
    </div>
  );
}
