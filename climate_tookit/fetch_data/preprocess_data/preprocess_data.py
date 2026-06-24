"""Internal preprocessing helper for fetch pipeline.

Converts transformed source output into analysis-ready frames. Library callers
may import this helper directly, but it is not stable end-user CLI surface.
End users should prefer `climate-toolkit-fetch` or higher-level analysis CLIs.
"""

import os
from datetime import date
from pathlib import Path
import pandas as pd
import numpy as np
from ..transform_data.transform_data import transform_data


def _active_group_columns(df: pd.DataFrame, group_columns=None) -> list[str]:
    return [column for column in (group_columns or []) if column in df.columns]


def _fill_precipitation_series(series: pd.Series) -> pd.Series:
    """Fill precipitation gaps with zero only when some valid data exists."""
    if series.notna().any():
        return series.fillna(0)
    return series


def clean_climate_data(
    df: pd.DataFrame,
    group_columns=None,
) -> pd.DataFrame:
    """Clean climate data: sort records and fill missing values conservatively."""
    if df.empty:
        return df

    cleaned_df = df.copy()

    if 'date' in cleaned_df.columns:
        cleaned_df['date'] = pd.to_datetime(cleaned_df['date'])

    active_group_columns = _active_group_columns(cleaned_df, group_columns)
    sort_columns = [*active_group_columns, 'date'] if 'date' in cleaned_df.columns else active_group_columns
    if sort_columns:
        cleaned_df = cleaned_df.sort_values(sort_columns).reset_index(drop=True)

    numeric_columns = cleaned_df.select_dtypes(include=[np.number]).columns

    if active_group_columns:
        grouped = cleaned_df.groupby(active_group_columns, group_keys=False, dropna=False)
        for col in numeric_columns:
            if col == 'precipitation':
                cleaned_df[col] = grouped[col].transform(_fill_precipitation_series)
            else:
                cleaned_df[col] = grouped[col].transform(lambda series: series.ffill().bfill())
    else:
        for col in numeric_columns:
            if col == 'precipitation':
                cleaned_df[col] = _fill_precipitation_series(cleaned_df[col])
            else:
                cleaned_df[col] = cleaned_df[col].ffill().bfill()

    return cleaned_df


def apply_unit_conversions(
    df: pd.DataFrame,
    source: str,
    verbose: bool = True,
) -> pd.DataFrame:
    """Apply necessary unit conversions for consistency.

    Unit normalization is internal pipeline behavior, so keep it silent in
    normal runs. Repeated per-fetch printouts add noise without helping users
    act on anything.
    """
    if df.empty:
        return df

    converted_df = df.copy()
    source_lc = (source or "").lower()

    if source_lc in ['agera_5', 'era_5', 'nex_gddp']:
        temp_columns = [col for col in converted_df.columns if 'temperature' in col.lower()]
        for col in temp_columns:
            if col in converted_df.columns:
                if converted_df[col].mean() > 200:
                    converted_df[col] = converted_df[col] - 273.15
    elif source_lc == 'ghcn_daily':
        temp_columns = [col for col in converted_df.columns if 'temperature' in col.lower()]
        for col in temp_columns:
            if col in converted_df.columns:
                converted_df[col] = converted_df[col] / 10.0
    elif source_lc == 'gsod':
        temp_columns = [col for col in converted_df.columns if 'temperature' in col.lower()]
        for col in temp_columns:
            if col in converted_df.columns:
                converted_df[col] = (converted_df[col] - 32.0) * (5.0 / 9.0)

    if 'precipitation' in converted_df.columns:
        if source_lc in ['agera_5', 'era_5']:
            # ERA5 and AgERA5 precipitation bands are depth in meters.
            converted_df['precipitation'] = converted_df['precipitation'] * 1000.0
        elif source_lc == 'imerg':
            # IMERG GEE fetch currently sums half-hourly precipitation rates
            # expressed in mm/hr; multiply by 0.5 hr to obtain daily depth.
            converted_df['precipitation'] = converted_df['precipitation'] * 0.5
        elif source_lc == 'ghcn_daily':
            converted_df['precipitation'] = converted_df['precipitation'] / 10.0
        elif source_lc == 'gsod':
            converted_df['precipitation'] = converted_df['precipitation'] * 25.4

    if source_lc == 'ghcn_daily' and 'wind_speed' in converted_df.columns:
        converted_df['wind_speed'] = converted_df['wind_speed'] / 10.0
    elif source_lc == 'gsod' and 'wind_speed' in converted_df.columns:
        converted_df['wind_speed'] = converted_df['wind_speed'] * 0.514444
    return converted_df

def quality_control_checks(
    df: pd.DataFrame,
    group_columns=None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Perform quality control checks and flag suspicious data."""
    if df.empty:
        return df

    qc_df = df.copy()

    temp_columns = [col for col in qc_df.columns if 'temperature' in col]
    for col in temp_columns:
        if col in qc_df.columns:
            mask = (qc_df[col] < -50) | (qc_df[col] > 60)
            if mask.any():
                if verbose:
                    print(f"Warning: {mask.sum()} extreme {col} values detected")
                qc_df.loc[mask, col] = np.nan

    if 'precipitation' in qc_df.columns:
        small_negative = (qc_df['precipitation'] < 0) & (qc_df['precipitation'] > -0.01)
        qc_df.loc[small_negative, 'precipitation'] = 0

        large_negative = qc_df['precipitation'] <= -0.01
        if large_negative.any() and verbose:
            print(
                "Warning: "
                f"{int(large_negative.sum())} precipitation value(s) <= -0.01 detected; "
                "setting to NaN."
            )
        qc_df.loc[large_negative, 'precipitation'] = np.nan

        extreme_precip = qc_df['precipitation'] > 500
        if extreme_precip.any() and verbose:
            max_precip = float(qc_df.loc[extreme_precip, 'precipitation'].max())
            print(
                "Warning: "
                f"{int(extreme_precip.sum())} precipitation value(s) > 500 mm/day detected "
                f"(max={max_precip:.2f}). Values retained; inspect source data."
            )

    if 'wind_speed' in qc_df.columns:
        extreme_wind = qc_df['wind_speed'].abs() > 50
        if extreme_wind.any() and verbose:
            max_abs_wind = float(qc_df.loc[extreme_wind, 'wind_speed'].abs().max())
            print(
                "Warning: "
                f"{int(extreme_wind.sum())} wind_speed value(s) with |value| > 50 detected "
                f"(max abs={max_abs_wind:.2f}). Values retained; verify units and source data."
            )

    active_group_columns = _active_group_columns(qc_df, group_columns)
    sort_columns = [*active_group_columns, 'date'] if 'date' in qc_df.columns else active_group_columns
    if sort_columns:
        qc_df = qc_df.sort_values(sort_columns).reset_index(drop=True)

    return qc_df


def preprocess_transformed_data(
    transformed_df: pd.DataFrame,
    source: str,
    group_columns=None,
    verbose: bool = True,
) -> pd.DataFrame:
    if transformed_df.empty:
        if verbose:
            print("No data retrieved from source")
        return pd.DataFrame()

    data_columns = [col for col in transformed_df.columns if col != 'date']
    if not data_columns:
        if verbose:
            print("ERROR: No data columns retrieved")
        return pd.DataFrame()

    converted_df = apply_unit_conversions(transformed_df, source, verbose=verbose)
    if (
        source.lower() in {"ghcn_daily", "gsod"}
        and 'mean_temperature' not in converted_df.columns
        and 'max_temperature' in converted_df.columns
        and 'min_temperature' in converted_df.columns
    ):
        converted_df['mean_temperature'] = (
            converted_df['max_temperature'] + converted_df['min_temperature']
        ) / 2.0
    cleaned_df = clean_climate_data(converted_df, group_columns=group_columns)
    final_df = quality_control_checks(
        cleaned_df,
        group_columns=group_columns,
        verbose=verbose,
    )

    # Round climate values for readability, but preserve coordinate precision.
    roundable_columns = [
        column
        for column in final_df.select_dtypes(include=[np.number]).columns
        if column not in {"lat", "lon"}
    ]
    final_df[roundable_columns] = final_df[roundable_columns].round(2)
    return final_df


def preprocess_data(
    source: str,
    location_coord=None,
    variables=None,
    date_from=None,
    date_to=None,
    settings=None,
    transformed_data=None,
    model=None,
    scenario=None,
    verbose=True,
    cache_dir=None,
    refresh_cache=False,
    station_id=None,
    ee_project_id=None,
    workers: int = 1,
) -> pd.DataFrame:
    """Preprocess climate data into analysis-ready format."""
    if transformed_data is not None:
        transformed_df = transformed_data
    else:
        transformed_df = transform_data(
            source=source,
            location_coord=location_coord,
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            settings=settings,
            model=model,
            scenario=scenario,
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
            ee_project_id=ee_project_id,
            workers=workers,
        )

    return preprocess_transformed_data(
        transformed_df=transformed_df,
        source=source,
        verbose=verbose,
    )


def save_output(data, output_path, fmt):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        data.to_csv(output_path, index=False)
    elif fmt == "json":
        data.to_json(output_path, orient="records", date_format="iso", indent=2)
    else:
        raise ValueError(fmt)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Preprocess climate data for analysis")
    parser.add_argument("--source", required=True)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--lat", type=float)
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str)
    parser.add_argument("--model", type=str)
    parser.add_argument("--scenario", type=str)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument(
        "--format",
        choices=["csv", "json", "print"],
        default="print"
    )

    args = parser.parse_args()

    location_coord = (args.lat, args.lon) if args.lon and args.lat else None
    date_from = date.fromisoformat(args.start) if args.start else None
    date_to = date.fromisoformat(args.end) if args.end else None

    df = preprocess_data(
        source=args.source,
        location_coord=location_coord,
        date_from=date_from,
        date_to=date_to,
        model=args.model,
        scenario=args.scenario,
    )

    if args.format == "print" or not args.output:
        print(df)
    else:
        save_output(df, args.output, args.format)
        print(f"Saved to {args.output}")
 
        
# python climate_tookit/fetch_data/preprocess_data/preprocess_data.py --source era_5 --lon 36.8 --lat -1.3 --start 2020-01-01 --end 2020-03-05

# python climate_tookit/fetch_data/preprocess_data/preprocess_data.py --source nex_gddp --lon 36.8 --lat -1.3 --start 2020-01-01 --end 2020-08-31 --model MRI-ESM2-0 --scenario ssp585

# Download data in csv
# For NEX_GDDP
# python climate_tookit/fetch_data/preprocess_data/preprocess_data.py --source nex_gddp --lon 36.8 --lat -1.3 --start 2020-01-01 --end 2020-08-31 --model MRI-ESM2-0 --scenario ssp585 --format csv --output nex_gddp_preprocessed_jan-aug_2020.csv

# For other sources
# python climate_tookit/fetch_data/preprocess_data/preprocess_data.py --source era_5 --lon 36.8 --lat -1.3 --start 2020-01-01 --end 2020-03-05 --format csv --output era5_preprocessed.csv
