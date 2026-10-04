"""Stamp duty and mortgage affordability calculators (docs/api.md, Tools; D-048).

Information only, not financial advice: every answer says which rules it used, where they
come from and when they were checked."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require
from app.auth.permissions import Perm
from app.schemas.base import ApiModel, Money
from app.services import rates as r
from app.services.config_files import ConfigUnavailable

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require(Perm.TOOLS_USE))])

NOT_ADVICE = (
    "Information only, not financial or tax advice. Lenders decide individually, and your own "
    "circumstances or reliefs may change the figures."
)
MAX_PRICE = Decimal("100000000")


class Source(ApiModel):
    name: str
    url: str
    verified_on: date


class Rules(ApiModel):
    rules_version: str
    sources: list[Source]
    note: str = NOT_ADVICE


class DutyBandOut(ApiModel):
    from_eur: Money
    to_eur: Money | None
    rate: float
    duty_eur: Money


class StampDutyOut(Rules):
    price_eur: Money
    consideration_eur: Money
    vat_eur: Money
    vat_rate: float | None
    duty_eur: Money
    effective_rate: float
    bands: list[DutyBandOut]
    not_covered: str


class AffordabilityOut(Rules):
    income_eur: Money
    deposit_eur: Money
    loan_to_income: float | None
    loan_to_value: float
    max_loan_by_income_eur: Money | None
    max_price_by_deposit_eur: Money
    max_price_eur: Money
    loan_eur: Money
    limited_by: Literal["income", "deposit"]
    monthly_repayment_eur: Money | None
    stamp_duty_eur: Money
    allowance: float
    measures_note: str


def _rules() -> r.Rates:
    try:
        return r.load_rates()
    except ConfigUnavailable as exc:
        # A missing or unverified value must never turn into a figure (R-10).
        raise HTTPException(503, "The calculator's rates are not available") from exc


def _sources(rules: r.Rates, *which: str) -> list[Source]:
    out: list[Source] = []
    if "stamp_duty" in which:
        sd = rules.stamp_duty_residential
        out.append(
            Source(name="Revenue: Stamp Duty rates", url=sd.source_url, verified_on=sd.verified_on)
        )
    if "vat" in which:
        for v in rules.vat_new_dwellings:
            out.append(
                Source(
                    name=f"Revenue: VAT at {float(v.rate) * 100:g}%",
                    url=v.source_url,
                    verified_on=v.verified_on,
                )
            )
    if "measures" in which:
        m = rules.central_bank_mortgage_measures
        out.append(
            Source(
                name="Central Bank mortgage measures", url=m.source_url, verified_on=m.verified_on
            )
        )
    return out


@router.get("/rules", response_model=Rules)
def rules() -> Rules:
    """Which rules the calculators use, their sources and when they were checked."""
    data = _rules()
    return Rules(
        rules_version=data.rules_version, sources=_sources(data, "stamp_duty", "vat", "measures")
    )


@router.get("/stamp-duty", response_model=StampDutyOut)
def stamp_duty(
    price: Annotated[Decimal, Query(gt=0, le=MAX_PRICE, description="Price in euro")],
    is_new: Annotated[bool, Query(alias="isNew")] = False,
    vat_inclusive: Annotated[
        bool, Query(alias="vatInclusive", description="For a new home: the price includes VAT")
    ] = True,
    qualifying_apartment: Annotated[
        bool,
        Query(
            alias="qualifyingApartment",
            description="A new apartment in a block of 3+ with shared access (9% VAT since "
            "8 Oct 2025)",
        ),
    ] = False,
) -> StampDutyOut:
    """Stamp duty on one home at today's rates. On a new home it is charged on the price
    without VAT."""
    data = _rules()
    result = r.stamp_duty(
        price,
        is_new=is_new,
        vat_inclusive=vat_inclusive,
        dwelling="qualifying_apartment" if qualifying_apartment else "any",
        rates=data,
    )
    return StampDutyOut(
        rules_version=data.rules_version,
        sources=_sources(data, "stamp_duty", *(("vat",) if result.vat_rate else ())),
        price_eur=price,
        consideration_eur=result.consideration_eur,
        vat_eur=result.vat_eur,
        vat_rate=float(result.vat_rate) if result.vat_rate is not None else None,
        duty_eur=result.duty_eur,
        effective_rate=float(result.effective_rate),
        bands=[
            DutyBandOut(
                from_eur=b.from_eur, to_eur=b.to_eur, rate=float(b.rate), duty_eur=b.duty_eur
            )
            for b in result.bands
        ],
        not_covered=data.stamp_duty_residential.not_covered,
    )


@router.get("/affordability", response_model=AffordabilityOut)
def affordability(
    gross_income: Annotated[Decimal, Query(alias="grossIncome", ge=0, le=MAX_PRICE)],
    deposit: Annotated[Decimal, Query(ge=0, le=MAX_PRICE)],
    second_income: Annotated[Decimal, Query(alias="secondIncome", ge=0, le=MAX_PRICE)] = Decimal(0),
    buyer: Literal["first_time_buyer", "second_and_subsequent", "buy_to_let"] = "first_time_buyer",
    first_time_buyer: Annotated[
        bool | None, Query(alias="firstTimeBuyer", description="Shorthand for buyer")
    ] = None,
    term_years: Annotated[int, Query(alias="termYears", ge=5, le=35)] = 30,
    rate_pct: Annotated[
        Decimal | None, Query(alias="ratePct", ge=0, le=20, description="Your quoted rate")
    ] = None,
) -> AffordabilityOut:
    """The most the Central Bank measures allow you to borrow and spend: the lower of the
    income limit and the deposit limit. Lenders may lend less."""
    data = _rules()
    if first_time_buyer is not None:
        buyer = "first_time_buyer" if first_time_buyer else "second_and_subsequent"
    result = r.affordability(
        gross_income,
        second_income=second_income,
        buyer=buyer,
        deposit=deposit,
        term_years=term_years,
        rate_pct=rate_pct,
        rates=data,
    )
    m = data.central_bank_mortgage_measures
    return AffordabilityOut(
        rules_version=data.rules_version,
        sources=_sources(data, "measures", "stamp_duty"),
        income_eur=result.income_eur,
        deposit_eur=deposit,
        loan_to_income=float(result.loan_to_income) if result.loan_to_income is not None else None,
        loan_to_value=float(result.loan_to_value),
        max_loan_by_income_eur=result.max_loan_by_income_eur,
        max_price_by_deposit_eur=result.max_price_by_deposit_eur,
        max_price_eur=result.max_price_eur,
        loan_eur=result.loan_eur,
        limited_by=result.limited_by,
        monthly_repayment_eur=result.monthly_repayment_eur,
        stamp_duty_eur=result.stamp_duty_eur,
        allowance=float(result.allowance),
        measures_note=m.note,
    )
