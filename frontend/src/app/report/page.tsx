import { Suspense } from "react";

import { pageMetadata } from "@/components/placeholder-page";
import { ReportForm } from "@/components/report/report-form";
import { AuthShell } from "@/components/ui/page-header";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("report");

export default function Page() {
  return (
    <AuthShell
      title={ROUTES.report.title}
      lead={ROUTES.report.summary}
      windowTitle="request · correction or removal"
      wide
    >
      <Suspense fallback={<p>Loading…</p>}>
        <ReportForm />
      </Suspense>
    </AuthShell>
  );
}
