"""Data processing logic for RAW Files Combiner."""

import os
import warnings

import numpy as np
import openpyxl
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DATE_FORMAT = "%d/%m/%y %H:%M:%S"

COLUMNS_TO_DROP = [
    "Temp (°C) c:2",
    "Unnamed: 4",
    "Water Level ACt (meters)",
    "Good Battery",
    "Coupler Attached",
    "Coupler Detached",
    "Stopped",
    "End Of File",
    "Abs Pres Barom. (kPa) c:1 2",
    "Unnamed: 2",
    "Host Connected",
    "Max: Temp (°C)",
    "Bad Battery",
    "Temp (°C)",
    "Temp (°C) c:1",
    "Unnamed: 5",
]


def format_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def autofit_excel(filepath):
    """Auto-fit column widths in an Excel file."""
    workbook = openpyxl.load_workbook(filepath)
    worksheet = workbook.active
    for column in worksheet.columns:
        max_length = 0
        col_letter = openpyxl.utils.get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        worksheet.column_dimensions[col_letter].width = (max_length + 2) * 1.7
    workbook.save(filepath)
    workbook.close()


def process_directory(directory_path, log_fn=None):
    """Process a single RAW directory: convert XLSX -> CSV, combine, resample.

    Parameters
    ----------
    directory_path : str
        Full path to the SSD directory to process.
    log_fn : callable, optional
        Function(msg, color) for logging output. Colors: "info", "ok", "warn", "err", "white".

    Returns
    -------
    bool
        True if processing succeeded, False otherwise.
    """
    def log(msg, color="white"):
        if log_fn:
            log_fn(msg, color)

    sitename = os.path.basename(directory_path)

    if not os.path.isdir(directory_path):
        log(f"[SKIP] {sitename}: directory not found", "warn")
        return False

    output_folder = os.path.join(directory_path, f"{sitename}_updated")
    os.makedirs(output_folder, exist_ok=True)

    # Phase 1: Convert each XLSX to a cleaned CSV
    converted_files = 0
    xlsx_files = [f for f in os.listdir(directory_path) if f.endswith(".xlsx")]

    for filename in xlsx_files:
        input_path = os.path.join(directory_path, filename)
        try:
            df = pd.read_excel(input_path)
            df["Date Time"] = pd.to_datetime(df["Date Time"], format=DATE_FORMAT)
        except Exception as e:
            log(f"  [SKIP] {filename}: {e}", "warn")
            continue

        df = df.dropna(subset=["Abs Pres (kPa) c:1 2"])
        if df.empty:
            log(f"  [SKIP] {filename}: no usable rows", "warn")
            continue

        # Drop unwanted columns
        cols_exist = [c for c in COLUMNS_TO_DROP if c in df.columns]
        if cols_exist:
            df = df.drop(cols_exist, axis=1)

        # Mark first/last rows with EOF sentinel
        df.loc[df.index[0], "EOF"] = -1111
        df.loc[df.index[-1], "EOF"] = -9999

        # Save as temporary CSV
        csv_tmp = os.path.join(directory_path, os.path.splitext(filename)[0] + "_modify.csv")
        df.to_csv(csv_tmp, index=False)

        # Rename based on last date
        last_dt = df["Date Time"].iloc[-1]
        if pd.notnull(last_dt):
            dt = pd.to_datetime(last_dt, dayfirst=True)
            new_name = f"{sitename}_{dt.strftime('%Y-%m-%d')}_{dt.strftime('%H%M')}.csv"
        else:
            new_name = f"{sitename}_{os.path.splitext(filename)[0]}.csv"

        new_path = os.path.join(output_folder, new_name)
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(csv_tmp, new_path)
        converted_files += 1

    if converted_files == 0:
        log(f"[SKIP] {sitename}: no files to combine", "warn")
        return False

    # Phase 2: Combine all CSVs in the _updated folder
    dfs = []
    for filename in os.listdir(output_folder):
        if filename.endswith(".csv"):
            csv_path = os.path.join(output_folder, filename)
            df = pd.read_csv(csv_path, parse_dates=["Date Time"])
            dfs.append(df)

    if not dfs:
        log(f"[SKIP] {sitename}: no CSVs to combine", "warn")
        return False

    main_df = pd.concat(dfs)
    main_df["Date Time"] = pd.to_datetime(main_df["Date Time"])

    # Gap-fill with 30-minute date range
    date_range = pd.date_range(
        start=main_df["Date Time"].min(),
        end=main_df["Date Time"].max(),
        freq="30min",
    )
    main_df = pd.merge(
        main_df,
        pd.DataFrame({"Date Time": date_range}),
        on="Date Time",
        how="outer",
    )

    main_df = main_df.sort_values(by="Date Time")
    main_df = main_df.drop_duplicates(
        subset=["Date Time", "Abs Pres (kPa) c:1 2"], keep="first"
    )

    # Remove NaN pressure rows where time gap < 30 min
    main_df["Time Difference"] = main_df["Date Time"].diff().dt.total_seconds() / 60
    main_df = main_df[
        ~((main_df["Abs Pres (kPa) c:1 2"].isna()) & (main_df["Time Difference"] < 30))
    ]
    main_df = main_df.drop("Time Difference", axis=1)

    # Resample to 30-minute intervals
    main_df.set_index("Date Time", inplace=True)
    main_df = main_df[["Abs Pres (kPa) c:1 2", "EOF"]].resample(
        "30min", label="right", closed="right"
    ).mean()

    # Save combined output
    output_path = os.path.join(output_folder, f"{sitename}_Combined.xlsx")
    main_df.to_excel(output_path, index=True)
    autofit_excel(output_path)

    log(f"{sitename} -> {converted_files} file(s) combined", "ok")
    return True
