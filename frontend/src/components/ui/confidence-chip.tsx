import { CONFIDENCE_LABEL } from "@/lib/format";

/** Short names for the chip; the full label stays in the tooltip and on the property page. */
const SHORT: Record<string, string> = {
  exact: "Exact address",
  street: "Street",
  locality: "Town or townland",
  routing_key: "Eircode area",
  county: "County",
  unmatched: "Not located",
};

/**
 * How precisely a sale was placed, drawn the way the map draws it: a solid dot for a house or
 * street, a ring for a sale only placed at a town, townland or wider area.
 */
export function ConfidenceChip({ confidence }: { confidence: string }) {
  const solid = confidence === "exact" || confidence === "street";
  return (
    <span
      className="chip shrink-0"
      title={`Location: ${CONFIDENCE_LABEL[confidence] ?? confidence}`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-2.5 w-2.5 rounded-full ${
          solid ? "bg-[#1c5cab]" : "border-2 border-[#1c5cab] bg-transparent"
        }`}
      />
      <span className="sr-only">Location: </span>
      {SHORT[confidence] ?? confidence}
    </span>
  );
}
