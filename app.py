"""Sri Lanka fisheries dashboard. Run: streamlit run app.py"""
from functools import partial
import inspect
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from data import (
    REPO_ID, PRODUCTS, WEATHER, MARINE, build_daily, build_forecasts,
    colombo_today, export_bytes, indicator_status,
    load_hf_bundle, load_local_snapshot, repo_info, validate_optional_csv, validate_profiles,
)
from demo import SPECIES, generate_demo

st.set_page_config(page_title="Sri Lanka Fisheries Observatory", page_icon="🌊", layout="wide")

LABELS = {
    "precipitation_sum": ("Daily precipitation", "mm"),
    "precipitation_hours": ("Hours with precipitation", "hours"),
    "wind_speed_10m_max": ("Daily maximum wind speed", "m/s"),
    "wind_speed_10m_mean": ("Daily mean wind speed", "m/s"),
    "wind_direction_10m_dominant": ("Dominant wind direction", "degrees"),
    "temperature_2m_mean": ("Mean air temperature", "°C"),
    "temperature_2m_max": ("Maximum air temperature", "°C"),
    "temperature_2m_min": ("Minimum air temperature", "°C"),
    "relative_humidity_2m_mean": ("Mean relative humidity", "%"),
    "pressure_msl_mean": ("Mean sea-level pressure", "hPa"),
    "wave_height_max": ("Daily maximum significant wave height", "m"),
    "wave_period_max": ("Daily maximum wave period", "s"),
    "wave_direction_dominant": ("Dominant wave direction", "degrees"),
    "sea_surface_temperature": ("Sea surface temperature", "°C"),
    "chlorophyll_a": ("Chlorophyll-a concentration", "mg/m³"),
    "salinity": ("Salinity", "PSU"),
    "current_speed": ("Ocean current speed", "m/s"),
}
COLORS = {"Higher values": [203, 69, 60, 230], "Elevated values": [221, 161, 54, 230],
          "Below display thresholds": [0, 127, 122, 230], "Missing indicators": [148, 163, 184, 210]}
FULL_WIDTH = {"use_container_width": True} if "use_container_width" in inspect.signature(st.button).parameters else {"width": "stretch"}


def apply_theme_css(is_dark):
    if is_dark:
        st.markdown(
            """
            <style>
            .stApp {
                background-color: #0c1322 !important;
                color: #f1f5f9 !important;
            }
            section[data-testid="stSidebar"] {
                background-color: #070d18 !important;
                border-right: 1px solid #1e293b !important;
            }
            div[data-testid="stMetricValue"] {
                color: #38bdf8 !important;
            }
            div[data-testid="stMetricLabel"] {
                color: #94a3b8 !important;
            }
            div[data-testid="stExpander"] {
                background-color: #111a2e !important;
                border: 1px solid #1e293b !important;
                border-radius: 8px;
            }
            div[data-testid="stDataFrame"] {
                background-color: #111a2e !important;
            }
            button[data-baseweb="tab"] {
                color: #94a3b8 !important;
            }
            button[data-baseweb="tab"][aria-selected="true"] {
                color: #38bdf8 !important;
                border-bottom-color: #38bdf8 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            .stApp {
                background-color: #f8fafc !important;
                color: #0f172a !important;
            }
            section[data-testid="stSidebar"] {
                background-color: #f1f5f9 !important;
                border-right: 1px solid #e2e8f0 !important;
            }
            div[data-testid="stMetricValue"] {
                color: #007F7A !important;
            }
            div[data-testid="stMetricLabel"] {
                color: #475569 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def build_combined_timeline(history, forecasts):
    """Combine past historical records with deduplicated latest forecasts for a seamless timeline."""
    if forecasts.empty:
        return history.copy()
    if history.empty:
        return forecasts.copy()
    latest_fc = forecasts.sort_values("forecast_vintage").drop_duplicates(["site_id", "date_local"], keep="last")
    future_fc = latest_fc[~latest_fc.date_local.isin(history.date_local)]
    combined = pd.concat([history, future_fc], ignore_index=True)
    return combined.sort_values(["site_id", "date_local"]).reset_index(drop=True)


@st.cache_data(ttl=240, max_entries=4, show_spinner=False)
def cached_info(repo):
    return repo_info(repo)


@st.cache_data(ttl=900, max_entries=2, show_spinner="Loading one verified HF snapshot...")
def cached_live(info, repo):
    return load_hf_bundle(info, repo)


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def cached_local(folder, revision):
    return load_local_snapshot(folder, revision)


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def cached_demo(day):
    return generate_demo(day)


fragment = getattr(st, "fragment", getattr(st, "experimental_fragment", None))
if fragment is None:
    def fragment(**kwargs):
        def decorator(f):
            return f
        return decorator


@fragment(run_every="5m")
def watch_revision(repo, active_revision, enabled):
    if not enabled or os.getenv("FISHERIES_LOCAL_SNAPSHOT"):
        return
    try:
        new_revision = cached_info(repo)["sha"]
        if new_revision != active_revision:
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
        st.caption("Open sessions check HF for new dataset commits every 5 minutes.")
    except Exception:
        st.caption("HF update check unavailable. Retry or switch to the labelled demo.")


def fmt(value, digits=1):
    return "Not available" if pd.isna(value) else f"{value:.{digits}f}"


def paginate(frame, key):
    if frame.empty:
        st.info("No records match these filters.")
        return
    size = st.selectbox("Rows per page", [25, 50, 100, 250], index=2, key=f"{key}_size")
    pages = max(1, math.ceil(len(frame) / size))
    page_key = f"{key}_page"
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=page_key)
    st.caption(f"{len(frame):,} matching rows; page {page} of {pages}")
    st.dataframe(frame.iloc[(page - 1) * size:page * size], hide_index=True, **FULL_WIDTH)


def downloads(frame, key, demo=False):
    if frame.empty:
        return
    if len(frame) > 200000:
        st.info("Select fewer than 200,000 rows for an in-browser export. Use Colab for larger exports.")
        return
    prefix = "SYNTHETIC_DEMO_" if demo else ""
    for column, kind, mime, extension in zip(st.columns(3), ["CSV", "JSON", "Parquet"],
                                           ["text/csv", "application/json", "application/octet-stream"], ["csv", "json", "parquet"]):
        data_fn = partial(export_bytes, frame, kind)
        try:
            # Streamlit 1.65 defers callable serialization until a download is requested.
            column.download_button(f"Download {kind}", data=data_fn,
                                   file_name=f"{prefix}{key}.{extension}", mime=mime,
                                   key=f"{key}_{kind}", on_click="ignore", **FULL_WIDTH)
        except (TypeError, RuntimeError):
            column.download_button(f"Download {kind}", data=data_fn(),
                                   file_name=f"{prefix}{key}.{extension}", mime=mime,
                                   key=f"{key}_{kind}", **FULL_WIDTH)


def filtered(frame, sites, dates, severity=None, wave=2, wind=10):
    if frame.empty or not sites or len(dates) != 2:
        return frame.iloc[:0].copy()
    result = frame[frame.site_id.isin(sites) & frame.date_local.between(pd.Timestamp(dates[0]), pd.Timestamp(dates[1]))].copy()
    if "wave_height_max" in result:
        result["indicator_status"] = indicator_status(result, wave, wind)
        if severity is not None:
            result = result[result.indicator_status.isin(severity)]
    return result


def map_selected():
    event = st.session_state.get("harbour_map", {})
    objects = event.get("selection", {}).get("objects", {})
    for layer in ["land-points", "sea-points"]:
        if objects.get(layer):
            selected_site = objects[layer][0]["site_id"]
            st.session_state["focus_site"] = selected_site
            st.session_state["coastal_location_picker"] = selected_site
            st.session_state["_prev_focus_site"] = selected_site
            return


def render_map(sites, forecasts, history, target_day, wave, wind, is_dark=False, layer_style="Combined (Heatmap + Markers)"):
    chosen = forecasts[forecasts.date_local.eq(pd.Timestamp(target_day))].copy() if not forecasts.empty else forecasts
    if not chosen.empty:
        chosen = chosen.sort_values("forecast_vintage").drop_duplicates("site_id", keep="last")
    else:
        chosen = history[history.date_local.eq(pd.Timestamp(target_day))].copy()
    if not chosen.empty:
        chosen["status"] = indicator_status(chosen, wave, wind)
        points = sites.merge(chosen[["site_id", "status"]], on="site_id", how="left", validate="one_to_one")
    else:
        points = sites.copy()
        points["status"] = "Missing indicators"
    points["status"] = points.status.fillna("Missing indicators")
    points["color"] = points.status.map(COLORS)
    focus = st.session_state.get("focus_site", "beruwala")
    arc = points[points.site_id.eq(focus)]

    # Heatmap indicating sampling point density and coastal monitoring footprint
    heat_records = []
    for _, row in points.iterrows():
        heat_records.append({"lon": float(row["lon_land"]), "lat": float(row["lat_land"]), "weight": 1.5})
        heat_records.append({"lon": float(row["lon_sea"]), "lat": float(row["lat_sea"]), "weight": 1.5})
    heat_df = pd.DataFrame(heat_records)

    heat_layer = pdk.Layer(
        "HeatmapLayer",
        id="location-heat",
        data=heat_df,
        get_position="[lon, lat]",
        get_weight="weight",
        radius_pixels=65,
        intensity=1.6,
        threshold=0.03,
        color_range=[
            [0, 127, 122, 100],   # Emerald / Teal
            [46, 170, 150, 150],  # Cyan
            [221, 161, 54, 200],  # Amber
            [235, 120, 60, 230],  # Orange
            [203, 69, 60, 255],   # Coral Red
        ],
    )
    land_layer = pdk.Layer(
        "ScatterplotLayer", id="land-points", data=points, get_position="[lon_land, lat_land]",
        get_fill_color="color", get_radius=4200, radius_min_pixels=6, radius_max_pixels=15,
        pickable=True, auto_highlight=True
    )
    sea_layer = pdk.Layer(
        "ScatterplotLayer", id="sea-points", data=points, get_position="[lon_sea, lat_sea]",
        get_fill_color=[75, 125, 165, 160], get_radius=2800, radius_min_pixels=4,
        pickable=True, auto_highlight=True
    )
    arc_layer = pdk.Layer(
        "ArcLayer", id="sampling-pair", data=arc,
        get_source_position="[lon_land, lat_land]", get_target_position="[lon_sea, lat_sea]",
        get_source_color=[0, 127, 122], get_target_color=[75, 125, 165], get_width=3
    )

    if layer_style == "Location heatmap only":
        layers = [heat_layer, arc_layer]
    elif layer_style == "Sampling markers only":
        layers = [land_layer, sea_layer, arc_layer]
    else:  # Combined
        layers = [heat_layer, land_layer, sea_layer, arc_layer]

    deck = pdk.Deck(
        layers=layers,
        map_provider="carto",
        map_style="dark" if is_dark else "light",
        initial_view_state=pdk.ViewState(latitude=7.75, longitude=80.65, zoom=6.4),
        tooltip={"text": "{name}\n{site_id}\n{status}"}
    )
    params = inspect.signature(st.pydeck_chart).parameters
    map_kwargs = {}
    if "use_container_width" in params:
        map_kwargs["use_container_width"] = True
    elif "width" in params:
        map_kwargs["width"] = "stretch"
    if "height" in params:
        map_kwargs["height"] = 490
    if "key" in params:
        map_kwargs["key"] = "harbour_map"
    if "on_select" in params:
        map_kwargs.update({"on_select": map_selected, "selection_mode": "single-object"})
    st.pydeck_chart(deck, **map_kwargs)
    st.caption("Click a land/sea point or choose from the dropdown above to focus on a harbour. Heatmap layer visualizes coastal sampling coverage across Sri Lanka.")


def plot_series(frame, metric, start, end, monthly=False, label=None, template="plotly_white"):
    name, unit = LABELS[metric]
    index = pd.date_range(start, end, freq="MS" if monthly else "D")
    if monthly:
        values = frame.set_index("date_local")[metric].resample("MS")
        series = values.sum(min_count=1) if metric == "precipitation_sum" else values.mean()
        name += " (monthly sum)" if metric == "precipitation_sum" else " (monthly mean of daily values)"
    else:
        series = frame.set_index("date_local")[metric]
    series = series.reindex(index)
    color = "#38bdf8" if template == "plotly_dark" else "#007F7A"
    fig = go.Figure(go.Scatter(x=series.index, y=series, mode="lines", connectgaps=False,
                              line={"color": color, "width": 2.5}, name=name))
    fig.update_layout(title=label or name, yaxis_title=unit, xaxis_title=None, height=320,
                      margin={"l": 10, "r": 10, "t": 45, "b": 10}, template=template,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, **FULL_WIDTH)


def field_guide():
    with st.expander("Field guide and data dictionary"):
        st.markdown("Daily wind and wave indicators can help describe changing conditions. Harbour-mouth conditions, vessels and official warnings require separate information. ERA5 is a model-based reconstruction of past weather, not a direct observation at every harbour. Recent IFS values are provisional model estimates.")
        rows = []
        for column, (name, unit) in LABELS.items():
            available = column in WEATHER + MARINE
            method = "Daily model aggregation" if available else "Optional documented ocean connector"
            relevance = "Track weather and marine conditions alongside fish-market records"
            if "direction" in column:
                relevance = "Circular value: use sine/cosine or circular averaging, not ordinary degree averages"
            if column == "wave_period_max":
                relevance = "Longer periods change how waves approach the coast; this value alone does not determine launch safety"
            if column == "sea_surface_temperature":
                relevance = "Describes surface-water conditions; species relationships require location-specific evidence"
            rows.append({"column": column, "description": name, "unit": unit, "method": method,
                          "in_current_HF_schema": available, "relevance": relevance})
        st.dataframe(pd.DataFrame(rows), hide_index=True, **FULL_WIDTH)
        st.caption("wind_speed_10m_max is maximum wind speed, not wind gusts. wave_height_max is the daily maximum of significant wave height, not the height of the largest individual wave. The current marine schema does not separate swell from wind waves.")
        st.link_button("Open-Meteo variable definitions", "https://open-meteo.com/en/docs/marine-weather-api")


def colab_code(repo, revision):
    source = (Path(__file__).parent / "data.py").read_text(encoding="utf-8")
    suffix = f'''
# Raw data comes from https://huggingface.co/datasets/{repo}/resolve/<commit>/...
REPO = {repo!r}
PINNED_REVISION = {revision!r}  # Set to None to capture the newest dataset commit.
info = repo_info(REPO)
if PINNED_REVISION:
    # Query the pinned revision's file inventory instead of the changing main branch.
    import urllib.parse
    info = json.loads(http_bytes(f"https://huggingface.co/api/datasets/{{REPO}}/revision/{{PINNED_REVISION}}"))
bundle = load_hf_bundle(info, REPO)
df_all = build_daily(bundle, include_recent=False)
coverage = coverage_by_year(df_all, bundle["sites"]["site_id"])
assert bundle["sites"]["site_id"].nunique() == 16
assert not df_all.duplicated(["site_id", "date_local"]).any()
print("HF commit:", bundle["revision"])
print(f"Loaded {{len(df_all):,}} merged harbour-days across {{df_all.site_id.nunique()}} sites")
print("Missing weather/marine pairs:", int((~df_all.complete_pair).sum()))
print("Entirely missing dates are counted in the coverage report, not filled with zero.")
df_all.info()
display(df_all.head())
display(coverage.groupby("year")[["expected_days", "paired_days", "missing_pair_days"]].sum())
df_all.to_parquet("sl_fisheries_daily_reanalysis.parquet", index=False, compression="snappy")
coverage.to_csv("sl_fisheries_coverage.csv", index=False)
# Optional: past provisional values, kept separate from df_all's ERA5 training baseline.
# df_operational = build_daily(bundle, include_recent=True)
# df_forecasts = build_forecasts(bundle)  # Separate forecast vintages, never train as realized weather.
'''
    return "%pip install -q pandas==3.0.6 numpy==2.4.6 pyarrow==25.0.1 requests==2.34.2 tzdata==2026.5\n" + source + suffix


def main():
    with st.sidebar:
        st.header("Observatory settings")
        theme_mode = st.radio("Theme", ["Light", "Dark"], horizontal=True, key="theme_mode", index=0)
        is_dark = (theme_mode == "Dark")
        st.divider()

    apply_theme_css(is_dark)
    plotly_template = "plotly_dark" if is_dark else "plotly_white"

    header_color = "#38bdf8" if is_dark else "#007F7A"
    st.markdown(f"<p style='color:{header_color};letter-spacing:0.14em;font-size:0.8rem;font-weight:700'>SRI LANKA · 16 FISHERIES SITES</p>", unsafe_allow_html=True)
    st.title("Fisheries observatory")
    st.write("Explore coastal weather, offshore waves and documented fishery records.")

    with st.sidebar:
        st.subheader("Data source")
        mode = st.selectbox("Data source", ["Live Hugging Face", "Synthetic demo"],
                            index=1 if os.getenv("DASHBOARD_DEFAULT_MODE") == "demo" else 0, key="data_mode")
        auto = st.toggle("Check for updates every 5 minutes", value=True)
        if st.button("Refresh HF now", **FULL_WIDTH):
            cached_info.clear()
            cached_live.clear()
            st.rerun()

    repo = os.getenv("FISHERIES_HF_REPO_ID", REPO_ID)
    fallback_error = None
    captured_info = None
    if mode == "Synthetic demo":
        bundle = cached_demo(str(colombo_today().date()))
    else:
        try:
            local = os.getenv("FISHERIES_LOCAL_SNAPSHOT")
            if local:
                bundle = cached_local(local, os.getenv("FISHERIES_SNAPSHOT_REVISION", "local_snapshot"))
            else:
                captured_info = cached_info(repo)
                bundle = cached_live(captured_info, repo)
        except Exception as exc:
            fallback_error = f"{type(exc).__name__}: {str(exc)[:220]}"
            bundle = cached_demo(str(colombo_today().date()))

    demo = bundle["is_demo"]
    if demo:
        st.warning("SYNTHETIC DEMO: all displayed weather, ocean and catch values are generated examples. Downloads are labelled synthetic. No demo records are published to HF.")
        if fallback_error:
            st.error("The live connector failed; the app is displaying its isolated demo fallback.")
            with st.expander("Live connector error"):
                st.code(fallback_error, language="text")
    else:
        st.success("HF DATA: model reanalysis, provisional recent estimates and separate forecast vintages.")

    sites = bundle["sites"].sort_values("name")
    ids = sites.site_id.tolist()
    names = sites.set_index("site_id").name.to_dict()
    history = build_daily(bundle, include_recent=True)
    reanalysis = build_daily(bundle)
    forecasts = build_forecasts(bundle)
    combined_timeline = build_combined_timeline(history, forecasts)

    watched_revision = captured_info["sha"] if captured_info else bundle["revision"]
    watch_revision(repo, watched_revision, auto and mode == "Live Hugging Face")
    st.caption(f"Dataset revision: {bundle['revision']} · Read at {bundle['loaded_at_utc']} · Daily dates: Asia/Colombo")

    stats = st.columns(4)
    stats[0].metric("Raw domain/vintage records", f"{sum(len(x) for x in bundle['products'].values()):,}")
    stats[1].metric("Merged reanalysis harbour-days", f"{len(reanalysis):,}")
    stats[2].metric("Fisheries sites", len(sites))
    stats[3].metric("Latest past daily date", str(history.date_local.max().date()))
    st.caption("Weather and marine rows describe the same site-day. Joining the domains reduces the row count; forecast vintages add separate records.")
    field_guide()

    # Session state initialization for focus site synchronization
    if "focus_site" not in st.session_state:
        st.session_state["focus_site"] = "beruwala"
    if "coastal_location_picker" not in st.session_state:
        st.session_state["coastal_location_picker"] = st.session_state["focus_site"]
    if "_prev_focus_site" not in st.session_state:
        st.session_state["_prev_focus_site"] = st.session_state["focus_site"]

    # Keep coastal picker synced with focus site if changed externally
    if st.session_state.get("_prev_focus_site") != st.session_state.get("focus_site"):
        st.session_state["coastal_location_picker"] = st.session_state["focus_site"]
        st.session_state["_prev_focus_site"] = st.session_state["focus_site"]

    def sync_coastal_to_focus():
        st.session_state["focus_site"] = st.session_state["coastal_location_picker"]
        st.session_state["_prev_focus_site"] = st.session_state["coastal_location_picker"]

    with st.sidebar:
        st.subheader("Filter & harbour selection")
        selected_sites = st.multiselect("Harbours / areas", ids, default=ids, format_func=names.get, key="selected_sites")
        focus = st.selectbox("Harbour detail", ids, format_func=names.get, key="focus_site")
        if focus != st.session_state.get("_prev_focus_site"):
            st.session_state["coastal_location_picker"] = focus
            st.session_state["_prev_focus_site"] = focus

        view = st.selectbox("Explorer product", ["Historical to Forecast (full timeline)", "Past: prefer reanalysis", "Reanalysis only", "Forecast vintages"])
        if view == "Historical to Forecast (full timeline)":
            source = combined_timeline
        elif view == "Forecast vintages":
            source = forecasts
        elif view == "Reanalysis only":
            source = reanalysis
        else:
            source = history

        if source.empty:
            st.info("This product is not published yet.")
            source = history.iloc[:0].copy()

        date_min = source.date_local.min().date() if not source.empty else history.date_local.min().date()
        date_max = source.date_local.max().date() if not source.empty else history.date_local.max().date()
        default_start = max(date_min, date_max - pd.Timedelta(days=29))
        date_key = f"dates_{view}"
        dates = st.date_input("Explorer date range", value=(default_start, date_max), min_value=date_min,
                              max_value=date_max, key=date_key)
        categories = st.multiselect("Catch category (catch records only)", ["small_pelagic", "large_pelagic", "demersal", "other"], default=["small_pelagic", "large_pelagic", "demersal", "other"])
        severity = st.multiselect("Weather indicator filter", list(COLORS), default=list(COLORS))
        with st.expander("Display thresholds"):
            wave = st.number_input("Wave display threshold (m)", 0.5, 10.0, 2.0, 0.5)
            wind = st.number_input("Wind display threshold (m/s)", 1.0, 40.0, 10.0, 1.0)
            st.caption("Illustrative filters, not official alerts or vessel-specific sailing limits.")
        st.divider()
        st.caption("Optional documented records. Uploads stay in this viewer's session.")
        catch_upload = st.file_uploader("Catch CSV", type="csv", key="catch_upload")
        ocean_upload = st.file_uploader("Ocean CSV (SST etc.)", type="csv", key="ocean_upload")
        profile_upload = st.file_uploader("Documented species-profile CSV", type="csv", key="profile_upload")

    catch, ocean = (bundle.get("catch", pd.DataFrame()), bundle.get("ocean", pd.DataFrame()))
    for uploaded, kind in [(catch_upload, "catch"), (ocean_upload, "ocean")]:
        if uploaded:
            if demo:
                st.warning("Switch to live mode to view real uploaded records; demo data stays separate.")
            else:
                try:
                    validated = validate_optional_csv(uploaded.getvalue(), kind)
                    if kind == "catch":
                        catch = validated
                    else:
                        ocean = validated
                except Exception as exc:
                    st.error(f"{kind.title()} CSV rejected: {exc}")

    tabs = st.tabs(["Harbour map", "Trends & fish profiles", "Explore and export", "Google Colab loader"])
    with tabs[0]:
        left, right = st.columns([1.35, 1])
        with left:
            st.subheader("Coastal sampling points")
            col_target, col_picker = st.columns([1, 1])
            with col_target:
                target = st.date_input(
                    "Map and daily-card date",
                    value=colombo_today().date(),
                    min_value=history.date_local.min().date(),
                    max_value=max(colombo_today().date(), forecasts.date_local.max().date() if not forecasts.empty else colombo_today().date()),
                    key="map_card_date"
                )
            with col_picker:
                coastal_loc = st.selectbox(
                    "Choose location",
                    ids,
                    format_func=names.get,
                    key="coastal_location_picker",
                    on_change=sync_coastal_to_focus
                )
                if coastal_loc != st.session_state.get("focus_site"):
                    st.session_state["focus_site"] = coastal_loc
                    st.session_state["_prev_focus_site"] = coastal_loc

            map_mode = st.radio(
                "Map layer display",
                ["Combined (Heatmap + Markers)", "Location heatmap only", "Sampling markers only"],
                horizontal=True,
                key="coastal_map_layer_style"
            )
            render_map(sites, forecasts, history, target, wave, wind, is_dark=is_dark, layer_style=map_mode)

        with right:
            st.subheader(names[focus])
            record = pd.DataFrame()
            if not forecasts.empty:
                record = forecasts[forecasts.site_id.eq(focus) & forecasts.date_local.eq(pd.Timestamp(target))].sort_values("forecast_vintage").tail(1)
            if record.empty:
                record = history[history.site_id.eq(focus) & history.date_local.eq(pd.Timestamp(target))]
            if record.empty:
                st.info(f"No daily values are available for {target}. Select another date; the app does not substitute an older day.")
            else:
                row = record.iloc[0]
                st.caption(f"{target} · {row.source_kind} · {row.weather_model} / {row.marine_model}")
                if "forecast_vintage" in row:
                    st.caption(f"Forecast vintage label: {row.forecast_vintage}. A date-only label does not establish an exact issuance time.")
                a, b = st.columns(2)
                a.metric("Daily maximum wave height", f"{fmt(row.wave_height_max)} m")
                b.metric("Daily maximum wind speed", f"{fmt(row.wind_speed_10m_max)} m/s")
                a.metric("Daily precipitation", f"{fmt(row.precipitation_sum)} mm")
                b.metric("Mean air temperature", f"{fmt(row.temperature_2m_mean)} °C")
                a.metric("Wave period maximum", f"{fmt(row.wave_period_max)} s")
                b.metric("Sea-level pressure mean", f"{fmt(row.pressure_msl_mean)} hPa")
                st.info(f"Model indicators: {indicator_status(record, wave, wind).iloc[0]}")
            extra = ocean[ocean.site_id.eq(focus) & ocean.date_local.eq(pd.Timestamp(target))] if not ocean.empty else ocean
            st.markdown("**Ocean measurements**")
            for col in ["sea_surface_temperature", "chlorophyll_a", "salinity", "current_speed"]:
                value = extra.iloc[0][col] if not extra.empty and col in extra else np.nan
                st.write(f"{LABELS[col][0]}: {fmt(value)} {LABELS[col][1] if pd.notna(value) else ''}")
            if not extra.empty:
                st.caption(f"Ocean source: {extra.iloc[0]['source']} · {extra.iloc[0]['measurement_kind']}")
            st.caption("Daily aggregates describe a whole local day. They are not instantaneous sea conditions. Official warnings are not ingested by this dashboard.")
            st.link_button("Check official Sri Lanka marine forecasts", "https://meteo.gov.lk/", **FULL_WIDTH)
        with st.expander("Selected sampling-point metadata"):
            st.dataframe(sites[sites.site_id.eq(focus)].T.astype(str).rename(columns={sites[sites.site_id.eq(focus)].index[0]: "value"}), **FULL_WIDTH)
            st.caption("Coordinates are the dataset's chosen land and offshore sampling points. Registry verification labels are reproduced from the source metadata; the app does not independently certify harbour locations.")

    with tabs[1]:
        st.subheader(f"Daily and seasonal trends: {names[focus]}")
        part = history[history.site_id.eq(focus)].copy()
        metric_labels = {f"{LABELS[x][0]} ({LABELS[x][1]})": x for x in WEATHER + MARINE}
        selected_label = st.selectbox("Variable", list(metric_labels.keys()), key="trend_variable")
        metric = metric_labels[selected_label]
        period = st.radio("Time horizon", ["Last 30 days", "Last 12 months", "All available years"], horizontal=True)
        end = colombo_today() - pd.Timedelta(days=1)
        if period == "Last 30 days":
            start = end - pd.Timedelta(days=29)
            plot_series(part[part.date_local.between(start, end)], metric, start, end, template=plotly_template)
        else:
            start = (end.replace(day=1) - pd.DateOffset(months=11)) if period == "Last 12 months" else part.date_local.min().replace(day=1)
            if "direction" in metric:
                # Circular monthly direction, no misleading 359°/1° arithmetic mean.
                subset = part[part.date_local.between(start, end)].copy()
                radians = np.deg2rad(subset[metric])
                subset["_sin"], subset["_cos"] = np.sin(radians), np.cos(radians)
                means = subset.set_index("date_local")[["_sin", "_cos"]].resample("MS").mean()
                means[metric] = np.mod(np.rad2deg(np.arctan2(means._sin, means._cos)), 360)
                means.loc[np.hypot(means._sin, means._cos) < 1e-6, metric] = np.nan
                # Already aggregated; avoid a second non-circular reduction.
                plot_series(means.reset_index(), metric, start, end.replace(day=1), monthly=True, label="Monthly circular mean direction", template=plotly_template)
            else:
                plot_series(part[part.date_local.between(start, end)], metric, start, end.replace(day=1), monthly=True, template=plotly_template)
        st.caption("Absent dates remain gaps. Monthly rainfall is the sum of available days; other monthly values are means of available daily values. Check coverage before treating a partial month as complete.")
        st.markdown("**Fish groups and harbour catch records**")
        st.caption("Market names and broad groups below follow your project brief. Species identity, harbour occurrence, depth zones and a local seasonal calendar need verified fishery records; weather alone does not establish fish availability.")
        profiles = pd.DataFrame(SPECIES, columns=["local_market_name", "reference_group", "fish_category"])
        profiles["verified_local_depth_zone"] = "Not supplied"
        profiles["verified_local_season"] = "Not supplied"
        if profile_upload and not demo:
            try:
                profiles = validate_profiles(profile_upload.getvalue()).rename(columns={
                    "species": "local_market_name", "common_name": "reference_group",
                    "depth_zone": "documented_depth_zone", "seasonal_note": "documented_seasonal_note",
                })
                st.caption("User-supplied documented species profiles; source URLs are retained. Check whether each reference applies to this harbour.")
            except Exception as exc:
                st.error(f"Species profile CSV rejected: {exc}")
        st.dataframe(profiles[profiles.fish_category.isin(categories)], hide_index=True, **FULL_WIDTH)
        harbour_catch = catch[catch.site_id.eq(focus) & catch.fish_category.isin(categories)].copy() if not catch.empty else catch
        if harbour_catch.empty:
            st.info("No catch records are connected for this harbour/category. Upload a documented catch CSV to enable species shares, recorded seasonal occurrence and catch-volume trends.")
        else:
            st.caption("SYNTHETIC catch examples" if demo else "Catch records supplied in this session; missing reporting days are not zero catch.")
            shares = harbour_catch.groupby("species", as_index=False).catch_weight_kg.sum()
            bar_color = "#38bdf8" if is_dark else "#007F7A"
            bar_fig = px.bar(shares, x="species", y="catch_weight_kg", title="Catch weight in available records",
                             color_discrete_sequence=[bar_color], template=plotly_template)
            bar_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(bar_fig, **FULL_WIDTH)
            monthly_c = harbour_catch.set_index("date_local").catch_weight_kg.resample("MS").sum(min_count=1).reset_index()
            line_fig = px.line(monthly_c, x="date_local", y="catch_weight_kg", title="Recorded monthly catch (kg)", template=plotly_template)
            line_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(line_fig, **FULL_WIDTH)
            seasonal = harbour_catch.assign(month=harbour_catch.date_local.dt.month, positive_catch=harbour_catch.catch_weight_kg.gt(0)).groupby(["species", "month"], as_index=False).agg(recorded_days=("date_local", "nunique"), positive_catch_days=("positive_catch", "sum"), mean_recorded_kg=("catch_weight_kg", "mean"))
            seasonal["positive_catch_pct_of_reported_days"] = (100 * seasonal.positive_catch_days / seasonal.recorded_days).round(1)
            st.dataframe(seasonal, hide_index=True, **FULL_WIDTH)
            st.caption("Positive-catch percentages use only explicitly reported species-days. They describe the supplied sample, not the probability that a species will be present on an unobserved day.")

    with tabs[2]:
        st.subheader("Explore and export")
        st.write("Customize your download by selecting coastal locations, desired data columns, and any time period spanning historical records up to current forecasts.")

        # Data product & timeline selector
        col_scope, col_dates = st.columns([1, 1.2])
        with col_scope:
            exp_scope = st.selectbox(
                "Data product / timeline",
                [
                    "Historical to Forecast (full timeline)",
                    "Past: prefer reanalysis",
                    "Reanalysis only",
                    "Forecast vintages (all issuance dates)",
                ],
                index=0,
                key="exp_dataset_choice"
            )

        if exp_scope == "Historical to Forecast (full timeline)":
            exp_source = combined_timeline
        elif exp_scope == "Past: prefer reanalysis":
            exp_source = history
        elif exp_scope == "Reanalysis only":
            exp_source = reanalysis
        else:
            exp_source = forecasts

        min_exp_date = exp_source.date_local.min().date() if not exp_source.empty else history.date_local.min().date()
        max_exp_date = exp_source.date_local.max().date() if not exp_source.empty else forecasts.date_local.max().date()
        default_start_date = max(min_exp_date, max_exp_date - pd.Timedelta(days=60))

        with col_dates:
            exp_dates = st.date_input(
                "Select time period (historical to forecast)",
                value=(default_start_date, max_exp_date),
                min_value=min_exp_date,
                max_value=max_exp_date,
                key="exp_dates_range_picker"
            )

        # 1. Option to choose location(s) (one or more)
        exp_sites = st.multiselect(
            "Select location(s)",
            ids,
            default=ids,
            format_func=names.get,
            key="exp_locations_multiselect"
        )

        # 2. Option to choose wanted columns
        available_cols = [c for c in exp_source.columns if not c.startswith("_")]
        core_cols = [
            "site_id", "name", "date_local", "source_kind",
            "precipitation_sum", "wind_speed_10m_max", "temperature_2m_mean",
            "wave_height_max", "wave_period_max", "wave_direction_dominant",
            "weather_model", "marine_model"
        ]
        default_cols = [c for c in core_cols if c in available_cols]
        if not default_cols:
            default_cols = available_cols[:8]

        wanted_columns = st.multiselect(
            "Select wanted columns to export",
            options=available_cols,
            default=default_cols,
            key="exp_wanted_columns_picker"
        )

        # Parse date range
        if isinstance(exp_dates, (list, tuple)) and len(exp_dates) == 2:
            export_dates = exp_dates
        elif isinstance(exp_dates, (list, tuple)) and len(exp_dates) == 1:
            export_dates = (exp_dates[0], exp_dates[0])
        else:
            export_dates = (exp_dates, exp_dates)

        # Filter dataset
        current_rows = filtered(exp_source, exp_sites, export_dates, severity, wave, wind)

        # Apply wanted columns
        if wanted_columns:
            current_export = current_rows[[c for c in wanted_columns if c in current_rows.columns]]
        else:
            current_export = current_rows

        st.caption(f"Showing {len(current_export):,} rows across {len(exp_sites)} location(s) and {len(current_export.columns)} columns. Download files below contain this selection.")

        paginate(current_export, "export_table")
        downloads(current_export, "weather_marine", demo)

        for frame, label in [(catch, "catch"), (ocean, "ocean")]:
            with st.expander(f"{label.title()} records and downloads"):
                selected = filtered(frame, exp_sites, export_dates) if not frame.empty else frame
                if label == "catch" and not selected.empty:
                    selected = selected[selected.fish_category.isin(categories)]
                    if not current_rows.empty and "date_local" in current_rows.columns:
                        matching_keys = current_rows[["site_id", "date_local"]].drop_duplicates()
                        selected = selected.merge(matching_keys, on=["site_id", "date_local"], how="inner", validate="many_to_one")
                    st.caption("Catch records are restricted to the dates/sites passing the weather filters. Species rows remain separate; weights are not repeated across a weather join.")
                paginate(selected, label)
                downloads(selected, label, demo)

        with st.expander("CSV connector contracts and empty templates"):
            for kind, columns in [
                ("catch", ["site_id", "date_local", "species", "fish_category", "catch_weight_kg", "source", "source_url"]),
                ("ocean", ["site_id", "date_local", "sea_surface_temperature", "chlorophyll_a", "salinity", "current_speed", "measurement_kind", "source", "source_url"]),
                ("species_profiles", ["species", "common_name", "fish_category", "depth_zone", "seasonal_note", "source", "source_url"]),
            ]:
                st.code(",".join(columns), language="text")
                st.download_button(f"Download empty {kind} template", pd.DataFrame(columns=columns).to_csv(index=False), f"{kind}_template.csv", key=f"template_{kind}")
            st.caption("Catch: one aggregated species/site/day row; kg; categories small_pelagic, large_pelagic, demersal or other. Ocean: one site/day row; SST Celsius, chlorophyll mg/m³, salinity PSU, current m/s. Each upload must identify its source. It remains session-local and is not uploaded to HF.")

    with tabs[3]:
        st.subheader("Unified Google Colab loader")
        st.write("Load all historical years and both domains into one pandas DataFrame. The loader keeps both model names, flags unmatched domains and records the exact HF commit.")
        code = colab_code(repo, None if demo else bundle["revision"] if len(bundle["revision"]) == 40 else None)
        with st.expander("Copy this complete single Colab cell", expanded=True):
            st.code(code, language="python")
        st.download_button("Download Colab cell", code, "load_sl_fisheries_colab.py", mime="text/plain", on_click="ignore", **FULL_WIDTH)
        st.caption("The Colab loader always reads real HF data; it does not export dashboard demo fixtures. Reanalysis values can be revised and were not necessarily available at a historical forecast date. Use forecast vintages available at each forecast origin for operational backtesting.")

    st.divider()
    st.caption("Sources: Open-Meteo/ECMWF via the linked HF dataset. CC BY 4.0 weather attribution. Catch and ocean uploads retain their own provenance and licences.")
    st.link_button("View source dataset on Hugging Face", f"https://huggingface.co/datasets/{repo}")


if __name__ == "__main__":
    main()
