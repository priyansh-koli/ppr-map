"""Pure geocoding rules for the D-003 cascade: queries, name matching, candidate checks.

Nominatim matches loosely: "Fenit, Tralee" returns Fenit *Road* first and "Coosan, Athlone"
returns the *Coosan Heath* estate. A candidate is only accepted when its name matches the
address part that was queried, it is a plausible feature for the level claimed, and it lies
near the address's town. Everything here is deterministic and unit-tested; `runner.py` does
the I/O.
"""

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.models.enums import GeocodeConfidence

from ppr_pipeline.address import ABBREVIATIONS, HOUSE_NUMBER

# "Apt 11 Cartron Court" -> "Cartron Court"; the unit is stored separately on the property.
UNIT_PREFIX = re.compile(
    r"^(?:apt|apartment|appartment|flat|unit|no)\.?\s*[a-z]?\d+[a-z]?"
    r"(?:\s+block\s+[a-z0-9]+)?\b[\s,]*",
    re.I,
)
COUNTY_PART = re.compile(r"^(?:co\.?|county)\s+(\w+)$", re.I)
DUBLIN_DISTRICT = re.compile(r"^dublin\s+\d{1,2}\s*w?$", re.I)
# "Donnybrook Dublin 4", "Kildare Town", "Louth Village", "Off Cathedral Road"
TRAILING_DISTRICT = re.compile(r"\s+dublin\s+\d{1,2}\s*w?$", re.I)
TRAILING_TOWN = re.compile(r"(?<=\w)\s+(?:town|village)$", re.I)
LEADING_OFF = re.compile(r"^off\s+", re.I)

# Words that may differ between a PPR address and the OSM name without changing the place.
NAME_FILLER = {"the", "saint", "of"}
# Townland divisions: the PPR says "Pollerton", OSM has "Pollerton Big" and "Pollerton Little".
DIVISIONS = {
    "big", "little", "more", "beg", "upper", "lower", "north", "south", "east", "west",
    "middle", "great",
}  # fmt: skip

# Highway types that are streets people live on (not lamps, stops or paths).
STREET_HIGHWAYS = {
    "residential",
    "living_street",
    "unclassified",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
    "service",
    "road",
    "pedestrian",
    "track",
}
# Buildings whose name can stand for where people live ("The Benson Building", "Carrigmore
# Court"). A station, school or hotel sharing a place's name is not an address: "Adamstown"
# matched Adamstown railway station and put a whole suburb on the platform.
RESIDENTIAL_BUILDINGS = {
    "apartments", "residential", "house", "terrace", "detached", "semidetached_house",
    "bungalow", "dormitory", "flats", "yes",
}  # fmt: skip
LOCALITY_PLACES = {
    "town",
    "village",
    "hamlet",
    "suburb",
    "neighbourhood",
    "quarter",
    "isolated_dwelling",
    "locality",
    "townland",
    "farm",
}
# Cities are too coarse to be a useful location; they fall through to routing key or county.
CITY_PLACES = {"city"}

# How far a candidate may lie from the address's town (the last address part).
MAX_KM_FROM_TOWN = {GeocodeConfidence.EXACT: 5.0, GeocodeConfidence.STREET: 5.0}
MAX_KM_FROM_CITY = 15.0
MAX_KM_LOCALITY = 20.0


@dataclass(frozen=True, slots=True)
class Candidate:
    confidence: GeocodeConfidence
    lon: float
    lat: float
    kind: str  # "category/type" from Nominatim
    name: str
    raw: dict[str, Any]


def fold(text: str) -> str:
    """Lowercase, no accents: "Dún Laoghaire" -> "dun laoghaire"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def query_parts(address_display: str, county: str) -> list[str]:
    """Comma parts to query, most specific first. Drops the unit and a trailing "Co X",
    and reduces "Dublin 6W" to "Dublin" (postal districts are not OSM places). A bare
    county name is kept: "..., Cavan" is usually the town."""
    parts = [p.strip(" .") for p in address_display.split(",")]
    parts = [p for p in parts if p]
    if parts:
        parts[0] = UNIT_PREFIX.sub("", parts[0]).strip()
        if not parts[0]:
            parts = parts[1:]
    if parts:
        m = COUNTY_PART.match(parts[-1])
        if m and fold(m.group(1)) == county:
            parts = parts[:-1]
    # "Rathvilly Carlow": the county name glued to the end of a part.
    trailing_county = re.compile(rf"(?<=\w)\s+(?:(?:co\.?|county)\s+)?{re.escape(county)}$", re.I)
    out: list[str] = []
    for p in parts:
        if DUBLIN_DISTRICT.match(p):
            p = "Dublin"
        else:
            p = TRAILING_TOWN.sub("", TRAILING_DISTRICT.sub("", p))
            p = LEADING_OFF.sub("", trailing_county.sub("", p))
        if not out or fold(out[-1]) != fold(p):
            out.append(p)
    return out


def ends_with_county_name(parts: Sequence[str], county: str) -> bool:
    """ "..., Athenry, Galway": the last part may be the county or the town of that name."""
    return len(parts) > 1 and fold(parts[-1]) == county


def ladder(parts: Sequence[str], county: str) -> list[tuple[str, int]]:
    """(query, index of its first part), from the full address down to the town alone.

    A trailing bare county name is tried with and without: it helps "Church St, Cavan"
    (the town) and breaks "5 Abbey Glen, Athenry, Galway" (the county). It is never
    queried alone, because that cannot tell the town from the county."""
    tail = ends_with_county_name(parts, county)
    out: list[tuple[str, int]] = []
    for i in range(len(parts) - (1 if tail else 0)):
        out.append((", ".join(parts[i:]), i))
        if tail:
            out.append((", ".join(parts[i:-1]), i))
    return out


def town_parts(parts: Sequence[str], county: str) -> list[str]:
    """Parts that may name the address's town, most likely first."""
    if len(parts) < 2:
        return []
    if ends_with_county_name(parts, county):
        return [parts[-2], parts[-1]] if len(parts) > 2 else [parts[-1]]
    return [parts[-1]]


def town_point(results: Sequence[Mapping[str, Any]], part: str) -> tuple[float, float, bool] | None:
    """(lon, lat, is_city) of the first result that is a settlement named `part`."""
    for r in results:
        if not names_match(part, candidate_names(r)):
            continue
        category, type_ = r.get("category"), r.get("type")
        rank = int(r.get("place_rank", 0))
        place = category == "place" and type_ in LOCALITY_PLACES | CITY_PLACES
        admin = category == "boundary" and type_ == "administrative" and rank >= 16
        if place or admin:
            is_city = type_ in CITY_PLACES or (admin and rank <= 16)
            return float(r["lon"]), float(r["lat"]), is_city
    return None


def name_tokens(text: str) -> frozenset[str]:
    """Comparable words of a name: folded, abbreviations expanded, possessives and
    house numbers removed, and filler words ignored."""
    text = re.sub(r"'s\b|['\u2019]", "", fold(text))
    words = re.findall(r"[a-z0-9]+", text)
    out: set[str] = set()
    for i, w in enumerate(words):
        if w == "st":
            w = "street" if i == len(words) - 1 else "saint"
        w = ABBREVIATIONS.get(w, w)
        if w in NAME_FILLER or w == "no" or HOUSE_NUMBER.match(w):
            continue
        out.add(w)
    return frozenset(out)


def names_match(queried: str, names: Sequence[str]) -> bool:
    """Same words, give or take filler; the candidate may add a townland division."""
    want = name_tokens(queried)
    if not want:
        return False
    for n in names:
        got = name_tokens(n) if n else frozenset()
        if got == want or (want < got and got - want <= DIVISIONS):
            return True
    return False


def candidate_names(result: Mapping[str, Any]) -> list[str]:
    details = result.get("namedetails") or {}
    names = [result.get("name") or ""]
    names += [v for k, v in details.items() if k.startswith(("name", "alt_name", "old_name"))]
    return names


def house_number_matches(result: Mapping[str, Any], house_number: str) -> bool:
    got = (result.get("address") or {}).get("house_number", "")
    return re.sub(r"\s+", "", str(got)).lower() == house_number.lower()


def split_house_number(part: str) -> tuple[str | None, str]:
    """ "58 Willowbank" -> ("58", "Willowbank"); "No. 5 Main St" -> ("5", "Main St")."""
    words = part.split()
    if words and words[0].lower().rstrip(".") in ("no", "number"):
        words = words[1:]
    if len(words) > 1 and HOUSE_NUMBER.match(words[0].lower()):
        return words[0].lower(), " ".join(words[1:])
    return None, " ".join(words)


def classify(result: Mapping[str, Any], queried_part: str) -> tuple[GeocodeConfidence | None, str]:
    """Level of one Nominatim result for `queried_part` (the query's first, most specific
    part), or None and why not. A house number counts only if it is in that part."""
    category, type_ = result.get("category", ""), result.get("type", "")
    address = result.get("address") or {}
    house_number, name = split_house_number(queried_part)

    if house_number and house_number_matches(result, house_number):
        streets = [str(address.get(k, "")) for k in ("road", "residential", "neighbourhood")]
        if names_match(name, streets):
            return GeocodeConfidence.EXACT, ""
        return None, "house_number_other_street"

    if not names_match(name, candidate_names(result)):
        return None, "name_mismatch"

    if category == "highway":
        if type_ in STREET_HIGHWAYS:
            return GeocodeConfidence.STREET, ""
        return None, "implausible_type"
    if category == "landuse" and type_ == "residential":
        return GeocodeConfidence.STREET, ""
    if category == "building":
        if type_ in RESIDENTIAL_BUILDINGS:
            return GeocodeConfidence.STREET, ""
        return None, "implausible_type"
    if category == "place" and type_ in CITY_PLACES:
        return None, "too_coarse"
    if category == "place" and type_ in LOCALITY_PLACES:
        return GeocodeConfidence.LOCALITY, ""
    if category == "boundary" and type_ in ("administrative", "civil_parish"):
        # Townlands and civil parishes; counties and municipal districts are too coarse.
        if int(result.get("place_rank", 0)) >= 20:
            return GeocodeConfidence.LOCALITY, ""
        return None, "too_coarse"
    return None, "implausible_type"


RANK = {c: i for i, c in enumerate(GeocodeConfidence)}
# Without a town to anchor it, a name found in two places this far apart is ambiguous:
# "Tullow Rd" is in Carlow town and in Leighlinbridge. A town, its townland and its parish
# share a name and overlap, so localities get more room.
AMBIGUOUS_KM = {GeocodeConfidence.EXACT: 3.0, GeocodeConfidence.STREET: 3.0}
AMBIGUOUS_KM_LOCALITY = 15.0


def pick(
    results: Sequence[Mapping[str, Any]],
    queried_part: str,
    town: tuple[float, float, bool] | None,
) -> tuple[Candidate | None, list[str]]:
    """The best acceptable result of one query, and the reasons others were rejected.

    `town` is None when the query is the town itself or the town did not geocode."""
    rejected: list[str] = []
    accepted: list[Candidate] = []
    for r in results:
        confidence, why = classify(r, queried_part)
        if confidence is None:
            rejected.append(why)
            continue
        lon, lat = float(r["lon"]), float(r["lat"])
        if too_far_from_town(confidence, lon, lat, town):
            rejected.append("far_from_town")
            continue
        kind = f"{r.get('category')}/{r.get('type')}"
        accepted.append(Candidate(confidence, lon, lat, kind, str(r.get("name") or ""), dict(r)))
    if not accepted:
        return None, rejected
    # Most precise level first; among localities, a place node (the village centre) before
    # a boundary's centroid.
    best = min(accepted, key=lambda c: (RANK[c.confidence], not c.kind.startswith("place/")))
    if town is None:
        limit = AMBIGUOUS_KM.get(best.confidence, AMBIGUOUS_KM_LOCALITY)
        rivals = [c for c in accepted if c.confidence is best.confidence]
        if any(km_between(best.lon, best.lat, c.lon, c.lat) > limit for c in rivals):
            return None, [*rejected, "ambiguous"]
    return best, rejected


def km_between(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def too_far_from_town(
    confidence: GeocodeConfidence,
    lon: float,
    lat: float,
    town: tuple[float, float, bool] | None,
) -> bool:
    """`town` is (lon, lat, is_city) of the address's last part, when it geocoded."""
    if town is None:
        return False
    tlon, tlat, is_city = town
    if confidence is GeocodeConfidence.LOCALITY:
        limit = MAX_KM_LOCALITY
    else:
        limit = MAX_KM_FROM_CITY if is_city else MAX_KM_FROM_TOWN[confidence]
    return km_between(lon, lat, tlon, tlat) > limit


def name_variants(name: str) -> set[str]:
    """ "Muinebeag (Bagenalstown)" is also "Muinebeag" and "Bagenalstown";
    "Graiguenamanagh-Tinnahinch" is also each town on its own."""
    out = {name}
    m = re.fullmatch(r"(.+?)\s*\((.+)\)", name)
    if m:
        out |= {m.group(1), m.group(2)}
    for n in list(out):
        if re.search(r"\w-\w", n) and " " not in n:
            out |= set(n.split("-"))
    return out
