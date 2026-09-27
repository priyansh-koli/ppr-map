"""Boundary names, slugs, and loading real Tailte Éireann / CSO features."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.models.enums import AreaKind

from ppr_pipeline.boundaries import LAYERS, area_name, area_slug, load_boundaries, read_layer
from ppr_pipeline.sources import load_sources
from tests.conftest import FIXTURES


def test_area_names_from_official_upper_case() -> None:
    assert area_name("KILLINAGH/TEEBANE") == "Killinagh/Teebane"
    assert area_name("CEATHARLACH (TUATH)") == "Ceatharlach (Tuath)"
    assert area_name("CILL LAIGHNEACH/AN TAOBH BÁN") == "Cill Laighneach/An Taobh Bán"
    assert area_name("BALLYO'BRIEN") == "Ballyo'Brien"
    assert area_name("ST. JAMES'S") == "St. James's"
    assert area_name("Dún na nGall") == "Dún na nGall"  # already cased: left alone
    assert area_name("DUNDALK No. 2 URBAN") == "Dundalk No. 2 Urban"


def test_slugs_are_stable_and_distinguish_same_names() -> None:
    assert area_slug(AreaKind.COUNTY, "cork", "Cork") == "cork"
    assert area_slug(AreaKind.SMALL_AREA, "A017010016", "017010016") == "sa-017010016"
    a = area_slug(AreaKind.TOWNLAND, "4e53b5b4-f409-4728-9d0b-f62916789acb", "Barnadarrig")
    b = area_slug(AreaKind.TOWNLAND, "0000aaaa-f409-4728-9d0b-f62916789acb", "Barnadarrig")
    assert a.startswith("townland-barnadarrig-") and a != b
    assert a == area_slug(AreaKind.TOWNLAND, "4e53b5b4-f409-4728-9d0b-f62916789acb", "Barnadarrig")


def test_every_layer_has_a_pinned_url() -> None:
    datasets = load_sources()["tailte_boundaries"].datasets
    assert datasets is not None
    assert {layer.kind.value for layer in LAYERS} == set(datasets)
    assert all(url.startswith("https://data-osi.opendata.arcgis.com/") for url in datasets.values())


def _ed_fixture_with(tmp_path: Path, sql: str) -> str:
    path = tmp_path / "ed.gpkg"
    shutil.copy(FIXTURES / "boundaries" / "electoral_division_2022.gpkg", path)
    with sqlite3.connect(path) as db:
        # The R-tree triggers call SpatiaLite functions that plain sqlite3 lacks.
        triggers = db.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
        for (name,) in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        db.execute(sql)
    return str(path)


def test_null_attributes_stay_null(tmp_path: Path) -> None:
    ed = next(la for la in LAYERS if la.kind is AreaKind.ELECTORAL_DIVISION)
    path = _ed_fixture_with(tmp_path, "UPDATE electoral_division_2022 SET ED_GAEILGE = NULL")
    ((code, name, name_ga, _parent, _wkb),) = read_layer(path, ed)
    assert (name, name_ga) == ("CARLOW RURAL", None)
    assert code and code != "None"


def test_a_feature_without_a_code_is_an_error(tmp_path: Path) -> None:
    ed = next(la for la in LAYERS if la.kind is AreaKind.ELECTORAL_DIVISION)
    path = _ed_fixture_with(tmp_path, "UPDATE electoral_division_2022 SET ED_GUID = NULL")
    with pytest.raises(ValueError, match="no code or name"):
        list(read_layer(path, ed))


@pytest.mark.db
def test_load_real_carlow_subset(engine: sa.Engine) -> None:
    """County Carlow, the Carlow Rural ED, one of its Small Areas, the Ballybannon townland
    and Carlow town, extracted unchanged from the Tailte Éireann / CSO layers."""
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    counts = load_boundaries(engine, FIXTURES / "boundaries", layers)
    assert counts == {
        "county": 1,
        "electoral_division": 1,
        "small_area": 1,
        "townland": 1,
        "settlement": 1,
    }
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT a.kind::text, a.name, a.name_ga, a.slug, p.name AS parent, "
                "ST_SRID(a.geom), ST_SRID(a.geom_full), ST_IsValid(a.geom) "
                "FROM area a LEFT JOIN area p ON p.id = a.parent_id ORDER BY a.id"
            )
        ).all()
        parts = conn.execute(sa.text("SELECT count(*) FROM area_part")).scalar_one()
    by_kind = {r[0]: r for r in rows}
    assert by_kind["county"][1:5] == ("Carlow", "Ceatharlach", "carlow", None)
    assert by_kind["electoral_division"][1] == "Carlow Rural"
    assert by_kind["electoral_division"][4] == "Carlow"
    assert by_kind["small_area"][3:5] == ("sa-017010016", "Carlow Rural")
    assert by_kind["townland"][1:3] == ("Ballybannon", "Baile Uí Bhánáin")
    assert by_kind["townland"][4] == "Carlow"
    assert by_kind["settlement"][4] == "Carlow"
    assert all(r[5:] == (4326, 2157, True) for r in rows)
    assert parts >= 5

    # Reloading is idempotent.
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM area")).scalar_one() == 5
