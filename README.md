# Climate Data Toolkit

A unified toolkit for retrieving climate data from various global datasets such as CHIRPS, AGERA5, TerraClimate, IMERG, TAMSAT, CHIRTS, ERA5, NEX-GDDP, NASA POWER, CMIP6 and SoilGrids.

## API Dataset Badges

[![CHIRPS](https://img.shields.io/badge/CHIRPS-Precipitation_4.8-blue)](https://data.chc.ucsb.edu/products/CHIRPS-2.0/)
[![AgERA5](https://img.shields.io/badge/AgERA5-Agriculture_Climate_4.8-brightgreen)](https://data.mcc.tu-berlin.de/agera5/)
[![TerraClimate](https://img.shields.io/badge/TerraClimate-Water_Balance_4.7-lightgrey)](http://www.climatologylab.org/terraclimate.html)
[![IMERG](https://img.shields.io/badge/IMERG-Global_Precipitation_4.7-green)](https://gpm.nasa.gov/data/imerg)
[![TAMSAT](https://img.shields.io/badge/TAMSAT-Africa_Precipitation_4.7-yellowgreen)](https://www.tamsat.org.uk/)
[![CHIRTS](https://img.shields.io/badge/CHIRTS-Temperature_4.7-blueviolet)](https://data.chc.ucsb.edu/products/CHIRTSdaily/)
[![ERA5](https://img.shields.io/badge/ERA5-Reanalysis_Climate_4.2-orange)](https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels)
[![NEX-GDDP](https://img.shields.io/badge/NEX--GDDP-Climate_Projections_4.1-blue)](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp)
[![NASA POWER](https://img.shields.io/badge/NASA_POWER-Solar_Temp_Global_4.0-lightblue)](https://power.larc.nasa.gov/)
[![CMIP6](https://img.shields.io/badge/CMIP6-Climate_Scenarios-red)](https://esgf-node.llnl.gov/projects/cmip6/)
[![SoilGrids](https://img.shields.io/badge/SoilGrids-Soil_Properties_4.6-brown)](https://www.isric.org/explore/soilgrids/)

---

## About

The Climate Toolkit offers a unified, programmatic interface to:

- Retrieve climate data from CHIRPS, AGERA5, TerraClimate, IMERG, TAMSAT, CHIRTS, ERA5, NEX-GDDP, NASA POWER, CMIP6 and SoilGrids
- Compute rainfall statistics, anomalies, and hazard indicators
- Compare climate trends over historical and seasonal periods

For user-facing historical daily climate work, the default module policy is
`chirps_v3_daily_rnl + agera_5`: CHIRPS v3 Daily RNL supplies precipitation and
AgERA5 supplies temperature plus companion variables such as humidity, wind,
and solar radiation. If a direct single-source historical fallback is needed,
prefer `agera_5`. Keep `era_5` available for compatibility, diagnostics, and
comparison work, but do not treat it as the primary recommended source.

TAMSAT remains available for completeness and Africa-focused precipitation
comparison work, but it is currently fragile and should not be treated as a
default or relied on for production workflows. It is precipitation-only, must
be paired with a temperature source for most analysis modules, and current
public access via JASMIN has shown slow performance and intermittent SSL /
download failures in live testing. Prefer `chirps_v3_daily_rnl + agera_5` for
normal user workflows.

---

## Project Structure

```
climate_tookit/
├── calculate_hazards/       # Hazard metrics like SPI
├── climate_statistics/      # Stats and anomalies
├── compare_periods/         # Compare historic trends
├── fetch_data/              # Modular data downloaders
└── season_analysis/         # Onset/cessation detection
```

---

## Getting Started

1. **Clone the repository**

   ```bash
   git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
   cd climate-toolkit
   ```

2. **Create virtual environment**

   ```bash
   python -m venv .venv
   ```

3. **Activate virtual environment**

   macOS / Linux:

   ```bash
   source .venv/bin/activate
   ```

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks script activation for current shell, run:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

   Project examples and local commands now assume environment name is `.venv`.

4. **Install dependencies**

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. **Create and configure your `.env`**

   ```bash
   cp .env.example .env
   ```

---

## How to Use

### Recommended CLI entry point

Use installed console scripts when package is installed. `python -m ...` form
still works and is shown as fallback where useful.

```bash
climate-toolkit-fetch \
  --source chirps_v3_daily_rnl \
  --lat -1.286 \
  --lon 36.817 \
  --start 2020-01-01 \
  --end 2020-01-10 \
  --variables precipitation \
  --stage preprocessed
```

Key options:

- `--source`: exact dataset key such as `chirps_v3_daily_rnl`, `chirps_v2`,
  `agera_5`, `era_5`, `nex_gddp`
- `--stage`: `raw`, `transformed`, or `preprocessed`
- `--variables`: comma-separated toolkit variable names such as `precipitation,max_temperature,min_temperature`
- `--output` and `--format`: save to `csv` or `json` instead of printing
- `--site` / `--sites-csv`: many-site fetch path for GEE/Xee-supported sources
- `--cache-dir`: optional local cache root for reuse across runs

For NEX-GDDP, you must also provide `--model` and `--scenario`. Current Earth Engine/Xee access also requires prior Earth Engine authentication plus `GCP_PROJECT_ID` in your environment. Current package backend is documented and tested against Earth Engine NEX-GDDP version `1.1`.

Regional NEX-GDDP fast/screening pools:

- CLI/API name remains `regional_fast`
- in practice this means smaller regional screening subsets, not guaranteed
  fast runtime
- current codified regional subsets carry explicit runtime warnings and should
  be treated as provisional screening pools, not full structural uncertainty
  envelopes
- decision memos:
  - [East Africa](analysis/nex_regional_fast_pool_memo_eaf.md)
  - [West Africa](analysis/nex_regional_fast_pool_memo_waf.md)
  - [Andes](analysis/nex_regional_fast_pool_memo_andes.md)

TAMSAT-specific note:

- use `tamsat` only as optional precipitation partner, not primary recommended
  historical source
- pair it with temperature source such as `agera_5`
- expect slower runs and possible download instability
- treat it as comparison / sensitivity source, not dependable default

The low-level `fetch_data` entry point expects an exact source name. Module-level
`auto` source selection happens in higher-level workflows such as
`climate_statistics`, `season_analysis`, and `calculate_hazards`, where the
historical default path is `chirps_v3_daily_rnl + agera_5`.

Example:

```bash
env GCP_PROJECT_ID=your-project-id climate-toolkit-fetch \
  --source nex_gddp \
  --lat -1.286 \
  --lon 36.817 \
  --start 2050-01-01 \
  --end 2050-01-05 \
  --model MRI-ESM2-0 \
  --scenario ssp245 \
  --variables precipitation,max_temperature,min_temperature \
  --stage raw
```

### Jupyter / notebook usage

If you are running from Jupyter, do not paste plain shell commands into a Python cell. Either:

1. Prefix CLI commands with `!`, or
2. Prefer the import-based Python API shown below.

Notebook-safe example:

```python
from datetime import date

from climate_tookit import fetch_climate_data
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = fetch_climate_data(
    source="chirps_v3_daily_rnl",
    location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 1, 10),
    stage="preprocessed",
)

df.head()
```

If console scripts are not on your PATH, or if you want notebook-safe module
form, use:

```bash
!python -m climate_tookit.fetch_data.fetch_data --help
```

`source_data.py` is internal module. Supported end-user entry points are:

- `climate-toolkit-fetch`
- `python -m climate_tookit.fetch_data.fetch_data`
- top-level Python API such as `fetch_climate_data(...)`

Current installed console scripts:

- `climate-toolkit-fetch`
- `climate-toolkit-seasons`
- `climate-toolkit-seasons-ensemble`
- `climate-toolkit-stats`
- `climate-toolkit-stats-ensemble`
- `climate-toolkit-periods`
- `climate-toolkit-periods-ensemble`
- `climate-toolkit-hazards`
- `climate-toolkit-hazards-ensemble`
- `climate-toolkit-weather-station-download`
- `climate-toolkit-weather-station-compare`
- `climate-toolkit-compare-datasets`
- `climate-toolkit-climatology`

Internal helper modules such as `source_data.py`, `preprocess_data.py`,
`transform_data.py`, `gee_xee_batch.py`, `nex_gddp_batch.py`, and
`cache_inventory.py` remain importable for package internals and advanced
development workflows, but they are not stable end-user CLI contracts.

Likewise, package roots such as `climate_tookit.fetch_data` and
`climate_tookit.weather_station` expose a small stable API surface for normal
use, while lower-level backend helpers remain available through their concrete
submodules for development work and should not be treated as stable package
contracts.

Top-level Python API names:

- `from climate_tookit import fetch_climate_data`
- `from climate_tookit import analyze_climate_statistics`
- `from climate_tookit import compare_climate_periods`
- `from climate_tookit import compare_climate_sources`
- `from climate_tookit import evaluate_hazards`
- `from climate_tookit import download_station_data`
- `from climate_tookit import compare_station_to_grids`

Preferred stable import paths:

- top-level package for end-user workflows:
  - `climate_tookit.fetch_climate_data`
  - `climate_tookit.analyze_climate_statistics`
  - `climate_tookit.compare_climate_periods`
  - `climate_tookit.compare_climate_sources`
  - `climate_tookit.evaluate_hazards`
  - `climate_tookit.download_station_data`
  - `climate_tookit.compare_station_to_grids`
- explicit subpackage roots for supported advanced use:
  - `climate_tookit.fetch_data`
  - `climate_tookit.weather_station`
  - `climate_tookit.crop_calendar`
  - `climate_tookit.climatology`

Avoid depending on deep internal modules unless you are doing package
development. Examples of internal paths that are importable but not stable
contracts:

- `climate_tookit.fetch_data.source_data.source_data`
- `climate_tookit.fetch_data.preprocess_data.preprocess_data`
- `climate_tookit.fetch_data.transform_data.transform_data`
- `climate_tookit.fetch_data.gee_xee_batch`
- `climate_tookit.fetch_data.nex_gddp_batch`
- `climate_tookit.fetch_data.cache_inventory`
- `climate_tookit.fetch_data.source_data.sources.utils`

### Cache and reuse

GEE/Xee-backed fetches can be slow on a cold run because the toolkit has to
retrieve and standardize the source data before writing cache files. Once the
cache exists, repeat runs can be near-instant for the same source, site, date
window, and variable set.

For example, a live three-site, one-year benchmark on June 13, 2026 using:

- `chirps_v3_daily_rnl` cold cache: about 22 seconds
- `agera_5` with precipitation, temperature, humidity, wind, and solar cold cache: about 78 seconds
- either source from warm cache: about 0.75 seconds

If you want cache reuse across sessions, pass a stable project-local
`--cache-dir` such as `outputs/cache/...`.

---

## Development

### Setting Up

- All configuration values (e.g., API keys) are managed via `.env` using `python-dotenv`.
- Modular dataset handlers are found in `climate_tookit/fetch_data/source_data/sources/`, each with `DownloadData` classes.
- Common utilities like enums and settings are stored in `climate_tookit/fetch_data/source_data/sources/utils/`.
- NEX-GDDP real-access R&D note: `analysis/nex_gddp_access_rnd.md`
- `nex_gddp` now uses real Earth Engine/Xee retrieval. It requires Earth Engine auth plus `GCP_PROJECT_ID`.
- Current `nex_gddp` Earth Engine backend uses dataset version `1.1`. Future `1.2` sourcing is tracked as follow-up work, not current runtime behavior.
- Arid-region NEX rainfall-spike warning rationale and literature links are documented in `analysis/nex_gddp_access_rnd.md`.


### Solution Architecture

<h3 style="margin-bottom: 1rem;">Technology Stack</h3>

<div style="display: flex; align-items: flex-start; gap: 24px;">

  <!-- Image block -->
  <div style="flex: 0 0 400px;">
    <img src="./assets/image.png" alt="Climate Data Workflow" style="max-width: 100%; height: auto; margin-top: 24px;" />
    <p style="font-style: italic; font-size: 0.9em; margin-top: 8px;">
      Climate data processing workflow diagram showing the flow from data sources through processing and analysis to end consumers.
    </p>
  </div>

  <!-- Text block -->
  <div style="flex: 1; padding-top:3rem;">
    <ul style="list-style-type: '- '; padding-left: 1em; line-height: 1.6;">
      <li>The core engine of the Climate Toolkit will reuse existing scripts, APIs, and code, with preference for lazy-execution engines.</li>
      <li>Interoperability between R, Python, and other languages will be ensured via OpenAPI-compliant interfaces.</li>
      <li>Project-local caching under <code>outputs/cache/...</code> is now supported for efficient reuse across sessions and repeated analyses.</li>
      <li>A notebook environment will support non-technical users in exploring climate data.</li>
      <li>Technical users will have access to source code and APIs through GitHub.</li>
      <li>The Solution Design & Architecture is a living document and will evolve over time.</li>
      <li>Timestamps will follow the ISO8601 format and be recorded in UTC.</li>
    </ul>
  </div>

</div>

### Application Modules

<div style="margin-top: 2rem;">
  <p>
    Below are the core modules that form the foundation of the application. Each module addresses a specific category of user stories and is designed with future scalability in mind—allowing for independent microservice deployment as the application evolves.
  </p>

  <table style="width: 100%; border-collapse: collapse; border: 1px solid #ccc; margin-top: 1rem;">
    <thead style="background-color:rgb(31, 28, 28);">
      <tr>
        <th style="text-align: left; padding: 8px; border: 1px solid #ccc;">SN</th>
        <th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Title</th>
        <th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Type</th>
        <th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Description</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">1.a</td>
        <td style="padding: 8px; border: 1px solid #ccc;">fetch_data</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Fetches data from a climate database and returns an enriched, analysis-ready dataset.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">1.b</td>
        <td style="padding: 8px; border: 1px solid #ccc;">source_data</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Function</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Retrieves raw data from a climate database in its native format.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">1.c</td>
        <td style="padding: 8px; border: 1px solid #ccc;">transform_data</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Function</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Standardizes external source data to align with the toolkit’s internal data dictionary.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">1.d</td>
        <td style="padding: 8px; border: 1px solid #ccc;">preprocess_data</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Function</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Prepares raw source data into an analysis-ready format (e.g., downscaling, bias correction). This step excludes enrichment like climate statistics, which is handled by dedicated services.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">2</td>
        <td style="padding: 8px; border: 1px solid #ccc;">climate_statistics</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Generates climate statistics from pre-processed datasets.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">3</td>
        <td style="padding: 8px; border: 1px solid #ccc;">calculate_hazards</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Retrieves crop hazard indices for specific locations.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">4</td>
        <td style="padding: 8px; border: 1px solid #ccc;">compare_datasets</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Compares datasets from various climate sources to help users assess and select preferred datasets.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">5</td>
        <td style="padding: 8px; border: 1px solid #ccc;">compare_periods</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Allows comparison of climate statistics between two time periods.</td>
      </tr>
      <tr>
        <td style="padding: 8px; border: 1px solid #ccc;">6</td>
        <td style="padding: 8px; border: 1px solid #ccc;">season_analysis</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Module</td>
        <td style="padding: 8px; border: 1px solid #ccc;">Estimates crop growing seasons in a specific location and returns relevant climate indicators.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- Application Module Interaction Diagram -->
<div style="display: flex; align-items: flex-start; gap: 24px; margin-top: 2.5rem;">

  <!-- Image block -->
  <div style="flex: 0 0 400px;">
    <img src="./assets/diagram2.jpeg" alt="Module Interaction Diagram" style="max-width: 100%; height: auto; margin-top: 4px;" />
    <p style="font-style: italic; font-size: 0.9em; margin-top: 8px;">
      Interaction diagram showing how modules depend on and communicate with each other.
    </p>
  </div>

  <!-- Text block -->
  <div style="flex: 1; padding-top: 0.5rem; line-height: 1.6;">
    <p>
      The diagram illustrates how the different modules interact within the Climate Toolkit. The numbering on the bottom right of each module indicates the suggested implementation order.
    </p>
    <p>
      At the center is the <strong><code>fetch_data</code></strong> module, which orchestrates the retrieval and preprocessing of climate data from various sources. It ensures the data is transformed and standardized before being made available for further analysis.
    </p>
    <p>
      This centralized workflow enables reuse across climate analysis operations like <code>season_analysis</code>, <code>climate_statistics</code>, and <code>compare_periods</code>, ensuring consistency in results and reducing duplication of effort.
    </p>
    <p>
      The <code>compare_datasets</code> module now exists as an active comparison workflow layered on top of the shared fetch pipeline. Its placement in the diagram still reflects its integration point with existing components, especially for assessing and selecting preferred historical data sources.
    </p>
  </div>
</div>

### API Statuses & Response Format

These are the API statuses that will be applicable to this application.

<!-- Styled Table -->
<table style="width: 100%; border-collapse: collapse; margin-top: 1rem;">
  <thead style="background-color: rgb(31, 28, 28);">
    <tr>
      <th style="padding: 8px; border: 1px solid #666;">Status Code</th>
      <th style="padding: 8px; border: 1px solid #666;">Status</th>
      <th style="padding: 8px; border: 1px solid #666;">Message</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="padding: 8px; border: 1px solid #ccc;">20X</td>
      <td style="padding: 8px; border: 1px solid #ccc;">REQUEST_SUCCESSFUL</td>
      <td style="padding: 8px; border: 1px solid #ccc;">"Your request was received and data processed successfully"</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ccc;">40X</td>
      <td style="padding: 8px; border: 1px solid #ccc;">REQUEST_UNSUCCESSFUL</td>
      <td style="padding: 8px; border: 1px solid #ccc;">"Your request was received but there was an issue with processing the data"</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ccc;">50X</td>
      <td style="padding: 8px; border: 1px solid #ccc;">SERVICE_UNREACHABLE</td>
      <td style="padding: 8px; border: 1px solid #ccc;">"Your request was not received by the server"</td>
    </tr>
  </tbody>
</table>

<!-- Text content -->

<div style="display: flex; align-items: flex-start; gap: 32px; margin-top: 1.5rem; flex-wrap: wrap;">
  <!-- Left column -->
  <div style="flex: 1; min-width: 280px;">
    <p>
      This is a basic structure of the API response format containing the mandatory fields. This enables the responses for various services consumed in this toolkit to have a standardised response format. It should be noted that the payload key-value pairs will depend on the return values of the application logic:
    </p>
    <ul style="padding-left: 1.25rem; line-height: 1.6;">
      <li><code>status_code</code>: integer</li>
      <li><code>status</code>: string</li>
      <li><code>message</code>: string</li>
      <li><code>data</code>: json</li>
    </ul>
  </div>
  <!-- Right column -->
  <div style="flex: 1; min-width: 280px; padding: 16px; border: 1px dashed #ccc; font-family: monospace; font-size: 0.9em;">
    <pre style="margin: 0;">{
  "status_code": 200,
  "status": "REQUEST_SUCCESSFUL",
  "message": "Your request was received and data processed successfully",
  "data": {
    # Payload depends on the app logic's return values
    "key1": "value1",
    "key2": "value2"
  }
}</pre>
  </div>
</div>

# Development Best Practices

| # | Practice | Description |
|---|----------|-------------|
| 1 | Commit Early and Often | Don't wait until a large feature is complete. Commit small, logical, and self-contained changes. |
| 2 | Atomic Commits | Each commit should represent a single, coherent change or a small set of related changes. If you're fixing two different bugs, create two separate commits. |
| 3 | Don't Commit Half-Done Work (to shared branches) | While local commits can be frequent, avoid pushing incomplete or broken code to shared development branches. Use "git stash" if you need a clean working directory temporarily. |
| 4 | Test Before Committing | Ensure your code works as expected and passes tests before committing. |
| 5 | Review Before Committing | Use "git diff" to review your own changes before committing to catch unintended modifications. |
| 6 | Conventional Commits | Consider adopting a convention like Conventional Commits (feat:, fix:, chore:, docs:, ci:, refactor:, test:) to categorize changes and enable automated changelog generation. For example, "feat: Add CHIRPS as a climate data source". Ref: https://www.conventionalcommits.org |
| 7 | Consistent Naming Conventions | Establish clear and consistent naming conventions for branches (e.g., feat/feature-name, fix/issue-description, refactor/performance-improvement, etc). |
| 8 | Pull Regularly | Each feature or fix should be developed on a dedicated branch. These branches should be short-lived and merged back into a main development branch (e.g., develop or main) as soon as the work is complete and reviewed. Pull frequently to avoid merge conflicts. |
| 9 | Branching Strategies | GitLab Flow will be used. It will have the following branches:<br><br>a. main: This branch should always be stable and deployable. Direct commits to this branch should be prohibited; all changes must come through pull requests.<br><br>b. staging: This branch is for the UAT/QA environment. Direct commits to this branch should be prohibited; all changes must come through pull requests. Maintainers can have "force push" access. |
| 10 | Well-Documented Pull Requests (PRs) | Summarize the PR's purpose effectively in the subject. The PR should also have a detailed description that covers:<br><br>a. Problem Statement: Clearly describe the problem or feature addressed by the PR.<br><br>b. Solution Overview: Explain how the PR solves the problem or implements the feature.<br><br>c. Technical Details (if necessary): Provide any necessary technical context, architectural decisions, or trade-offs.<br><br>d. Screenshots/Videos: For UI changes, include screenshots or short videos to demonstrate the changes.<br><br>e. Testing Instructions: Provide clear steps for reviewers to test the changes, including any specific configurations or data needed.<br><br>f. Related Issues/Tickets: Link to relevant issues in your issue tracker. |
| 11 | DevOps | Automating the build, test, and deployment process ensures that code changes are integrated frequently and validated quickly. This catches issues early and provides rapid feedback. This will be implemented using GitHub Actions since it is native to GitHub. |
| 12 | Conversation Trails | Keep implementation discussions on the ticket in the Kanban system. This makes it easier to maintain a trail of the conversations and decisions regarding a proposed feature or fix. If discussions are held outside of the ticket (e.g., on Teams due to confidentiality), the conclusions from those discussions should be transferred to the ticket itself. This will still allow the project to maintain an trail of the conversation and decisions affecting the implementation of the feature. |
---

## Contributing

We welcome PRs and suggestions!

1. Fork the repo
2. Work in a feature branch
3. Follow module layout and formatting
4. Submit a pull request with a clear description using the repository PR template
5. Complete every applicable PR template section, especially problem statement, implementation notes, data/auth/runtime notes, testing, and related issues

---

## Weather Station Workflows

Toolkit supports:

1. NOAA station discovery and download with `ghcn_daily`, `gsod`, or `auto`
2. station-vs-grid comparison against historical gridded products
3. custom station CSV/JSON ingestion
4. custom station override into historical climate analysis

### Candidate Review

Find nearby observed stations and create review artifacts:

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nairobi_auto_candidates \
  --open-report
```

Outputs:

- candidate CSV
- candidate JSON
- candidate HTML map

### NOAA Station Download

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --stage preprocessed
```

### Custom Station File

```bash
climate-toolkit-weather-station-download \
  --station-source custom_csv \
  --custom-station-file path/to/station.csv \
  --custom-station-name "My station" \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Expected custom file shape:

- required:
  - `date`
  - at least one requested climate variable
- accepted precipitation aliases:
  - `precipitation`, `precip`, `rain`, `rainfall`, `prcp`
- accepted temperature aliases:
  - `tmax` / `max_temperature`
  - `tmin` / `min_temperature`
  - `tmean` / `mean_temperature`
- optional metadata:
  - `station_id`, `station_name`, `lat`, `lon`, `elevation`

Declare units explicitly:

- `--custom-temp-unit c|f|k`
- `--custom-precip-unit mm|inch|tenth_mm`

### Station vs Grid Comparison

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --selection-mode auto \
  --auto-select auto-1 \
  --grid-source paired \
  --grid-source nasa_power \
  --precip-source chirps_v3_daily_rnl \
  --temp-source agera_5 \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid_2011_2020.json
```

### Historical Analysis With Custom Overrides

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=agera_5 \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation,max_temperature,min_temperature \
  --custom-station-name "My station"
```

### Caching

Weather-station cache uses:

- `outputs/cache/weather_stations/ghcn_daily`
- `outputs/cache/weather_stations/gsod`
- `outputs/cache/weather_stations/custom`
- `outputs/cache/weather_stations/dem_anchor`

Keep cache under project-local `outputs/cache/...` so repeat runs can reuse saved files.

---

## License

This project is licensed under the [MIT License](./LICENSE).
