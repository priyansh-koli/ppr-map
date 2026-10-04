"""Address and Eircode normalisation for PPR rows (docs/ARCHITECTURE.md, Data flow step 4).

Three forms come out of one raw address:
- `display`: the filer's text, cleaned (junk parts dropped, ALL CAPS turned into title case).
  Abbreviations are kept as written, so a wrong expansion is never shown to users.
- `normalised`: lowercase with abbreviations expanded; used for search and fuzzy matching.
- `key`: `normalised` without the unit and the trailing county, alphanumerics only, accents
  folded ("Seán" keys like "Sean"). Two numbers keep a hyphen between them, so "1 25" and
  "125" stay apart. Together with the county and the unit it is the exact dedupe key for a
  Property (D-001, R-11).
"""

import re
import unicodedata
from dataclasses import dataclass
from itertools import pairwise

from app.models.enums import County

COUNTIES = {c.value for c in County}

# Whole comma-separated parts that carry no information.
JUNK_PARTS = {"n/a", "na", "n.a", "n.a.", "-", ".", "none", "unknown"}

# Token expansions (lowercase, trailing dot stripped). `st` is handled separately.
ABBREVIATIONS = {
    "rd": "road",
    "ave": "avenue",
    "av": "avenue",
    "sq": "square",
    "pk": "park",
    "dr": "drive",
    "tce": "terrace",
    "terr": "terrace",
    "cres": "crescent",
    "cresc": "crescent",
    "ct": "court",
    "crt": "court",
    "gdns": "gardens",
    "grn": "green",
    "hts": "heights",
    "lwr": "lower",
    "upr": "upper",
    "est": "estate",
    "mt": "mount",
    "cl": "close",
    "cotts": "cottages",
    "apt": "apartment",
    "appartment": "apartment",
    "app": "apartment",
    "apts": "apartments",
    "blk": "block",
}
# `st` means "Saint" only where a name starts: first in its part or after a house number
# ("St John's Road", "5 St John's Road"). After a word ("5 Main St Naas") or directly before
# one of these ("Main St Lower") it means "Street".
STREET_QUALIFIERS = {"lower", "upper", "north", "south", "east", "west", "little", "great"}

UNIT_WORDS = {"apartment", "flat", "unit", "suite"}
UNIT_ID = re.compile(r"^[a-z]?\d+[a-z]?$|^[a-z]$")
HOUSE_NUMBER = re.compile(r"^\d+[a-z]?(?:-\d+[a-z]?)?$")


def st_is_saint(prev: str | None, nxt: str | None) -> bool:
    """`st` between the words `prev` and `nxt` (lowercase, None at the ends)."""
    starts_name = prev is None or bool(HOUSE_NUMBER.match(prev))
    return starts_name and nxt is not None and nxt not in STREET_QUALIFIERS


# Valid Dublin postal districts (D6W is the only lettered one).
DUBLIN_DISTRICTS = {str(n) for n in [*range(1, 19), 20, 22, 24]} | {"6w"}
DUBLIN_DISTRICT_RE = re.compile(r"\bdublin (\d{1,2}w?)\b")

# Eircode: routing key (letter, 2 digits, or D6W) + 4-character unique identifier.
EIRCODE_RE = re.compile(r"^(?:[AC-FHKNPRTV-Y]\d{2}|D6W)[0-9AC-FHKNPRTV-Y]{4}$")

# Words kept lowercase in title case unless they start a part.
LOWER_WORDS = {"of", "the", "and", "on", "at", "in", "na", "an", "de", "le", "ná", "upon"}


@dataclass(frozen=True, slots=True)
class Address:
    display: str
    normalised: str
    key: str
    unit: str | None
    house_number: str | None
    dublin_district: str | None


def _parts(raw: str) -> list[str]:
    text = re.sub(r"\s+", " ", raw).strip()
    parts = [p.strip(" .") for p in text.split(",")]
    return [p for p in parts if p and p.lower() not in JUNK_PARTS]


def _title_word(word: str) -> str:
    if any(c.isdigit() for c in word):
        return word.upper()  # 5B, D6W, A94
    lower = word.lower()
    if "'" in lower:
        head, _, tail = lower.partition("'")
        # O'Brien, D'Arcy; but James's, Mary's.
        tail = tail.capitalize() if len(head) == 1 and len(tail) > 1 else tail
        return f"{head.capitalize()}'{tail}"
    if lower.startswith("mc") and len(lower) > 2:
        return "Mc" + lower[2:].capitalize()
    return "-".join(p.capitalize() for p in lower.split("-"))


def _title_part(part: str) -> str:
    words = part.split(" ")
    out = [
        # "Parish of Anne Street", but "6 The Sycamore" (a small word after a number starts a name)
        w.lower()
        if i > 0 and w.lower() in LOWER_WORDS and words[i - 1].isalpha()
        else _title_word(w)
        for i, w in enumerate(words)
    ]
    return " ".join(out)


def _display(parts: list[str]) -> str:
    joined = ", ".join(parts)
    if any(c.islower() for c in joined):
        return joined  # the filer used mixed case; trust it
    return ", ".join(_title_part(p) for p in parts)


GLUED_UNIT = re.compile(r"\b(apt|flat|unit)(\d+[a-z]?)\b")


def _expand_part(part: str) -> list[str]:
    text = GLUED_UNIT.sub(r"\1 \2", part.lower())  # "apt1" -> "apt 1"
    tokens = [t.rstrip(".") for t in text.replace(".", ". ").split()]
    tokens = [t for t in tokens if t]
    out: list[str] = []
    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i > 0 else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if tok in ("no", "number") and nxt and nxt[0].isdigit():
            continue  # "No. 5 Main St" -> "5 main street"
        if tok == "county" and nxt in COUNTIES:
            out.append("co")  # "County Cork" and "Co. Cork" compare equal
        elif tok == "st":
            out.append("saint" if st_is_saint(prev, nxt) else "street")
        else:
            out.append(ABBREVIATIONS.get(tok, tok))
    return out


def _split_unit(parts: list[list[str]]) -> tuple[str | None, list[list[str]]]:
    """Take a leading "apartment 5 [block a]" off the first part(s)."""
    if not parts or not parts[0] or parts[0][0] not in UNIT_WORDS:
        return None, parts
    first = parts[0]
    if len(first) < 2 or not UNIT_ID.match(first[1]):
        return None, parts
    unit = first[:2]
    rest = first[2:]
    if len(rest) >= 2 and rest[0] == "block" and UNIT_ID.match(rest[1]):
        unit, rest = unit + rest[:2], rest[2:]
    remaining = ([rest] if rest else []) + parts[1:]
    # "Apartment 5, Block A, The Maltings"
    if remaining and len(remaining[0]) == 2 and remaining[0][0] == "block":
        unit, remaining = unit + remaining[0], remaining[1:]
    return " ".join(unit), remaining


def fold(text: str) -> str:
    """Lowercase, no accents: "Dún Laoghaire" -> "dun laoghaire"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def address_key(parts: list[list[str]]) -> str:
    """Alphanumerics only, but a hyphen between two numbers: "1 25" is not "125" (P2 #36),
    nor is the range "1-25". Accents are folded first, so a fada is never dropped (#37)."""
    words = re.findall(r"[a-z0-9]+", fold(" ".join(" ".join(p) for p in parts)))
    out = words[:1]
    for prev, word in pairwise(words):
        out.append(("-" if prev[-1].isdigit() and word[0].isdigit() else "") + word)
    return "".join(out)


def _strip_county(parts: list[list[str]], county: str) -> list[list[str]]:
    if not parts:
        return parts
    last = parts[-1]
    if last[-2:] == ["co", county]:
        last = last[:-2]
        return [*parts[:-1], last] if last else parts[:-1]
    if last == [county] and len(parts) > 1:
        return parts[:-1]  # "Douglas, Cork" keys like "Douglas, Co Cork"
    return parts


def normalise_address(raw: str, county: str) -> Address:
    """`county` is the lowercase county name from the PPR County column."""
    parts = _parts(raw)
    display = _display(parts) or re.sub(r"\s+", " ", raw).strip()
    expanded = [t for t in (_expand_part(p) for p in parts) if t]
    normalised = ", ".join(" ".join(p) for p in expanded)

    unit, rest = _split_unit(expanded)
    rest = _strip_county(rest, county)
    key = address_key(rest)

    house_number = None
    if rest and rest[0] and HOUSE_NUMBER.match(rest[0][0]):
        house_number = rest[0][0]

    district = None
    if county == "dublin":
        m = DUBLIN_DISTRICT_RE.search(normalised)
        if m and m.group(1) in DUBLIN_DISTRICTS:
            district = "D" + m.group(1).upper()

    return Address(display, normalised, key, unit, house_number, district)


def normalise_eircode(raw: str) -> str | None:
    """Return the 7-character Eircode, or None if `raw` is empty or not a valid format."""
    code = re.sub(r"\s+", "", raw).upper()
    return code if EIRCODE_RE.match(code) else None


def dublin_district_from_eircode(eircode: str) -> str | None:
    """Dublin routing keys D01-D24 and D6W are the postal districts."""
    rk = eircode[:3]
    if rk == "D6W":
        return "D6W"
    if rk[0] == "D" and rk[1:].isdigit() and str(int(rk[1:])) in DUBLIN_DISTRICTS:
        return f"D{int(rk[1:])}"
    return None
