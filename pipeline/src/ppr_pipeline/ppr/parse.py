"""Parse PPR-ALL.csv (cp1252) into typed rows, keeping every raw field (D-001, D-002)."""

import csv
import hashlib
import io
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import County, SizeBand

ENCODING = "cp1252"
HEADER = [
    "Date of Sale (dd/mm/yyyy)",
    "Address",
    "County",
    "Eircode",
    "Price (€)",
    "Not Full Market Price",
    "VAT Exclusive",
    "Description of Property",
    "Property Size Description",
]
PRICE_RE = re.compile(r"^€([\d,]+\.\d{2})$")
YES_NO = {"Yes": True, "No": False}


class HeaderMismatchError(ValueError):
    """The file layout changed upstream; stop rather than mis-load (D-022)."""


@dataclass(frozen=True, slots=True)
class RawRow:
    line_no: int
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedRow:
    line_no: int
    source_row_hash: str
    raw: tuple[str, ...]  # the 9 fields verbatim, in HEADER order
    sale_date: date
    county: County
    price_eur: Decimal
    not_full_market_price: bool
    vat_exclusive: bool
    is_new: bool
    size_band: SizeBand | None
    is_possible_duplicate: bool


@dataclass(frozen=True, slots=True)
class RowError:
    line_no: int
    raw_line: str
    error: str


def read_rows(data: bytes) -> Iterator[RawRow]:
    """Decode cp1252 CSV bytes and yield the data rows with 1-based file line numbers."""
    reader = csv.reader(io.StringIO(data.decode(ENCODING), newline=""))
    header = next(reader, None)
    if header != HEADER:
        raise HeaderMismatchError(f"unexpected PPR header: {header!r}")
    for fields in reader:
        yield RawRow(reader.line_num, tuple(fields))


def parse_description(text: str) -> bool:
    """Return is_new. English and Irish variants, including the mojibake rows."""
    t = text.strip().lower()
    if "second-hand" in t or "athláimhe" in t or "atháimhe" in t:
        return False
    if t.startswith("new ") or t.endswith(" nua"):
        return True
    raise ValueError(f"unknown property description {text!r}")


def parse_size(text: str) -> SizeBand | None:
    """Map the free-text size bands (English and Irish) to the three official bands."""
    t = text.strip()
    if not t:
        return None
    if "38" in t and "125" in t:
        return SizeBand.FROM_38_TO_125
    if "125" in t:
        return SizeBand.GTE_125  # "greater than" and "greater than or equal to" both appear
    if "38" in t:
        return SizeBand.LT_38
    raise ValueError(f"unknown size description {text!r}")


def _canonical(fields: Iterable[str]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", f).strip() for f in fields)


def row_hash(fields: tuple[str, ...], occurrence: int) -> str:
    """sha256 of the whitespace-normalised fields plus the occurrence index (D-001)."""
    payload = "\x1f".join((*_canonical(fields), str(occurrence)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_fields(
    fields: tuple[str, ...],
) -> tuple[date, County, Decimal, bool, bool, bool, SizeBand | None]:
    raw_date, _addr, raw_county, _eircode, raw_price, raw_nfmp, raw_vat, raw_desc, raw_size = fields
    sale_date = datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()
    try:
        county = County(raw_county.strip().lower())
    except ValueError:
        raise ValueError(f"unknown county {raw_county!r}") from None
    m = PRICE_RE.match(raw_price.strip())
    if not m:
        raise ValueError(f"bad price {raw_price!r}")
    price = Decimal(m.group(1).replace(",", ""))
    if raw_nfmp.strip() not in YES_NO or raw_vat.strip() not in YES_NO:
        raise ValueError(f"bad Yes/No flag {raw_nfmp!r} / {raw_vat!r}")
    return (
        sale_date,
        county,
        price,
        YES_NO[raw_nfmp.strip()],
        YES_NO[raw_vat.strip()],
        parse_description(raw_desc),
        parse_size(raw_size),
    )


def parse(rows: Iterable[RawRow]) -> Iterator[ParsedRow | RowError]:
    """Parse rows in file order. Identical rows get distinct hashes via an occurrence index.

    `is_possible_duplicate` marks every repeat of an earlier row's date, address and price
    (the 1,188 exact duplicates in the Phase 0 profile), so counts can exclude them.
    """
    seen_rows: Counter[tuple[str, ...]] = Counter()
    seen_sales: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        if len(row.fields) != len(HEADER):
            yield RowError(
                row.line_no, ",".join(row.fields), f"expected 9 fields, got {len(row.fields)}"
            )
            continue
        try:
            sale_date, county, price, nfmp, vat, is_new, size = _parse_fields(row.fields)
        except ValueError as exc:
            yield RowError(row.line_no, ",".join(row.fields), str(exc))
            continue
        canon = _canonical(row.fields)
        occurrence = seen_rows[canon]
        seen_rows[canon] += 1
        sale_key = (canon[0], canon[1].casefold(), canon[4])
        duplicate = seen_sales[sale_key] > 0
        seen_sales[sale_key] += 1
        yield ParsedRow(
            line_no=row.line_no,
            source_row_hash=row_hash(row.fields, occurrence),
            raw=row.fields,
            sale_date=sale_date,
            county=county,
            price_eur=price,
            not_full_market_price=nfmp,
            vat_exclusive=vat,
            is_new=is_new,
            size_band=size,
            is_possible_duplicate=duplicate,
        )
