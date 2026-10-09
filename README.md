# Sri Lanka fisheries observatory

A read-only Streamlit dashboard for the 16 sites in `tharinduperera/sl-fisheries-weather-daily`. It reads weather and marine data at one immutable HF commit, checks their contracts and displays historical estimates, provisional recent estimates and separate forecast vintages.

Start with `Antigravity_SL_Fisheries_Streamlit_Prompt.txt` if you want Antigravity to adapt or extend this implementation. Keep the dashboard separate from the running ingestion project.

## Run on your Windows laptop

1. Extract the project to `D:\sl-fisheries-dashboard`. The folder containing `app.py` must also contain `data.py`, `demo.py`, `sample_sites.csv` and `requirements.txt`.
2. Open that folder in Antigravity. In its PowerShell terminal run:

```powershell
cd D:\sl-fisheries-dashboard
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. The default mode reads public HF data; no HF login or write token is required. Use the sidebar's Synthetic demo option to test catch/ocean views immediately. A visible connector error activates an isolated, fully labelled demo fallback.

To start directly in demo mode:

```powershell
$env:DASHBOARD_DEFAULT_MODE = "demo"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

For tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Create the dashboard GitHub repository

1. Go to https://github.com/new and create a public repository named `sl-fisheries-dashboard` under `tharindperera`. If you use the commands below, leave the new repository empty without an automatically generated README.
2. Confirm the dashboard files are in the extracted folder. Keep local virtual environments, exports and credentials out of git. The supplied `.gitignore` covers these files.
3. Run:

```powershell
cd D:\sl-fisheries-dashboard
git init
git add app.py data.py demo.py sample_sites.csv requirements.txt requirements-dev.txt README.md .streamlit/config.toml .gitignore .github/workflows/ci.yml tests notebooks VALIDATION_REPORT.md Antigravity_SL_Fisheries_Streamlit_Prompt.txt
git commit -m "Add Sri Lanka fisheries dashboard"
git branch -M main
git remote add origin https://github.com/tharindperera/sl-fisheries-dashboard.git
git push -u origin main
```

If that folder is already a git checkout, inspect `git status` and `git remote -v` first and use the existing repository configuration. Do not point a dashboard checkout at the ingestion repository accidentally. You can also use GitHub Desktop or Antigravity's git interface.

The ZIP includes the Streamlit configuration folder; ensure it is included in the push. It sets the teal theme and a 10 MB upload limit. Do not upload `.streamlit/secrets.toml` or any token.

## Deploy on Streamlit Community Cloud

1. Open https://share.streamlit.io/ and sign in using your GitHub account. Connect the dashboard repository if needed.
2. Choose **Create app**, then **Yup, I have an app**.
3. Enter:

| Setting | Value |
| --- | --- |
| Repository | `tharindperera/sl-fisheries-dashboard` |
| Branch | `main` |
| Main file path | `app.py` |
| Advanced settings: Python | `3.12` |
| Secrets | Empty for this public HF dataset |

4. Choose a subdomain if desired, then click **Deploy**. Follow the build logs until the app opens. The app's actual URL will be assigned by Streamlit; none has been created by this package.
5. Confirm Live Hugging Face mode, 16 sites, a visible HF revision, and a coverage heatmap. Switch harbours/products and download a small CSV. Use demo mode to exercise catch/ocean views when those real providers are absent.

Code updates pushed to this GitHub repository are redeployed by Community Cloud. The weather-collection GitHub Actions remain in `sl-fisheries-weather`; the dashboard does not replace or modify them.

If you choose to keep this inside the existing pipeline repository, put all dashboard files in `dashboard/`, place the dashboard requirements there, and deploy `dashboard/app.py`. Avoid changing pipeline dependencies or workflows. The separate dashboard repository is simpler.

Official instructions:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies

## Automatic updates

The app checks the HF dataset revision every five minutes while a viewer session is active, using `st.fragment`. It caches the metadata for four minutes and data bundles for fifteen minutes, with bounded cache entries. A new revision triggers a new validated read and a full app rerun. The sidebar has a manual refresh button.

No Open-Meteo API calls are made by the dashboard. Collection and quota enforcement stay with your existing pipeline. Streamlit may sleep when idle; its cache/refresh mechanism is a reader, not a durable ingestion scheduler. A newly opened session reads the current available dataset.

The connector uses four concurrent downloads, retries transient errors, caps individual files at 64 MiB, caps the shard inventory at 300 and makes browser exports lazy. Filter exports below 200,000 rows. If the project grows far beyond this daily 16-site scale, switch to a partitioned database/query service rather than removing resource limits.

## Understand what you are seeing

- **Reanalysis only:** ERA5 atmosphere and ERA5-Ocean marine estimates. One row per site/local day after a checked outer join. Missing weather or marine rows remain visible.
- **Past: prefer reanalysis:** complete reanalysis wins over provisional recent estimates. Each domain keeps its own model/product/snapshot columns.
- **Forecast vintages:** separate site/day/vintage records; never included in historical reanalysis coverage. The map uses the latest available vintage for its selected date.
- **Synthetic demo:** generated examples for all three domains, with a prominent banner, synthetic flags and download filename prefixes. They are never mixed into HF values or written back to HF.

Weather and marine rows describe the same harbour-day. A dataset with about 134,000 raw domain/vintage records therefore yields about 67,000 paired historical harbour-days, rather than 134,000 independent historical dates.

Coverage is calculated from actual rows against expected dates and sites. Entirely missing years, unequal tails and incomplete current months remain visible. Do not interpolate them silently for modelling.

`wind_speed_10m_max` is maximum wind speed, not a gust. `wave_height_max` is the daily maximum of significant wave height, not the largest individual wave. ERA5 is reanalysis, not a direct harbour measurement. Daily model aggregates are not instantaneous readings. The HF snapshot/retrieval time does not establish when a historical value was first available.

Forecast snapshots in the inspected dataset contain date labels. An exact model issuance timestamp and multiple intraday forecast vintages cannot be recovered from those labels. The dashboard preserves whatever vintages the source actually stores.

Map markers are dataset sampling points, including a land/offshore pair. Source verification labels are displayed as received; the app does not certify a harbour's actual position or operating status.

## Connect real catch, ocean and species-profile data

The inspected HF dataset contains precipitation, wind, air temperature, humidity, pressure and three wave fields. It does not contain SST, chlorophyll, salinity, currents, fish species or catch weights. Live mode shows those values as unavailable until a documented connector is supplied.

Use the sidebar CSV uploads. They stay in the current viewer session and are not stored in HF or shared as a database. Download the empty templates from **Data explorer**. Units and source fields are mandatory contracts.

Catch CSV, one aggregated species/site/day row:

```csv
site_id,date_local,species,fish_category,catch_weight_kg,source,source_url
```

Allowed fish categories are `small_pelagic`, `large_pelagic`, `demersal` and `other`. Missing reports are not zero landings. Aggregate multiple events before upload. Do not directly join species rows to a weather table and sum the repeated weights.

Ocean CSV, one site/day row, with at least one ocean variable:

```csv
site_id,date_local,sea_surface_temperature,chlorophyll_a,salinity,current_speed,measurement_kind,source,source_url
```

SST is Celsius, chlorophyll is mg/m³, salinity is PSU and current speed is m/s. `measurement_kind` must be `observation`, `model_estimate` or `satellite_estimate`. Explain upstream conversions when a provider uses different units or salinity definitions.

Documented species-profile CSV:

```csv
species,common_name,fish_category,depth_zone,seasonal_note,source,source_url
```

Names such as salaya/hurulla/thalapath are regional market labels. The supplied reference table follows the project brief and does not invent verified harbour occurrences, depths or seasonal calendars. Upload documented profiles to show those fields. Catch season tables use only explicitly reported species-days; their positive-catch percentages are not ecological presence probabilities.

For persistent automatic catch/ocean data, extend the connector to a licensed, documented HF product or database and add provenance/unit/date tests. Satellite chlorophyll or salinity cannot be generated from the current wave fields. Upstream Open-Meteo additions should use the pipeline's existing quota ledger; do not add unrestricted per-viewer API requests.

## Colab

Upload `notebooks/SL_Fisheries_Unified_Loader.ipynb` to https://colab.research.google.com/ using **File -> Upload notebook**, then run its single code cell. It downloads real HF Parquet and metadata via hosted raw resolve URLs at one pinned revision.

For the current displayed data, the dashboard's **Coverage & Colab** tab offers a complete cell already pinned to the displayed commit. Set `PINNED_REVISION = None` to intentionally capture the newest HF revision. The cell preserves both domain models, validates uniqueness/site IDs and reports missing coverage. It saves:

- `sl_fisheries_daily_reanalysis.parquet`
- `sl_fisheries_coverage.csv`

The default is reanalysis-only history. The optional operational and forecast examples stay separate. This notebook does not merge catch/species rows into one site/day table or download hypothetical ocean variables absent from HF.

## Sea indicators and research use

Map colours and cards show whether model values exceed configurable display thresholds. They are not official warnings, harbour operating status or permission to sail. Check the Sri Lanka Department of Meteorology at https://meteo.gov.lk/ for official marine forecasts. This dashboard does not ingest official warning bulletins.

For fish-price modelling, later join to documented prices/indexes at the correct market/category frequency, create lagged features and use chronological evaluation. Reanalysis-only retrospective features are not necessarily operationally available at each historical forecast origin; use appropriately available forecast vintages for an honest live-use backtest.

## Sources and licences

Weather source: Open-Meteo/ECMWF via the linked HF dataset, attributed under the dataset's CC BY 4.0 weather-data licence. Uploaded fishery/ocean data retain their own source licences. This package does not grant permission to redistribute third-party uploads.

Variable documentation:
- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/docs/marine-weather-api

Refresh and cache documentation:
- https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- https://docs.streamlit.io/develop/concepts/architecture/caching
