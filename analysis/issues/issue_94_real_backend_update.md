Follow-up after real NEX-GDDP branch work:

This issue still accurately describes `main` / `staging` placeholder behaviour, but existing live Earth Engine artifacts from branch `codex-nex-gddp-access-rnd` show that the location-invariant pattern is a symptom of placeholder backend `#85`, not an inherent problem with the NEX-GDDP dataset itself.

Using real NEX-GDDP pulls already saved under `analysis/`:

- `analysis/nex_subset_sites10_historical_1985_2014_summary.csv`
- `analysis/nex_subset_sites10_ssp245_2041_2070_summary.csv`

historical 1985-2014 mean site climates across 3 models (`ACCESS-CM2`, `EC-Earth3`, `MRI-ESM2-0`) show strong spatial spread:

- precipitation total spread: `8512 mm` at Lodwar to `42520 mm` at Kampala
- tasmax spread: `12.53 C` at La Paz to `37.03 C` at Niamey
- tasmin spread: `-1.69 C` at La Paz to `24.05 C` at Lodwar

Simple sanity checks all pass in those real-backend outputs:

- Lodwar hotter than La Paz: `True`
- Niamey hotter than Cusco: `True`
- Kampala wetter than Lodwar: `True`
- Quito wetter than Niamey: `True`

So:

- on `main` / `staging`: this issue remains valid because active backend is still placeholder
- on `codex-nex-gddp-access-rnd`: this exact failure mode no longer reproduces with real backend artifacts

Suggested disposition:

- keep `#94` open until real NEX backend is merged off branch
- once merged, close `#94` as resolved by replacement of placeholder path tracked in `#85`
