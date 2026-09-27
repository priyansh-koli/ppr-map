import enum


class County(enum.StrEnum):
    CARLOW = "carlow"
    CAVAN = "cavan"
    CLARE = "clare"
    CORK = "cork"
    DONEGAL = "donegal"
    DUBLIN = "dublin"
    GALWAY = "galway"
    KERRY = "kerry"
    KILDARE = "kildare"
    KILKENNY = "kilkenny"
    LAOIS = "laois"
    LEITRIM = "leitrim"
    LIMERICK = "limerick"
    LONGFORD = "longford"
    LOUTH = "louth"
    MAYO = "mayo"
    MEATH = "meath"
    MONAGHAN = "monaghan"
    OFFALY = "offaly"
    ROSCOMMON = "roscommon"
    SLIGO = "sligo"
    TIPPERARY = "tipperary"
    WATERFORD = "waterford"
    WESTMEATH = "westmeath"
    WEXFORD = "wexford"
    WICKLOW = "wicklow"


class GeocodeConfidence(enum.StrEnum):
    """Ordered from most to least precise (D-003)."""

    EXACT = "exact"
    STREET = "street"
    LOCALITY = "locality"
    ROUTING_KEY = "routing_key"
    COUNTY = "county"
    UNMATCHED = "unmatched"


class IngestKind(enum.StrEnum):
    PPR = "ppr"
    GTFS = "gtfs"
    OSM = "osm"
    CENSUS = "census"
    POBAL = "pobal"
    SCHOOLS = "schools"
    BOUNDARIES = "boundaries"
    CRIME = "crime"
    PLANNING = "planning"
    ENVIRONMENT = "environment"
    BENCHMARKS = "benchmarks"
    GEOCODE = "geocode"
    AGGREGATE = "aggregate"


class IngestStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED_UNCHANGED = "skipped_unchanged"


class SizeBand(enum.StrEnum):
    """PPR 'Property Size Description' bands (new dwellings, mostly 2010-2018)."""

    LT_38 = "lt_38"
    FROM_38_TO_125 = "38_to_125"
    GTE_125 = "gte_125"


class AreaKind(enum.StrEnum):
    COUNTRY = "country"
    COUNTY = "county"
    LOCAL_AUTHORITY = "local_authority"
    ELECTORAL_DIVISION = "electoral_division"
    SMALL_AREA = "small_area"
    TOWNLAND = "townland"
    SETTLEMENT = "settlement"
    ROUTING_KEY = "routing_key"
    DUBLIN_DISTRICT = "dublin_district"


class PeriodKind(enum.StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ROLLING_12M = "rolling_12m"


class Segment(enum.StrEnum):
    ALL = "all"
    NEW = "new"
    SECOND_HAND = "second_hand"


class HexWindow(enum.StrEnum):
    ROLLING_12M = "rolling_12m"
    ROLLING_36M = "rolling_36m"


class PoiType(enum.StrEnum):
    SCHOOL_PRIMARY = "school_primary"
    SCHOOL_POST_PRIMARY = "school_post_primary"
    SCHOOL_SPECIAL = "school_special"
    BUS_STOP = "bus_stop"
    LUAS_STOP = "luas_stop"
    RAIL_STATION = "rail_station"
    DART_STATION = "dart_station"
    SHOP = "shop"
    SUPERMARKET = "supermarket"
    PHARMACY = "pharmacy"
    PARK = "park"
    GYM = "gym"
    RESTAURANT = "restaurant"
    GP = "gp"


class PlanningMatchKind(enum.StrEnum):
    SAME_ADDRESS = "same_address"
    SAME_EIRCODE = "same_eircode"
    WITHIN_250M = "within_250m"
    LARGE_SCHEME_1KM = "large_scheme_1km"


class EnvironmentLayerKind(enum.StrEnum):
    RADON_GRID = "radon_grid"
    NOISE_ROAD_LDEN = "noise_road_lden"
    NOISE_RAIL_LDEN = "noise_rail_lden"
    NOISE_AIR_LDEN = "noise_air_lden"
    GZT_ZONE = "gzt_zone"


class UserType(enum.StrEnum):
    FIRST_TIME_BUYER = "first_time_buyer"
    MOVER = "mover"
    INVESTOR = "investor"
    AGENT = "agent"
    RESEARCHER = "researcher"


class PropertyInterest(enum.StrEnum):
    NEW = "new"
    SECOND_HAND = "second_hand"
    BOTH = "both"


class ConsentKind(enum.StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    MARKETING_EMAIL = "marketing_email"
    COOKIES_ANALYTICS = "cookies_analytics"
    AGE_18_PLUS = "age_18_plus"


class WishlistTargetKind(enum.StrEnum):
    PROPERTY = "property"
    AREA = "area"


class AlertFrequency(enum.StrEnum):
    OFF = "off"
    ON_DATA_UPDATE = "on_data_update"
    WEEKLY = "weekly"


class RemovalRelationship(enum.StrEnum):
    OWNER = "owner"
    OCCUPANT = "occupant"
    OTHER = "other"


class RemovalRequestType(enum.StrEnum):
    SUPPRESS_DISPLAY = "suppress_display"
    CORRECT_LOCATION = "correct_location"
    CORRECT_DETAILS = "correct_details"


class RemovalStatus(enum.StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
