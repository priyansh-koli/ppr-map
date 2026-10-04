"""Match addresses against our own street gazetteer (D-046), after Nominatim.

Nominatim reads an address as a hierarchy, so a part it does not know stops the match:
"8 Clover Avenue, Broom Heights, Midleton" finds nothing when "Broom Heights" is not in
OSM, even though Clover Avenue is. Here every part is looked up on its own in the
`gazetteer_feature` table (OSM streets, estates, address points and places, and the DHLGH
housing-development surveys), and a street or estate is accepted only if it lies near a
place named later in the same address. Without such an anchor nothing is accepted: a
street name alone is repeated across a county ("Main Street", "Church Road").

A one-letter misspelling ("Steplechase Hill") is forgiven in a long, distinctive word of a
name of two or more words, and only when exactly one name in the county is that close.
A name made only of street words ("The Park", "The Green") is anchored only by the part
right after it, usually its estate. A part that is itself the name of a place ("Jerpoint
West, Thomastown") is left to the locality steps even if an estate shares its name.
Everything here is pure and unit-tested; `runner.py` loads the index and writes the results.
"""

import collections
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.models.enums import GeocodeConfidence

from ppr_pipeline.address import fold
from ppr_pipeline.geocode.rules import (
    km_between,
    name_tokens,
    query_parts,
    split_house_number,
)

# How far an address in a place may lie from its point, by OSM place type. A city is too
# coarse to anchor a street: Dublin has several Oak Parks.
PLACE_RADIUS_KM = {
    "town": 3.0,
    "suburb": 2.0,
    "village": 1.5,
    "quarter": 1.5,
    "neighbourhood": 1.0,
    "townland": 1.5,
    "hamlet": 1.0,
    "locality": 1.0,
    "isolated_dwelling": 0.5,
    "farm": 0.5,
}
# An estate named later in the address anchors the parts before it ("Clover Avenue, Broom
# Heights"), but only closely.
ESTATE_ANCHOR_KM = 1.0
# Every other place the address names must lie this close to the match: a post town can be
# 15 km from the village ("Firies, Killarney"), not 50.
CONSISTENT_KM = 20.0
# Official polygons get a radius from their area, capped so a large settlement stays local.
MAX_AREA_RADIUS_KM = 4.0
# A street's point is the middle of its named stretch; a long road may pass through the
# place well away from it.
STREET_SLACK_KM = 0.5
# Same-named candidates further apart than this are two different streets: ambiguous.
SPREAD_KM = 1.0
# House-number points for one address further apart than this disagree: ambiguous.
ADDRESS_SPREAD_KM = 0.2
# Misspellings are forgiven only in words at least this long.
FUZZY_MIN_LEN = 6
# Words that make a street name but do not tell one street from another.
STREET_WORDS = {
    "avenue", "bank", "close", "copse", "court", "crescent", "crest", "dale", "downs",
    "drive", "gardens", "glade", "glen", "green", "grove", "heights", "hill", "lane", "lawn",
    "lawns", "lodge", "main", "manor", "meadow", "meadows", "mews", "orchard", "paddock",
    "paddocks", "park", "place", "rise", "road", "row", "square", "street", "terrace", "vale",
    "view", "walk", "way", "wood", "woods", "upper", "lower", "north", "south", "east", "west",
    "new", "old", "little", "great", "church", "cottages", "estate", "grange",
}  # fmt: skip

Tokens = frozenset[str]


@dataclass(frozen=True, slots=True)
class Feature:
    kind: str  # street | estate | address | place | city
    lon: float
    lat: float
    source: str
    radius_km: float = 0.0  # places only


@dataclass(frozen=True, slots=True)
class LocalMatch:
    confidence: GeocodeConfidence
    lon: float
    lat: float
    method: str  # osm:address | osm:street | osm:estate | osm:street_fuzzy | nhds:estate
    source: str
    part: str


@dataclass
class Index:
    """Gazetteer features by county and name tokens."""

    named: dict[tuple[str, Tokens], list[Feature]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    addresses: dict[tuple[str, Tokens, str], list[Feature]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    places: dict[tuple[str, Tokens], list[Feature]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    # Cities never anchor a street, but an address naming one must be near it.
    cities: dict[tuple[str, Tokens], list[Feature]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    # (county, other tokens, token with one letter deleted) -> full names that produce it
    near_misses: dict[tuple[str, Tokens, str], set[Tokens]] = field(
        default_factory=lambda: collections.defaultdict(set)
    )

    def add(
        self, county: str, name: str, feature: Feature, house_number: str | None = None
    ) -> None:
        tokens = name_tokens(name)
        if not tokens:
            return
        if feature.kind == "place":
            self.places[(county, tokens)].append(feature)
        elif feature.kind == "city":
            self.cities[(county, tokens)].append(feature)
        elif feature.kind == "address":
            if house_number:
                self.addresses[(county, tokens, house_number.lower())].append(feature)
        else:
            key = (county, tokens)
            if key not in self.named:
                for k in _deletion_keys(tokens):
                    self.near_misses[(county, *k)].add(tokens)
            self.named[key].append(feature)

    def fuzzy(self, county: str, tokens: Tokens) -> list[Feature]:
        """Features whose name differs from `tokens` by one letter in one long word, if
        exactly one such name exists in the county."""
        names: set[Tokens] = set()
        for k in _deletion_keys(tokens, with_whole=True):
            names |= self.near_misses.get((county, *k), set())
        names.discard(tokens)
        if len(tokens) < 2:
            return []
        names = {n for n in names if len(n) == len(tokens) and _one_edit(tokens, n)}
        if len(names) != 1:
            return []
        return self.named[(county, names.pop())]


def _deletion_keys(tokens: Tokens, with_whole: bool = False) -> Iterable[tuple[Tokens, str]]:
    """(other tokens, a long token with one letter deleted). With `with_whole`, also the
    long token itself, so an inserted letter in the query is found too."""
    for t in tokens:
        if len(t) < FUZZY_MIN_LEN - 1:
            continue
        rest = tokens - {t}
        if with_whole:
            yield rest, t
        if len(t) >= FUZZY_MIN_LEN:
            for i in range(len(t)):
                yield rest, t[:i] + t[i + 1 :]


def _one_edit(a: Tokens, b: Tokens) -> bool:
    """Exactly one word differs, by one inserted, deleted or replaced letter."""
    only_a, only_b = a - b, b - a
    if len(only_a) != 1 or len(only_b) != 1:
        return False
    x, y = next(iter(only_a)), next(iter(only_b))
    if x in STREET_WORDS or y in STREET_WORDS:
        return False
    if max(len(x), len(y)) < FUZZY_MIN_LEN or abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(c1 != c2 for c1, c2 in zip(x, y, strict=True)) == 1
    short, long_ = sorted((x, y), key=len)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def place_radius_km(place_type: str | None, area_km2: float | None = None) -> float:
    """OSM place nodes by type; official polygons (settlements, townlands) by their size."""
    if area_km2 is not None:
        return min(math.sqrt(area_km2 / math.pi) + 0.5, MAX_AREA_RADIUS_KM)
    return PLACE_RADIUS_KM.get(place_type or "", 1.0)


def _near(features: Sequence[Feature], anchors: Sequence[Feature]) -> list[tuple[float, Feature]]:
    """Features within an anchor's reach, with their distance to the nearest anchor."""
    out = []
    for f in features:
        slack = STREET_SLACK_KM if f.kind == "street" else 0.0
        best = min(
            (km_between(f.lon, f.lat, a.lon, a.lat) - a.radius_km - slack for a in anchors),
            default=math.inf,
        )
        if best <= 0:
            out.append((best, f))
    return out


def _spread_km(features: Sequence[Feature]) -> float:
    return max(
        (km_between(a.lon, a.lat, b.lon, b.lat) for a in features for b in features),
        default=0.0,
    )


def _anchors(index: Index, county: str, parts: Sequence[str]) -> list[Feature]:
    """Places (or estates) named by the first of `parts` that names any: the most specific
    locality the address gives."""
    for part in parts:
        tokens = name_tokens(part)
        if not tokens:
            continue
        out = list(index.places.get((county, tokens), []))
        estates = [f for f in index.named.get((county, tokens), []) if f.kind == "estate"]
        out += [Feature("place", f.lon, f.lat, f.source, ESTATE_ANCHOR_KM) for f in estates]
        if out:
            return out
    return []


def _consistent(index: Index, county: str, parts: Sequence[str], lon: float, lat: float) -> bool:
    """Every later part that names a known place (or city) has one within reach."""
    for part in parts:
        tokens = name_tokens(part)
        if not tokens or fold(part) == county:
            continue
        known = index.places.get((county, tokens), []) + index.cities.get((county, tokens), [])
        if known and all(
            km_between(lon, lat, a.lon, a.lat) - a.radius_km > CONSISTENT_KM for a in known
        ):
            return False
    return True


def _method(f: Feature, fuzzy: bool) -> str:
    prefix = "nhds" if f.source.startswith("DHLGH") else "osm"
    kind = "street" if f.kind == "street" else "estate"
    return f"{prefix}:{kind}{'_fuzzy' if fuzzy else ''}"


def match(index: Index, address_display: str, county: str) -> LocalMatch | None:
    """The most specific part of the address found near a place named after it."""
    parts = query_parts(address_display, county)
    for i, part in enumerate(parts[:-1]):
        house_number, name = split_house_number(part)
        tokens = name_tokens(name)
        if not tokens or fold(name) == county:
            continue
        generic = tokens <= STREET_WORDS
        anchors = _anchors(index, county, parts[i + 1 : i + 2] if generic else parts[i + 1 :])
        if not anchors:
            continue

        if house_number:
            candidates = index.addresses.get((county, tokens, house_number), [])
            points = [f for _, f in _near(candidates, anchors)]
            if (
                points
                and _spread_km(points) <= ADDRESS_SPREAD_KM
                and _consistent(index, county, parts[i + 1 :], points[0].lon, points[0].lat)
            ):
                p = points[0]
                return LocalMatch(
                    GeocodeConfidence.EXACT, p.lon, p.lat, "osm:address", p.source, part
                )

        if (county, tokens) in index.places:
            continue  # a townland or village: the locality steps place it
        fuzzy = False
        near = _near(index.named.get((county, tokens), []), anchors)
        if not near:
            near = _near(index.fuzzy(county, tokens), anchors)
            fuzzy = True
        if not near or _spread_km([f for _, f in near]) > SPREAD_KM:
            continue
        # Prefer a street to an estate of the same name, then the one nearest an anchor.
        _, best = min(near, key=lambda t: (t[1].kind != "street", t[0]))
        if not _consistent(index, county, parts[i + 1 :], best.lon, best.lat):
            continue
        return LocalMatch(
            GeocodeConfidence.STREET, best.lon, best.lat, _method(best, fuzzy), best.source, part
        )
    return None
