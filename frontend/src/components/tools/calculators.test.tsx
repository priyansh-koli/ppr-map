import { fireEvent, render, screen } from "@testing-library/react";

import type { Affordability, StampDuty } from "@/lib/api/client";
import { mockApi } from "@/test-fixtures/api";

import { AffordabilityCalculator, StampDutyCalculator } from "./calculators";

afterEach(() => vi.unstubAllGlobals());

const RULES = {
  rulesVersion: "2026-09-30",
  note: "Information only, not financial or tax advice.",
  sources: [
    {
      name: "Revenue: Stamp Duty rates",
      url: "https://www.revenue.ie/en/property/stamp-duty/property/stamp-duty-property/rates.aspx",
      verifiedOn: "2026-09-30",
    },
  ],
};

const DUTY: StampDuty = {
  ...RULES,
  priceEur: 400000,
  considerationEur: 352422.9,
  vatEur: 47577.1,
  vatRate: 0.135,
  dutyEur: 3524.23,
  effectiveRate: 0.01,
  bands: [{ fromEur: 0, toEur: 1000000, rate: 0.01, dutyEur: 3524.23 }],
  notCovered: "Three or more apartments in one block.",
};

describe("StampDutyCalculator", () => {
  it("takes VAT out of a new home's price and shows each band", async () => {
    const { fetch } = mockApi({ "GET /tools/stamp-duty": () => [200, DUTY] });
    render(<StampDutyCalculator />);
    fireEvent.click(screen.getByLabelText("New, bought from a builder or developer"));
    expect(await screen.findAllByText("€3,524.23")).toHaveLength(2); // the total and its band
    expect(screen.getByText(/the price without 13.5% VAT/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "€0 to €1,000,000" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revenue: Stamp Duty rates" })).toHaveAttribute(
      "href",
      RULES.sources[0]?.url,
    );
    const last = String(fetch.mock.calls.at(-1)?.[0]);
    expect(last).toContain("price=400000&isNew=true&vatInclusive=true");
  });

  it("says so, rather than guessing, when the rates are unavailable", async () => {
    mockApi({ "GET /tools/stamp-duty": () => [503, { title: "Service Unavailable" }] });
    render(<StampDutyCalculator />);
    expect(await screen.findByRole("alert")).toHaveTextContent("nothing is calculated");
  });
});

describe("AffordabilityCalculator", () => {
  it("shows which limit applies, and a repayment only for a quoted rate", async () => {
    const result: Affordability = {
      ...RULES,
      incomeEur: 60000,
      depositEur: 40000,
      loanToIncome: 4,
      loanToValue: 0.9,
      maxLoanByIncomeEur: 240000,
      maxPriceByDepositEur: 400000,
      maxPriceEur: 280000,
      loanEur: 240000,
      limitedBy: "income",
      monthlyRepaymentEur: null,
      stampDutyEur: 2800,
      allowance: 0.15,
      measuresNote: "Lenders decide individually.",
    };
    mockApi({ "GET /tools/affordability": () => [200, result] });
    render(<AffordabilityCalculator />);
    expect(await screen.findByText("€280,000")).toBeInTheDocument();
    expect(screen.getByText("income")).toBeInTheDocument();
    expect(screen.getByText("Enter your quoted rate")).toBeInTheDocument();
    expect(screen.getByText(/€240,000 \(4 × €60,000\)/)).toBeInTheDocument();
  });
});
