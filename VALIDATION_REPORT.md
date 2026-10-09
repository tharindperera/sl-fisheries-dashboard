# Dashboard validation report

Validated 9 October 2026 against HF commit `507972cbe0c94063a2d59063f1189f211bce3402` and the current 16-site schema. The dataset can continue changing; this report describes that captured commit.

## Real dataset and connector

- Public read-only HTTP connector executed successfully against HF raw resolve URLs pinned to the captured revision.
- 134,592 raw weather/marine domain and forecast-vintage records.
- 67,072 joined reanalysis site-days, all 16 configured sites, zero duplicate site-day keys, 67,072 complete weather/marine pairs.
- 67,152 preferred past site-days after adding available recent estimates, without including forecasts.
- 112 joined forecast site-day-vintage rows at the captured revision.
- All inspected source shards had zero null core-value rows and zero duplicate full primary keys.
- 2010 through 2020 have complete paired daily coverage across all 16 sites.
- 2021 is partial: 2,016 rows per domain through 6 May.
- 2022 through 2025 are absent in this snapshot.
- 2026 is partial: 768 rows per reanalysis domain; the aggregate date range does not establish equal site coverage.
- Recent estimates: 1 through 7 October 2026, 112 rows per domain.
- Forecasts: 8 through 14 October 2026, 112 rows per domain, snapshot label 2026-10-08.

The HF coverage and manifest JSON files in this captured revision remain empty. Dashboard coverage is independently derived from validated Parquet records, so those metadata placeholders do not cause it to claim missing years are complete. This dashboard is not a full operational audit of the upstream pipeline.

## Tests

- 23 offline behavioral tests pass, covering demo reproducibility and isolation; source preference; unmatched domain retention; forecast vintages; leap years and missing years; invalid numbers, directions and duplicates; CSV connector contracts; source provenance; CSV/JSON/Parquet round trips; demo/live-error UI; failed-shard refresh-loop regression; empty severity filters; shared map/dropdown selection state; coastal location dropdown selection; 1-click whole dataset downloads; and combined historical-to-forecast timeline exports.
- Streamlit AppTest also rendered the actual HF snapshot, changed the selected harbour, tested complete dataset downloads, selected forecast products and rendered daily trend charts with forecast lines without exceptions.
- The complete generated Colab cell parsed successfully and executed on the real downloaded snapshot using mocked transport, yielding the same 67,072 historical site-days. The pinned HF revision inventory endpoint was also verified over real HTTP.
- Python modules compile successfully. pip check reports no broken requirements.
- Approximate retained memory for three joined real tables in the local test: 71.4 MB, before Streamlit cache/runtime and per-session overhead. Cache entries, download workers and export sizes are bounded; concurrent-user load testing remains deployment-specific.

## Practical limits

- The current HF schema lacks SST, chlorophyll, salinity, currents and catch/species observations. Live mode labels these unavailable; documented session-local uploads enable them. All synthetic examples remain inside the labelled demo mode.
- Exact forecast issuance times and absent intraday vintages cannot be reconstructed from date-only upstream snapshot labels.
- Harbour-specific species depth zones/seasons are not fabricated. The app accepts documented profiles and computes catch summaries only from supplied records.
- Map locations follow the dataset's sampling registry; registry labels are displayed as received, without certification of port locations.
- Sea-value threshold cards are descriptive model indicators with an official Meteorology link, not official warnings or vessel clearance.
- The cloud browser could not reach the workspace-local preview server, so browser screenshot/visual verification was unavailable. AppTest UI behavior and map serialization/callback state were checked. Confirm actual map tiles and marker clicks in your browser after launching locally.
- Community Cloud deployment has not been performed. The setup guide contains the exact user-side repository and deployment steps; no public deployed URL is claimed.

## Tested direct dependencies

Python 3.12; Streamlit 1.65.0; pandas 3.0.6; NumPy 2.4.6; Plotly 7.1.0; Pydeck 0.9.3; PyArrow 25.0.1; requests 2.34.2; tzdata 2026.5; pytest 9.1.1 for development.


