# Weather Station Data Access Research

Date: 2026-06-15  
Repo branch: `codex/issue-3-spei-4-ndws`

## Question

Where can we get weather station data that is actually usable for the toolkit, and can we access it live from this machine?

## Short Answer

Yes. The strongest practical options are:

1. `Meteostat` for easiest developer experience and station discovery.
2. `NOAA Global Hourly (ISD-derived)` for raw open hourly observations with no token.
3. `NOAA GSOD` for raw open daily summaries with no token.
4. `NOAA GHCN-Daily` for raw open daily climate records with no token.
5. `NOAA CDO API` only as an optional metadata/query layer, because it requires a token.

The important caveat is that station-data completeness is uneven. Live tests showed that nearby-station discovery works well, but variable coverage differs sharply by site and by parameter.

## Official Sources Reviewed

- Meteostat Python docs: <https://dev.meteostat.net/python/>
- Meteostat stations docs: <https://dev.meteostat.net/python/stations>
- Meteostat station inventory docs: <https://dev.meteostat.net/python/stations/inventory>
- Meteostat providers docs: <https://dev.meteostat.net/python/providers>
- Meteostat bulk daily docs: <https://dev.meteostat.net/bulk/daily.html>
- Meteostat station daily API docs: <https://dev.meteostat.net/api/stations/daily.html>
- NOAA Integrated Surface Database: <https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database>
- NOAA Global Hourly public archive: <https://www.ncei.noaa.gov/data/global-hourly/access/>
- NOAA GHCN-Daily product page: <https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily>
- NOAA GHCN-Daily public archive root: <https://www.ncei.noaa.gov/pub/data/ghcn/daily/>
- NOAA GSOD public archive: <https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/>
- NOAA CDO API docs: <https://www.ncei.noaa.gov/cdo-web/webservices/v2>

## What The Docs Say

### Meteostat

- Convenient Python access layer with nearby-station search and inventory inspection.
- Pulls from multiple providers, not one single observing network.
- Has free/open bulk data paths.
- Hosted JSON API path is separate and tied to RapidAPI / API-key style use.

Implication:
- Very good for toolkit prototyping and operational convenience.
- Less ideal if we need a single-source provenance story.

### NOAA Global Hourly / ISD

- Official NOAA/NCEI archive.
- Global hourly and synoptic station observations.
- Public HTTPS file access, no token required for raw files.

Implication:
- Strongest open raw hourly station source tested so far.
- Best fallback if we want direct provenance and can tolerate more parsing work.

### NOAA GSOD

- Official NOAA/NCEI daily summary archive.
- Public HTTPS file access, no token required for raw files.

Implication:
- Easier daily station ingestion than hourly ISD.
- Legacy-style format, but practical.

### NOAA GHCN-Daily

- Official NOAA/NCEI daily climate archive.
- Public station files and metadata over HTTPS.
- Strong for daily precipitation, Tmin, Tmax.

Implication:
- Best open daily climate-station archive for rainfall and temperature.
- Better fit than GSOD when climate-summary variables are the main goal.

### NOAA CDO API

- Useful for station and dataset queries.
- Requires an assigned token.

Implication:
- Good optional helper.
- Not suitable as the zero-friction default access path.

## Live Access Tests

All successful tests below were run from this machine on 2026-06-15.

### 1. Meteostat Python

Installed package:

```bash
.venv/bin/pip install meteostat
```

Live test result:

- Nearby station lookup worked.
- Daily data fetch worked for several sites.
- Coverage was mixed by variable and site.

Tested sites and outcomes:

- `Nairobi (-1.286, 36.817)`
  - Nearby stations found: Wilson, Doonholm, Dagoretti.
  - Daily temperature and wind returned.
  - Daily precipitation came back fully missing for the tested 2020-01-01 to 2020-01-10 window.
- `Lodwar (3.119, 35.5973)`
  - Nearby station found: Lodwar.
  - Daily temperature returned.
  - Precipitation and wind were missing in the tested window.
- `Cusco (-13.5319, -71.9675)`
  - Nearby station found: Cuzco.
  - Daily temperature returned.
  - Only sparse precipitation in the tested window.
- `Kisangani (0.5153, 25.1910)`
  - Nearby stations found.
  - No daily rows returned for the tested window from the selected nearby station.

Conclusion:

- Meteostat is good for station discovery and a quick first-pass fetch layer.
- It is not enough on its own if we need reliable rainfall across Africa and the Andes.

### 2. NOAA Global Hourly

Live fetch:

```bash
curl -L https://www.ncei.noaa.gov/data/global-hourly/access/2025/63742099999.csv | sed -n '1,8p'
```

Result:

- Successful.
- Returned raw hourly rows for `NAIROBI WILSON, KE`.
- Confirms direct public archive access works without a token.

### 3. NOAA GSOD

Live fetch:

```bash
curl -L https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/2025/63742099999.csv | sed -n '1,8p'
```

Result:

- Successful.
- Returned daily summary rows for `NAIROBI WILSON, KE`.
- Includes daily temp, dew point, pressure, visibility, wind, max, min, and precipitation.

### 4. NOAA GHCN-Daily

Live metadata path check:

```bash
curl -L -I https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt
```

Result:

- Successful `HTTP/1.1 200 OK`.

Live station file fetch:

```bash
curl -L https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/KE000063612.dly | sed -n '1,5p'
```

Result:

- Successful.
- Returned raw station records for Lodwar (`KE000063612`).
- Confirms direct public daily station-file access works without a token.

## Access Friction Comparison

| Source | Resolution | Auth Needed | Strength | Main Weakness |
|---|---|---:|---|---|
| Meteostat Python/bulk | Daily, hourly in some cases | No | Easiest discovery and fetch workflow | Coverage varies by site/variable; provenance is provider-mixed |
| NOAA Global Hourly / ISD | Hourly | No | Best open raw hourly station source | Parsing burden is higher |
| NOAA GSOD | Daily | No | Simple daily summaries | Legacy format and units need normalization |
| NOAA GHCN-Daily | Daily | No | Best open daily climate archive | Fixed-width raw format needs parser |
| NOAA CDO API | Query/API layer | Yes | Helpful metadata/search API | Token required |

## Recommendation For The Toolkit

### Recommended order

1. Add a `weather_station` pathway built around `NOAA GHCN-Daily` for daily precip/Tmin/Tmax.
2. Add optional `NOAA Global Hourly` support where sub-daily variables are needed.
3. Use `Meteostat` as a convenience layer for discovery and fallback, not as the only station-data backend.
4. Keep `NOAA CDO API` optional, not mandatory.

### Why

- If the toolkit needs robust climate-station summaries, `GHCN-Daily` is the strongest open default.
- If the toolkit needs an easy UX for station lookup, `Meteostat` is very useful.
- If the toolkit needs rainfall reliability in data-sparse regions, relying only on an aggregator is risky.

## Recommended Next Technical Step

Prototype a downloader abstraction like:

```text
weather_station:
  source = ghcn_daily | gsod | global_hourly | meteostat
  mode = nearest_station | specified_station
```

Then:

1. Build station discovery.
2. Build inventory / availability checks.
3. Build raw-file parsers and harmonization into toolkit variable names.
4. Cache by `source/station_id/year`.
5. Expose station provenance in outputs.

## Bottom Line

Weather station data is accessible, but there is no single perfect source.

- For easiest use: `Meteostat`
- For best open daily climate station archive: `NOAA GHCN-Daily`
- For best open hourly archive: `NOAA Global Hourly / ISD`

If we want dependable station rainfall and temperature workflows in the package, NOAA raw archives should be treated as the serious backend, and Meteostat should be treated as a convenience layer.
