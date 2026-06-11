# NEX-GDDP Sanity Matrix

Active nex_gddp backend is currently synthetic placeholder data. Scenario directionality can still be tested, but spatial realism and seasonal realism should not be treated as production-valid.

## Sites

| Site | Region | Historical precip (mm) | Historical Tavg (C) | Historical peak precip month | SSP245 Tavg | SSP585 Tavg |
|---|---|---:|---:|---:|---:|---:|
| Nairobi | East Africa bimodal | 1279.43 | 21.00 | 3 | 22.62 | 23.25 |
| Niamey | Sahel | 1280.33 | 21.00 | 3 | 22.61 | 23.25 |
| Addis Ababa | Ethiopian highlands | 1280.70 | 21.00 | 3 | 22.62 | 23.25 |
| Cusco | Andean highlands | 1279.74 | 21.00 | 3 | 22.61 | 23.25 |
| Lodwar | East Africa dryland | 1278.53 | 21.00 | 3 | 22.63 | 23.25 |

## Directional Checks

### Nairobi
- `PASS` mean_annual_tavg_c: historical < ssp245 < ssp585 | `[21.0, 22.62, 23.25]`
- `PASS` mean_annual_tmax_c: historical < ssp245 < ssp585 | `[26.0, 27.8, 28.51]`
- `PASS` mean_annual_tmin_c: historical < ssp245 < ssp585 | `[15.99, 17.44, 18.0]`
- `PASS` precipitation declines historical > ssp245 > ssp585 (current backend expectation) | `[1279.43, 1152.04, 1088.81]`

### Niamey
- `PASS` mean_annual_tavg_c: historical < ssp245 < ssp585 | `[21.0, 22.61, 23.25]`
- `PASS` mean_annual_tmax_c: historical < ssp245 < ssp585 | `[26.0, 27.8, 28.49]`
- `PASS` mean_annual_tmin_c: historical < ssp245 < ssp585 | `[16.0, 17.43, 18.01]`
- `PASS` precipitation declines historical > ssp245 > ssp585 (current backend expectation) | `[1280.33, 1149.16, 1087.9]`

### Addis Ababa
- `PASS` mean_annual_tavg_c: historical < ssp245 < ssp585 | `[21.0, 22.62, 23.25]`
- `PASS` mean_annual_tmax_c: historical < ssp245 < ssp585 | `[26.0, 27.8, 28.5]`
- `PASS` mean_annual_tmin_c: historical < ssp245 < ssp585 | `[16.0, 17.44, 18.0]`
- `PASS` precipitation declines historical > ssp245 > ssp585 (current backend expectation) | `[1280.7, 1151.4, 1087.23]`

### Cusco
- `PASS` mean_annual_tavg_c: historical < ssp245 < ssp585 | `[21.0, 22.61, 23.25]`
- `PASS` mean_annual_tmax_c: historical < ssp245 < ssp585 | `[26.0, 27.8, 28.5]`
- `PASS` mean_annual_tmin_c: historical < ssp245 < ssp585 | `[16.0, 17.42, 18.0]`
- `PASS` precipitation declines historical > ssp245 > ssp585 (current backend expectation) | `[1279.74, 1152.99, 1088.02]`

### Lodwar
- `PASS` mean_annual_tavg_c: historical < ssp245 < ssp585 | `[21.0, 22.63, 23.25]`
- `PASS` mean_annual_tmax_c: historical < ssp245 < ssp585 | `[26.0, 27.81, 28.5]`
- `PASS` mean_annual_tmin_c: historical < ssp245 < ssp585 | `[16.0, 17.45, 18.0]`
- `PASS` precipitation declines historical > ssp245 > ssp585 (current backend expectation) | `[1278.53, 1151.45, 1086.56]`

## Site Realism Checks

- `FAIL` historical inter-site mean annual temperature spread >= 5C | `0.0`
- `FAIL` historical inter-site mean annual precipitation spread >= 300 mm | `2.17`
- `FAIL` Addis Ababa cooler than Lodwar | `[21.0, 21.0]`
- `FAIL` Cusco cooler than Niamey | `[21.0, 21.0]`
- `PASS` Nairobi wetter than Lodwar | `[1279.43, 1278.53]`
- `FAIL` Not all sites share same peak precipitation month | `{'Nairobi': 3, 'Niamey': 3, 'Addis Ababa': 3, 'Cusco': 3, 'Lodwar': 3}`
