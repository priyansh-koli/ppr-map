"""Stamp duty, VAT on new homes and the Central Bank mortgage measures (D-015, D-048, R-10).

Every figure comes from config/rates.yaml, where each one carries its official source and the
day it was checked. Loading refuses a missing or empty value, so a calculator can never run
on a guess. All money is Decimal.
"""

from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings

CENT = Decimal("0.01")
EURO = Decimal("1")
Buyer = Literal["first_time_buyer", "second_and_subsequent", "buy_to_let"]
DwellingType = Literal["any", "qualifying_apartment"]


class _Strict(BaseModel):
    # Every field is required and none may be null, so a half-filled file fails to load.
    model_config = ConfigDict(extra="ignore", frozen=True)


class VatRate(_Strict):
    applies_from: date
    applies_to: date | None
    dwelling_type: DwellingType
    rate: Decimal = Field(gt=0, lt=1)
    note: str
    source_url: str
    verified_on: date


class Band(_Strict):
    up_to: Decimal | None
    rate: Decimal = Field(ge=0, lt=1)


class StampDuty(_Strict):
    applies_from: date
    bands: list[Band] = Field(min_length=1)
    vat_exclusive_consideration: bool
    not_covered: str
    source_url: str
    verified_on: date


class ByBuyer(_Strict):
    first_time_buyer: Decimal
    second_and_subsequent: Decimal
    buy_to_let: Decimal


class LoanToIncome(_Strict):
    first_time_buyer: Decimal
    second_and_subsequent: Decimal
    buy_to_let: Decimal | None  # not subject to the LTI limit


class MortgageMeasures(_Strict):
    applies_from: date
    loan_to_income: LoanToIncome
    loan_to_value: ByBuyer
    allowances: ByBuyer
    note: str
    source_url: str
    verified_on: date


class Rates(_Strict):
    rules_version: str
    vat_new_dwellings: list[VatRate] = Field(min_length=1)
    stamp_duty_residential: StampDuty
    central_bank_mortgage_measures: MortgageMeasures


@lru_cache
def load_rates() -> Rates:
    path = get_settings().ppr_config_dir / "rates.yaml"
    return Rates.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


# --- VAT --------------------------------------------------------------------------------------


def vat_rate(on: date, dwelling: DwellingType = "any", rates: Rates | None = None) -> VatRate:
    """The rate for a new dwelling sold on `on`. A qualifying apartment gets its own rate
    while one applies; otherwise, and before then, the general rate."""
    table = (rates or load_rates()).vat_new_dwellings

    def live(r: VatRate) -> bool:
        return r.applies_from <= on and (r.applies_to is None or on <= r.applies_to)

    if dwelling == "qualifying_apartment":
        special = [r for r in table if r.dwelling_type == "qualifying_apartment" and live(r)]
        if special:
            return special[-1]
    general = [r for r in table if r.dwelling_type == "any" and live(r)]
    if not general:
        raise LookupError(f"no VAT rate for new dwellings on {on}")
    return general[-1]


def vat_estimates(
    price_ex_vat: Decimal, sold_on: date, rates: Rates | None = None
) -> list[tuple[Decimal, Decimal, DwellingType]]:
    """What a VAT-exclusive PPR price becomes with VAT: (rate, estimate, which dwellings).
    The PPR does not say whether a new home is an apartment, so when the rates differ both
    estimates are given (D-015)."""
    out = []
    general = vat_rate(sold_on, "any", rates)
    out.append((general.rate, _money(price_ex_vat * (1 + general.rate)), general.dwelling_type))
    apartment = vat_rate(sold_on, "qualifying_apartment", rates)
    if apartment.rate != general.rate:
        out.append(
            (apartment.rate, _money(price_ex_vat * (1 + apartment.rate)), "qualifying_apartment")
        )
    return out


# --- stamp duty -------------------------------------------------------------------------------


class DutyBand(BaseModel):
    from_eur: Decimal
    to_eur: Decimal | None
    rate: Decimal
    duty_eur: Decimal


class DutyResult(BaseModel):
    consideration_eur: Decimal
    vat_eur: Decimal
    vat_rate: Decimal | None
    duty_eur: Decimal
    effective_rate: Decimal
    bands: list[DutyBand]


def stamp_duty(
    price: Decimal,
    *,
    is_new: bool,
    vat_inclusive: bool,
    dwelling: DwellingType = "any",
    on: date | None = None,
    rates: Rates | None = None,
) -> DutyResult:
    """Stamp duty on one residential property. On a new home the duty is charged on the
    price without VAT; if the price given includes VAT, it is taken out first."""
    r = rates or load_rates()
    sd = r.stamp_duty_residential
    consideration, vat, rate = price, Decimal(0), None
    if is_new and vat_inclusive and sd.vat_exclusive_consideration:
        rate = vat_rate(on or date.today(), dwelling, r).rate
        # Truncated to the cent, as in Revenue's worked example (€400,000 / 1.135 = €352,422.90).
        consideration = (price / (1 + rate)).quantize(CENT, rounding=ROUND_DOWN)
        vat = price - consideration
    bands: list[DutyBand] = []
    lower = Decimal(0)
    for band in sd.bands:
        upper = band.up_to
        top = consideration if upper is None else min(consideration, upper)
        if top > lower:
            bands.append(
                DutyBand(
                    from_eur=lower, to_eur=upper, rate=band.rate, duty_eur=(top - lower) * band.rate
                )
            )
        if upper is None or consideration <= upper:
            break
        lower = upper
    duty = _money(sum((b.duty_eur for b in bands), Decimal(0)))
    return DutyResult(
        consideration_eur=consideration,
        vat_eur=vat,
        vat_rate=rate,
        duty_eur=duty,
        effective_rate=(
            (duty / consideration).quantize(Decimal("0.0001")) if consideration else Decimal(0)
        ),
        bands=[b.model_copy(update={"duty_eur": _money(b.duty_eur)}) for b in bands],
    )


# --- affordability ----------------------------------------------------------------------------


class Affordability(BaseModel):
    income_eur: Decimal
    loan_to_income: Decimal | None
    loan_to_value: Decimal
    max_loan_by_income_eur: Decimal | None
    max_price_by_deposit_eur: Decimal
    max_price_eur: Decimal
    loan_eur: Decimal
    limited_by: Literal["income", "deposit"]
    monthly_repayment_eur: Decimal | None
    stamp_duty_eur: Decimal
    allowance: Decimal


def monthly_repayment(loan: Decimal, annual_rate_pct: Decimal, years: int) -> Decimal:
    """An ordinary repayment (annuity) mortgage, interest charged monthly."""
    months = years * 12
    if loan <= 0:
        return Decimal(0)
    r = annual_rate_pct / Decimal(1200)
    if r == 0:
        return _money(loan / months)
    return _money(loan * r / (1 - (1 + r) ** -months))


def affordability(
    gross_income: Decimal,
    *,
    buyer: Buyer,
    deposit: Decimal,
    term_years: int,
    rate_pct: Decimal | None,
    second_income: Decimal = Decimal(0),
    rates: Rates | None = None,
) -> Affordability:
    """The most the Central Bank measures allow: the lower of the income limit (LTI times gross
    income, plus the deposit) and the deposit limit (deposit / (1 - LTV)). Lenders may lend
    less, and each can go above the limits for a small share of its lending."""
    m = (rates or load_rates()).central_bank_mortgage_measures
    income = gross_income + second_income
    lti = getattr(m.loan_to_income, buyer)
    ltv = getattr(m.loan_to_value, buyer)
    by_deposit = (deposit / (1 - ltv)).quantize(EURO, rounding=ROUND_DOWN)
    by_income = None if lti is None else (income * lti).quantize(EURO, rounding=ROUND_DOWN)
    limited: Literal["income", "deposit"] = "deposit"
    price = by_deposit
    if by_income is not None and by_income + deposit < by_deposit:
        price, limited = by_income + deposit, "income"
    loan = price - deposit
    return Affordability(
        income_eur=income,
        loan_to_income=lti,
        loan_to_value=ltv,
        max_loan_by_income_eur=by_income,
        max_price_by_deposit_eur=by_deposit,
        max_price_eur=price,
        loan_eur=loan,
        limited_by=limited,
        monthly_repayment_eur=(
            monthly_repayment(loan, rate_pct, term_years) if rate_pct is not None else None
        ),
        stamp_duty_eur=stamp_duty(price, is_new=False, vat_inclusive=False, rates=rates).duty_eur,
        allowance=getattr(m.allowances, buyer),
    )
