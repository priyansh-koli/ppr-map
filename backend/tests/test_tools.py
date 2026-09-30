"""The calculators and the rates behind them (D-015, D-048, R-10)."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import REPO_CONFIG_DIR
from app.services import rates as r


@pytest.fixture
def rates() -> r.Rates:
    return r.load_rates()


def test_every_rate_names_its_source_and_check_date(rates: r.Rates) -> None:
    for v in rates.vat_new_dwellings:
        assert v.source_url.startswith("https://www.revenue.ie/")
        assert v.verified_on >= date(2026, 9, 30)
    assert rates.stamp_duty_residential.source_url.startswith("https://www.revenue.ie/")
    assert rates.central_bank_mortgage_measures.source_url.startswith("https://www.centralbank.ie/")


def test_an_empty_value_refuses_to_load(tmp_path: Path) -> None:
    data = yaml.safe_load((REPO_CONFIG_DIR / "rates.yaml").read_text())
    data["central_bank_mortgage_measures"]["loan_to_value"]["first_time_buyer"] = None
    with pytest.raises(ValidationError):
        r.Rates.model_validate(data)


def test_stamp_duty_bands(rates: r.Rates) -> None:
    def duty(price: int) -> D:
        return r.stamp_duty(D(price), is_new=False, vat_inclusive=False, rates=rates).duty_eur

    assert duty(350_000) == D("3500.00")
    assert duty(1_000_000) == D("10000.00")
    assert duty(1_200_000) == D("14000.00")  # 1% of 1m + 2% of 200k
    assert duty(1_600_000) == D("26000.00")  # + 6% of the part over 1.5m


def test_new_homes_pay_duty_on_the_price_without_vat(rates: r.Rates) -> None:
    # Revenue's worked example: €400,000 including 13.5% VAT is €352,422.90 without it.
    res = r.stamp_duty(
        D(400_000), is_new=True, vat_inclusive=True, on=date(2026, 9, 30), rates=rates
    )
    assert res.consideration_eur == D("352422.90")
    assert res.vat_rate == D("0.135")
    assert res.duty_eur == D("3524.23")
    apartment = r.stamp_duty(
        D(400_000),
        is_new=True,
        vat_inclusive=True,
        dwelling="qualifying_apartment",
        on=date(2026, 9, 30),
        rates=rates,
    )
    assert apartment.vat_rate == D("0.09")
    assert apartment.consideration_eur == D("366972.47")


def test_vat_estimates_by_sale_date(rates: r.Rates) -> None:
    before = r.vat_estimates(D(300_000), date(2025, 10, 7), rates)
    assert before == [(D("0.135"), D("340500.00"), "any")]
    after = r.vat_estimates(D(300_000), date(2025, 10, 8), rates)
    assert after == [
        (D("0.135"), D("340500.00"), "any"),
        (D("0.09"), D("327000.00"), "qualifying_apartment"),
    ]
    # The 9% rate ends with 2030.
    assert len(r.vat_estimates(D(300_000), date(2031, 1, 1), rates)) == 1


def test_affordability_takes_the_lower_limit(rates: r.Rates) -> None:
    income_bound = r.affordability(
        D(60_000),
        second_income=D(40_000),
        buyer="first_time_buyer",
        deposit=D(45_000),
        term_years=30,
        rate_pct=D("3.9"),
        rates=rates,
    )
    assert income_bound.max_loan_by_income_eur == D(400_000)  # 4 x 100k
    assert income_bound.max_price_by_deposit_eur == D(450_000)  # 45k is 10%
    assert (income_bound.max_price_eur, income_bound.limited_by) == (D(445_000), "income")
    assert income_bound.monthly_repayment_eur == D("1886.67")

    deposit_bound = r.affordability(
        D(100_000), buyer="second_and_subsequent", deposit=D(20_000), term_years=25,
        rate_pct=None, rates=rates,
    )  # fmt: skip
    assert (deposit_bound.max_price_eur, deposit_bound.limited_by) == (D(200_000), "deposit")
    assert deposit_bound.loan_to_income == D("3.5")

    investor = r.affordability(
        D(10_000), buyer="buy_to_let", deposit=D(90_000), term_years=20, rate_pct=D(5),
        rates=rates,
    )  # fmt: skip
    assert investor.max_loan_by_income_eur is None  # not subject to the LTI limit
    assert investor.max_price_eur == D(300_000)  # 70% LTV


def test_repayment_formula() -> None:
    assert r.monthly_repayment(D(300_000), D(4), 30) == D("1432.25")
    assert r.monthly_repayment(D(120_000), D(0), 10) == D("1000.00")


def test_tools_endpoints(client: TestClient) -> None:
    body = client.get("/api/v1/tools/stamp-duty", params={"price": 400000, "isNew": True}).json()
    assert body["dutyEur"] == 3524.23 and body["considerationEur"] == 352422.9
    assert body["rulesVersion"] == "2026-09-30"
    assert {s["url"] for s in body["sources"]} >= {
        "https://www.revenue.ie/en/property/stamp-duty/property/stamp-duty-property/rates.aspx"
    }
    assert "not financial" in body["note"]

    a = client.get(
        "/api/v1/tools/affordability",
        params={"grossIncome": 55000, "deposit": 30000, "firstTimeBuyer": "false", "ratePct": 4},
    ).json()
    assert a["loanToIncome"] == 3.5 and a["maxPriceEur"] == 222500 and a["limitedBy"] == "income"
    assert a["monthlyRepaymentEur"] > 0

    assert client.get("/api/v1/tools/stamp-duty", params={"price": -5}).status_code == 422
    assert client.get("/api/v1/tools/affordability", params={"grossIncome": 1}).status_code == 422
    assert client.get("/api/v1/tools/rules").json()["sources"]


def test_missing_rates_are_a_503_not_a_guess(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ppr_config_dir", tmp_path)
    r.load_rates.cache_clear()
    try:
        res = client.get("/api/v1/tools/stamp-duty", params={"price": 300000})
        assert res.status_code == 503
    finally:
        monkeypatch.undo()
        r.load_rates.cache_clear()
