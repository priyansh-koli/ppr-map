"""The CSO Residential Property Price Index series a property follows (D-053).

The PPR does not say whether a home is a house or an apartment. A property with a unit
(Apt 5, Unit 3) follows an apartment series; the rest follow the house series of their
region, the most local the CSO publishes. Regions are the CSO's (RPPI background notes,
checked 2026-09-30); Dublin's four council areas have their own house series, but a PPR
address does not say which council it is in, so Dublin uses the county series."""

SOURCE = "cso_rppi"

# CSO code in table HPM09 -> label.
SERIES: dict[str, str] = {
    "06": "Dublin - houses",
    "07": "Dublin - apartments",
    "12": "National excluding Dublin - apartments",
    "14": "Midland - houses",
    "15": "West - houses",
    "19": "South-West - houses",
    "21": "Border - houses",
    "22": "Mid-East - houses",
    "23": "Mid-West - houses",
    "24": "South-East - houses",
}

REGION_HOUSES: dict[str, str] = {
    **dict.fromkeys(("cavan", "donegal", "leitrim", "monaghan", "sligo"), "21"),
    **dict.fromkeys(("laois", "longford", "offaly", "westmeath"), "14"),
    **dict.fromkeys(("galway", "mayo", "roscommon"), "15"),
    **dict.fromkeys(("kildare", "louth", "meath", "wicklow"), "22"),
    **dict.fromkeys(("clare", "limerick", "tipperary"), "23"),
    **dict.fromkeys(("carlow", "kilkenny", "waterford", "wexford"), "24"),
    **dict.fromkeys(("cork", "kerry"), "19"),
    "dublin": "06",
}


def series_code(county: str, has_unit: bool) -> str:
    if has_unit:
        return "07" if county == "dublin" else "12"
    return REGION_HOUSES[county]


def series_key(code: str) -> str:
    return f"rppi:{code}"


# SQL for the same choice, for set-based work (the calibration).
SERIES_SQL = (
    "CASE WHEN {unit} IS NOT NULL THEN CASE WHEN {county} = 'dublin' THEN 'rppi:07' "
    "ELSE 'rppi:12' END ELSE 'rppi:' || CASE {county} "
    + " ".join(f"WHEN '{c}' THEN '{code}'" for c, code in REGION_HOUSES.items())
    + " END END"
)


def gap_band(years: float) -> str:
    return "0-3y" if years < 3 else "3-7y" if years < 7 else "7y+"
