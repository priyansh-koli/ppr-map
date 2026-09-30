import { pageMetadata } from "@/components/placeholder-page";
import { AffordabilityCalculator } from "@/components/tools/calculators";
import { PageHeader } from "@/components/ui/page-header";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("affordability");

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-12">
      <PageHeader
        eyebrow="Tools"
        title={ROUTES.affordability.title}
        lead="The most the Central Bank's mortgage measures let you borrow and spend: the lower of the limit set by your income and the limit set by your deposit."
      />
      <AffordabilityCalculator />
    </div>
  );
}
