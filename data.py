"""Read-only HF connector and daily-table contracts, also used by Colab."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import re
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ID = "tharinduperera/sl-fisheries-weather-daily"
SITE_IDS = {
    "dikkowita", "beruwala", "negombo", "tangalle", "mirissa", "nilwella",
    "kudawella", "puranawella", "puttalam", "chilaw", "kalpitiya",
    "ambalangoda", "galle", "trincomalee", "valaichchenai", "myliddy",
}
KEYS = ["site_id", "date_local", "model", "snapshot_id"]
WEATHER = [
    "precipitation_sum", "precipitation_hours", "wind_speed_10m_max",
    "wind_speed_10m_mean", "wind_direction_10m_dominant", "temperature_2m_mean",
    "temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean",
    "pressure_msl_mean",
]
MARINE = ["wave_height_max", "wave_period_max", "wave_direction_dominant"]
PRODUCTS = {
    "weather_reanalysis": (WEATHER, "era5"),
    "marine_reanalysis": (MARINE, "era5_ocean"),
    "weather_recent": (WEATHER, "ecmwf_ifs025"),
    "marine_recent": (MARINE, "ecmwf_wam"),
    "weather_forecasts": (WEATHER, "ecmwf_ifs025"),
    "marine_forecasts": (MARINE, "ecmwf_wam"),
}
PRODUCT_PATH = re.compile(r"^data/(" + "|".join(PRODUCTS) + r")/.*\.parquet$")
MAX_FILE_BYTES = 64 * 1024 * 1024


def colombo_today():
    return pd.Timestamp(datetime.now(ZoneInfo("Asia/Colombo")).date())


def http_bytes(url):
    """Bounded, retrying public GET. Does not use HF credentials or write APIs."""
    with requests.Session() as session:
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        with session.get(url, timeout=(10, 45), stream=True) as response:
            response.raise_for_status()
            output = BytesIO()
            for chunk in response.iter_content(65536):
                output.write(chunk)
                if output.tell() > MAX_FILE_BYTES:
                    raise ValueError("Remote file exceeds the configured 64 MiB limit")
            return output.getvalue()


def repo_info(repo_id=REPO_ID):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo_id):
        raise ValueError("Expected an HF owner/dataset identifier")
    info = json.loads(http_bytes(f"https://huggingface.co/api/datasets/{repo_id}"))
    if not re.fullmatch(r"[0-9a-f]{40}", info.get("sha", "")):
        raise ValueError("HF returned no immutable dataset revision")
    return info


def validate_sites(sites):
    needed = {"site_id", "name", "lat_land", "lon_land", "lat_sea", "lon_sea"}
    if not needed.issubset(sites):
        raise ValueError(f"Site registry is missing {needed - set(sites)}")
    if sites.site_id.duplicated().any() or set(sites.site_id) != SITE_IDS:
        raise ValueError("The dataset must contain exactly the 16 configured site IDs")
    for column in ["lat_land", "lon_land", "lat_sea", "lon_sea"]:
        sites[column] = pd.to_numeric(sites[column], errors="raise")
        if not np.isfinite(sites[column]).all():
            raise ValueError(f"Nonfinite coordinate in {column}")
    for column in ["lat_land", "lat_sea"]:
        if not sites[column].between(5, 11).all():
            raise ValueError("Latitude outside the Sri Lanka sampling region")
    for column in ["lon_land", "lon_sea"]:
        if not sites[column].between(78, 83).all():
            raise ValueError("Longitude outside the Sri Lanka sampling region")
    return sites


def validate_product(frame, product):
    columns, model = PRODUCTS[product]
    needed = set(KEYS + columns)
    if not needed.issubset(frame):
        raise ValueError(f"{product}: missing columns {needed - set(frame)}")
    df = frame.copy()
    if df[KEYS].isna().any().any():
        raise ValueError(f"{product}: null primary key")
    df["date_local"] = pd.to_datetime(df.date_local, format="%Y-%m-%d", errors="raise")
    if not df.date_local.eq(df.date_local.dt.normalize()).all():
        raise ValueError(f"{product}: dates must be daily local dates")
    if not set(df.site_id).issubset(SITE_IDS) or not df.model.eq(model).all():
        raise ValueError(f"{product}: unknown site or unexpected model")
    if df.duplicated(KEYS).any():
        raise ValueError(f"{product}: duplicate full primary keys; inspect the source")
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="raise")
        values = df[column].dropna()
        if not np.isfinite(values).all():
            raise ValueError(f"{product}: infinite {column}")
        if "direction" in column and not values.between(0, 360).all():
            raise ValueError(f"{product}: invalid direction {column}")
        if column.startswith(("precipitation", "wind_speed", "wave_height", "wave_period")) and (values < 0).any():
            raise ValueError(f"{product}: negative {column}")
        if "temperature" in column and not values.between(-90, 60).all():
            raise ValueError(f"{product}: invalid temperature")
        if column == "relative_humidity_2m_mean" and not values.between(0, 100).all():
            raise ValueError(f"{product}: humidity outside 0 to 100")
        if column == "precipitation_hours" and not values.between(0, 24).all():
            raise ValueError(f"{product}: rainfall duration outside 0 to 24 hours")
        if column == "pressure_msl_mean" and not values.between(800, 1100).all():
            raise ValueError(f"{product}: invalid sea-level pressure")
    weather_complete = df[columns].notna().all(axis=1)
    if product.startswith("weather"):
        ordered = (df.temperature_2m_min <= df.temperature_2m_mean) & (df.temperature_2m_mean <= df.temperature_2m_max)
        if (~ordered & weather_complete).any():
            raise ValueError(f"{product}: reversed temperature bounds")
    df["complete_core"] = weather_complete
    df["product"] = product
    df["is_synthetic"] = False
    return df


def assemble_bundle(parts, sites, revision, repo_id=REPO_ID, last_modified=None):
    products = {}
    for product, frames in parts.items():
        if frames:
            products[product] = validate_product(pd.concat(frames, ignore_index=True), product)
    if not {"weather_reanalysis", "marine_reanalysis"}.issubset(products):
        raise ValueError("Both historical weather and marine products are required")
    if products["weather_reanalysis"].empty or products["marine_reanalysis"].empty:
        raise ValueError("No historical daily records have been published yet")
    return {
        "products": products, "sites": validate_sites(sites.copy()),
        "revision": revision, "repo_id": repo_id, "last_modified": last_modified,
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(), "is_demo": False,
    }


def load_hf_bundle(info, repo_id=REPO_ID):
    """Read all six products from raw HF resolve URLs at one captured commit."""
    revision = info["sha"]
    names = [x["rfilename"] for x in info["siblings"] if PRODUCT_PATH.fullmatch(x["rfilename"])]
    if len(names) > 300:
        raise ValueError("More than 300 shards; configure a partitioned database connector")
    def read_file(name):
        content = http_bytes(f"https://huggingface.co/datasets/{repo_id}/resolve/{revision}/{name}")
        # ParquetFile avoids accidental Hive 'year' columns or schema inference.
        return name.split("/")[1], pq.ParquetFile(BytesIO(content)).read().to_pandas()
    parts = {x: [] for x in PRODUCTS}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for product, frame in pool.map(read_file, names):
            parts[product].append(frame)
    content = http_bytes(f"https://huggingface.co/datasets/{repo_id}/resolve/{revision}/metadata/sites.csv")
    return assemble_bundle(parts, pd.read_csv(BytesIO(content)), revision, repo_id, info.get("lastModified"))


def load_local_snapshot(root, revision="local_snapshot"):
    """For offline QA of actual downloaded data; no API calls or credentials."""
    root = Path(root)
    parts = {x: [] for x in PRODUCTS}
    for product in PRODUCTS:
        for path in sorted((root / "data" / product).rglob("*.parquet")):
            parts[product].append(pq.ParquetFile(path).read().to_pandas())
    return assemble_bundle(parts, pd.read_csv(root / "metadata/sites.csv"), revision)


def select_history(bundle, domain, include_recent=False, today=None):
    today = colombo_today() if today is None else pd.Timestamp(today)
    names = [f"{domain}_reanalysis"] + ([f"{domain}_recent"] if include_recent else [])
    frames = [bundle["products"][name] for name in names if name in bundle["products"]]
    df = pd.concat(frames, ignore_index=True)
    df = df[df.date_local < today].copy()
    df["_rank"] = df.complete_core.astype(int) * 2 + df["product"].str.endswith("reanalysis").astype(int)
    df["_vintage"] = pd.to_datetime(df.snapshot_id, errors="coerce", utc=True)
    # Unknown vintage is not newer than a timestamped one.
    df = df.sort_values(["_rank", "_vintage", "snapshot_id"], na_position="first")
    df = df.drop_duplicates(["site_id", "date_local"], keep="last").drop(columns=["_rank", "_vintage"])
    return df


def join_domains(weather, marine, sites, revision, forecast=False):
    keys = ["site_id", "date_local"]
    if forecast:
        weather = weather.rename(columns={"snapshot_id": "forecast_vintage"})
        marine = marine.rename(columns={"snapshot_id": "forecast_vintage"})
        keys += ["forecast_vintage"]
    def rename(frame, domain):
        return frame.rename(columns={
            "model": f"{domain}_model", "snapshot_id": f"{domain}_snapshot_id",
            "product": f"{domain}_product", "complete_core": f"{domain}_complete",
            "is_synthetic": f"{domain}_synthetic",
        })
    df = rename(weather, "weather").merge(rename(marine, "marine"), on=keys, how="outer", validate="one_to_one", indicator="domain_match")
    # Metadata changes must be versioned upstream; do not silently infer new coordinates.
    df = df.merge(sites, on="site_id", how="left", validate="many_to_one")
    for column in ["weather_complete", "marine_complete", "weather_synthetic", "marine_synthetic"]:
        df[column] = df[column].fillna(False).astype(bool)
    df["complete_pair"] = df.weather_complete & df.marine_complete
    df["is_synthetic"] = df.weather_synthetic | df.marine_synthetic
    df["hf_revision"] = revision
    df["source_kind"] = "forecast" if forecast else np.where(
        df.weather_product.eq("weather_recent") | df.marine_product.eq("marine_recent"),
        "provisional_recent", "reanalysis",
    )
    if df.is_synthetic.any():
        df.loc[df.is_synthetic, "source_kind"] = "synthetic_demo"
    return df.sort_values(keys).reset_index(drop=True)


def build_daily(bundle, include_recent=False, today=None):
    return join_domains(select_history(bundle, "weather", include_recent, today), select_history(bundle, "marine", include_recent, today), bundle["sites"], bundle["revision"])


def build_forecasts(bundle):
    weather = bundle["products"].get("weather_forecasts")
    marine = bundle["products"].get("marine_forecasts")
    if weather is None or marine is None:
        return pd.DataFrame()
    return join_domains(weather, marine, bundle["sites"], bundle["revision"], forecast=True)


def coverage_by_year(daily, site_ids, start="2010-01-01", end=None):
    """Coverage uses expected dates, including missing entire years and domains."""
    start = pd.Timestamp(start)
    end = colombo_today() - pd.Timedelta(days=1) if end is None else pd.Timestamp(end)
    rows = []
    for year in range(start.year, end.year + 1):
        lower, upper = max(start, pd.Timestamp(year, 1, 1)), min(end, pd.Timestamp(year, 12, 31))
        expected = max(0, (upper - lower).days + 1)
        for site in sorted(site_ids):
            mask = daily.site_id.eq(site) & daily.date_local.between(lower, upper)
            if not mask.any():
                values = {"available_rows": 0, "weather_days": 0, "marine_days": 0, "paired_days": 0}
            else:
                part = daily.loc[mask]
                values = {"available_rows": len(part), "weather_days": int(part.weather_complete.sum()), "marine_days": int(part.marine_complete.sum()), "paired_days": int(part.complete_pair.sum())}
            rows.append({"site_id": site, "year": year, "expected_days": expected, **values,
                         "missing_pair_days": expected - values["paired_days"],
                         "coverage_pct": round(100 * values["paired_days"] / expected, 2) if expected else 0})
    return pd.DataFrame(rows)


def indicator_status(frame, wave_limit=2.0, wind_limit=10.0):
    """Display filters, not vessel-specific sailing permission or official alerts."""
    valid = frame.wave_height_max.notna() & frame.wind_speed_10m_max.notna()
    elevated = (frame.wave_height_max >= wave_limit) | (frame.wind_speed_10m_max >= wind_limit)
    high = (frame.wave_height_max >= wave_limit * 1.5) | (frame.wind_speed_10m_max >= wind_limit * 1.5)
    return pd.Series(np.select([~valid, high, elevated], ["Missing indicators", "Higher values", "Elevated values"], default="Below display thresholds"), index=frame.index)


def validate_optional_csv(content, kind, site_ids=SITE_IDS):
    df = pd.read_csv(BytesIO(content))
    required = {"site_id", "date_local", "source", "source_url"}
    if kind == "catch":
        required |= {"species", "fish_category", "catch_weight_kg"}
    else:
        required |= {"measurement_kind"}
    if not required.issubset(df):
        raise ValueError(f"Missing {required - set(df)}")
    if df[list(required)].isna().any().any():
        raise ValueError("Required identifiers/provenance cannot be empty")
    if len(df) > 200000:
        raise ValueError("CSV exceeds the 200,000-row session limit")
    if not set(df.site_id).issubset(site_ids):
        raise ValueError("CSV contains an unconfigured harbour")
    df["date_local"] = pd.to_datetime(df.date_local, format="%Y-%m-%d", errors="raise")
    keys = ["site_id", "date_local"] + (["species"] if kind == "catch" else [])
    if df.duplicated(keys).any():
        raise ValueError("Aggregate repeated events to one site/date/species before upload")
    numeric = ["catch_weight_kg"] if kind == "catch" else [x for x in ["sea_surface_temperature", "chlorophyll_a", "salinity", "current_speed"] if x in df]
    if not numeric:
        raise ValueError("Ocean CSV has none of the supported ocean variables")
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors="raise")
        values = df[column].dropna()
        if not np.isfinite(values).all() or (column != "sea_surface_temperature" and (values < 0).any()):
            raise ValueError(f"Invalid numeric {column}")
        if column == "sea_surface_temperature" and not values.between(-5, 45).all():
            raise ValueError("SST outside -5 to 45 Celsius")
    if kind == "catch":
        if not set(df.fish_category).issubset({"small_pelagic", "large_pelagic", "demersal", "other"}):
            raise ValueError("Unknown fish category")
        if df.catch_weight_kg.isna().any():
            raise ValueError("Missing catch is not zero catch")
    elif not set(df.measurement_kind).issubset({"observation", "model_estimate", "satellite_estimate"}):
        raise ValueError("measurement_kind must be observation, model_estimate or satellite_estimate")
    df["is_synthetic"] = False
    return df


def validate_profiles(content):
    df = pd.read_csv(BytesIO(content))
    needed = {"species", "common_name", "fish_category", "depth_zone", "seasonal_note", "source", "source_url"}
    if not needed.issubset(df) or df[list(needed)].isna().any().any():
        raise ValueError("Species catalogue needs identity, category, depth/season notes and source provenance")
    if df.species.duplicated().any() or len(df) > 1000:
        raise ValueError("Species catalogue must have at most 1,000 unique species/market labels")
    return df


def export_bytes(frame, format_name):
    if len(frame) > 200000:
        raise ValueError("Narrow your export below 200,000 rows")
    if format_name == "CSV":
        out = frame.copy()
        for col in out.select_dtypes(include=["datetime"]).columns:
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        return out.to_csv(index=False).encode("utf-8-sig")
    if format_name == "JSON":
        return frame.to_json(orient="records", date_format="iso").encode()
    out = BytesIO()
    frame.to_parquet(out, index=False, compression="snappy")
    return out.getvalue()
