import { pageMetadata } from "@/components/placeholder-page";
import { StampDutyCalculator } from "@/components/tools/calculators";
import { PageHeader } from "@/components/ui/page-header";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("stampDuty");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="Tools"
        title={ROUTES.stampDuty.title}
        lead="Stamp duty on one home in Ireland at today's rates, worked out band by band. On a new home it is charged on the price without VAT."
      />
      <StampDutyCalculator />
    </div>
  );
}
