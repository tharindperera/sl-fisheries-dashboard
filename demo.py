"""Deterministic synthetic UI fixtures. Never written to HF or mixed into live data."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data import PRODUCTS, assemble_bundle, colombo_today

SPECIES = [
    ("salaya", "Sardine group", "small_pelagic"),
    ("hurulla", "Local small-fish market label", "small_pelagic"),
    ("handalla", "Anchovy group", "small_pelagic"),
    ("kumbala", "Mackerel group", "small_pelagic"),
    ("kelawalla", "Yellowfin tuna", "large_pelagic"),
    ("balaya", "Skipjack tuna", "large_pelagic"),
    ("thalapath", "User-provided large-fish market label", "large_pelagic"),
    ("thora", "Seer-fish group", "large_pelagic"),
]


def generate_demo(today=None):
    today = colombo_today() if today is None else pd.Timestamp(today)
    sites = pd.read_csv(Path(__file__).parent / "sample_sites.csv")
    rng = np.random.default_rng(20261009)
    dates = pd.date_range(today - pd.DateOffset(years=3), today + pd.Timedelta(days=6))
    frame = pd.MultiIndex.from_product([sites.site_id, dates], names=["site_id", "date_local"]).to_frame(index=False)
    n = len(frame)
    season = np.sin(2 * np.pi * frame.date_local.dt.dayofyear.to_numpy() / 365.25)
    mean_temp = 27.8 + 0.9 * season + rng.normal(0, 0.7, n)
    frame["temperature_2m_mean"] = mean_temp
    frame["temperature_2m_max"] = mean_temp + rng.uniform(1, 4, n)
    frame["temperature_2m_min"] = mean_temp - rng.uniform(1, 3, n)
    frame["precipitation_sum"] = np.where(rng.random(n) < 0.4, rng.gamma(1.6, 5, n), 0)
    frame["precipitation_hours"] = np.minimum(24, frame.precipitation_sum / 3)
    frame["wind_speed_10m_mean"] = np.maximum(0, 4.2 + 1.8 * season + rng.normal(0, 1, n))
    frame["wind_speed_10m_max"] = frame.wind_speed_10m_mean + rng.uniform(0.2, 6, n)
    frame["wind_direction_10m_dominant"] = rng.uniform(0, 360, n)
    frame["relative_humidity_2m_mean"] = rng.uniform(65, 94, n)
    frame["pressure_msl_mean"] = rng.normal(1010, 2, n)
    frame["wave_height_max"] = np.maximum(0.2, 1.5 + 0.6 * season + rng.normal(0, 0.5, n))
    frame["wave_period_max"] = rng.uniform(4, 13, n)
    frame["wave_direction_dominant"] = rng.uniform(0, 360, n)
    parts = {}
    for name, (metrics, model) in PRODUCTS.items():
        if name.endswith("reanalysis"):
            mask = frame.date_local < today - pd.Timedelta(days=5)
        elif name.endswith("recent"):
            mask = frame.date_local.between(today - pd.Timedelta(days=7), today - pd.Timedelta(days=1))
        else:
            mask = frame.date_local >= today
        product = frame.loc[mask, ["site_id", "date_local"] + metrics].copy()
        product["model"] = model
        product["snapshot_id"] = today.strftime("%Y-%m-%d") if name.endswith("forecasts") else "historical"
        parts[name] = [product]
    bundle = assemble_bundle(parts, sites, "SYNTHETIC_DEMO", last_modified=datetime.now(timezone.utc).isoformat())
    for product in bundle["products"].values():
        product["is_synthetic"] = True
    bundle["is_demo"] = True
    past = frame[frame.date_local < today].copy()
    ocean = past[["site_id", "date_local"]].copy()
    ocean["sea_surface_temperature"] = 28 + rng.normal(0, 0.7, len(ocean))
    ocean["chlorophyll_a"] = rng.lognormal(-1, 0.5, len(ocean))
    ocean["salinity"] = rng.uniform(32, 35, len(ocean))
    ocean["current_speed"] = rng.uniform(0.05, 0.8, len(ocean))
    ocean["measurement_kind"] = "synthetic_demo"
    ocean["source"] = "Synthetic UI fixture"
    ocean["source_url"] = "demo://not-an-observation"
    ocean["is_synthetic"] = True
    catch = past[["site_id", "date_local"]].copy()
    species = [SPECIES[i % len(SPECIES)] for i in range(len(catch))]
    catch["species"] = [x[0] for x in species]
    catch["fish_category"] = [x[2] for x in species]
    catch["catch_weight_kg"] = rng.gamma(4, 40, len(catch))
    catch["source"] = "Synthetic UI fixture"
    catch["source_url"] = "demo://not-a-landing-record"
    catch["is_synthetic"] = True
    bundle["ocean"] = ocean
    bundle["catch"] = catch
    return bundle
