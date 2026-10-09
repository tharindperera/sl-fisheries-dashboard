from io import BytesIO
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import numpy as np
import pandas as pd
import pytest

from data import (WEATHER, MARINE, assemble_bundle, build_daily, build_forecasts,
                  coverage_by_year, export_bytes, validate_optional_csv, validate_product, validate_profiles)
from demo import generate_demo


@pytest.fixture(scope="module")
def demo():
    return generate_demo("2026-10-09")


def test_exact_16_sites_and_synthetic_isolation(demo):
    again = generate_demo("2026-10-09")
    assert demo["sites"].site_id.nunique() == 16
    for name, df in demo["products"].items():
        assert df.is_synthetic.all()
        pd.testing.assert_frame_equal(df, again["products"][name])
    assert build_daily(demo).is_synthetic.all()


def test_prefer_reanalysis_and_exclude_today(demo):
    daily = build_daily(demo, True, today="2026-10-09")
    assert not daily.duplicated(["site_id", "date_local"]).any()
    assert daily.date_local.max() == pd.Timestamp("2026-10-08")
    overlap = daily[daily.date_local.eq(pd.Timestamp("2026-10-02"))]
    assert overlap.weather_model.eq("era5").all()
    tail = daily[daily.date_local.eq(pd.Timestamp("2026-10-08"))]
    assert tail.weather_model.eq("ecmwf_ifs025").all()


def test_unmatched_domains_not_silently_dropped(demo):
    copy = {**demo, "products": demo["products"].copy()}
    marine = copy["products"]["marine_reanalysis"].copy()
    key = marine.iloc[0][["site_id", "date_local"]]
    copy["products"]["marine_reanalysis"] = marine.iloc[1:]
    daily = build_daily(copy, today="2026-10-09")
    row = daily[daily.site_id.eq(key.site_id) & daily.date_local.eq(key.date_local)].iloc[0]
    assert not row.marine_complete
    assert row.domain_match == "left_only"
    assert pd.isna(row.wave_height_max)


def test_forecasts_preserve_multiple_vintages(demo):
    copy = {**demo, "products": demo["products"].copy()}
    for name in ["weather_forecasts", "marine_forecasts"]:
        frame = copy["products"][name]
        second = frame.copy()
        second["snapshot_id"] = "2026-10-09T08:00:00Z"
        copy["products"][name] = pd.concat([frame, second], ignore_index=True)
    result = build_forecasts(copy)
    assert len(result) == 224
    assert not result.duplicated(["site_id", "date_local", "forecast_vintage"]).any()
    assert "weather_model" in result and "marine_model" in result


def test_coverage_counts_leap_year_and_missing_year(demo):
    daily = build_daily(demo, today="2026-10-09")
    report = coverage_by_year(daily, demo["sites"].site_id, start="2022-01-01", end="2025-12-31")
    assert report[report.year.eq(2022)].paired_days.sum() == 0
    assert report[report.year.eq(2024)].expected_days.sum() == 16 * 366
    assert report[report.year.eq(2024)].coverage_pct.eq(100).all()


@pytest.mark.parametrize("column,value", [("precipitation_sum", float("inf")), ("wind_direction_10m_dominant", 999), ("precipitation_sum", -1)])
def test_reject_bad_numeric(demo, column, value):
    df = demo["products"]["weather_reanalysis"].head(1).copy()
    df[column] = value
    with pytest.raises(ValueError):
        validate_product(df, "weather_reanalysis")


def test_reject_duplicates(demo):
    df = demo["products"]["weather_reanalysis"].head(1)
    with pytest.raises(ValueError, match="duplicate"):
        validate_product(pd.concat([df, df]), "weather_reanalysis")


def test_unknown_site_and_missing_catch_not_zero():
    text = "site_id,date_local,species,fish_category,catch_weight_kg,source,source_url\nmissing,2026-10-01,balaya,large_pelagic,20,Research,https://example.org\n"
    with pytest.raises(ValueError, match="harbour"):
        validate_optional_csv(text.encode(), "catch")
    with pytest.raises(ValueError):
        validate_optional_csv(text.replace("missing", "galle").replace(",20,", ",," ).encode(), "catch")


def test_optional_ocean_contract():
    text = "site_id,date_local,sea_surface_temperature,measurement_kind,source,source_url\ngalle,2026-10-01,28.1,model_estimate,Research,https://example.org\n"
    df = validate_optional_csv(text.encode(), "ocean")
    assert len(df) == 1 and not df.is_synthetic.any()


def test_species_profile_requires_provenance():
    text = "species,common_name,fish_category,depth_zone,seasonal_note,source,source_url\nbalaya,Skipjack tuna,large_pelagic,Not supplied,Not supplied,User reference,https://example.org\n"
    assert len(validate_profiles(text.encode())) == 1
    with pytest.raises(ValueError):
        validate_profiles(text.replace("User reference", "").encode())


@pytest.mark.parametrize("kind", ["CSV", "JSON", "Parquet"])
def test_export_roundtrip(demo, kind):
    original = build_daily(demo).head(3)
    raw = export_bytes(original, kind)
    if kind == "CSV":
        restored = pd.read_csv(BytesIO(raw))
    elif kind == "JSON":
        restored = pd.read_json(BytesIO(raw))
    else:
        restored = pd.read_parquet(BytesIO(raw))
    assert len(restored) == 3
    assert restored.is_synthetic.all()
    assert restored.weather_model.eq("era5").all()
