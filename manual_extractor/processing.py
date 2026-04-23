import os

import numpy as np
import openpyxl
import pandas as pd


def format_duration(total_seconds):
    total = int(total_seconds)
    if total < 60:
        return f"Duration: {total:02d} sec"
    if total < 3600:
        return f"Duration: {total // 60:02d} min {total % 60:02d} sec"
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"Duration: {hours:02d} hr {minutes:02d} min {seconds:02d} sec"


def process_pipe(full_filename, output_dir, site, pipe, date_start, date_end):
    out_path = os.path.join(output_dir, f"{site}_{pipe}.xlsx")

    with pd.ExcelFile(full_filename) as xls:
        df = pd.read_excel(xls, sheet_name=site)

    date_range = pd.date_range(start=date_start, end=date_end, freq="30min")
    df1 = pd.DataFrame({"Timestamp": date_range})

    df = df.dropna(subset=["Time", "Date"])

    drop_cols = [
        "Year",
        "Month",
        "Cable Length",
        "WS",
        "PH",
        "Logger Type",
        "Remark",
        "Diver S/N",
        "Unnamed: 12",
        "Muhaini_Remarks",
        "Check_WT_M",
        "Remark 2 (Rain gauge)",
        "Remark 3 (Diver)",
        "Day",
        "Station",
        "Pipe",
        "TimeRaw",
    ]
    df = df.drop(columns=[column for column in drop_cols if column in df.columns])

    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df.to_excel(out_path, index=False)
    df = pd.read_excel(out_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Timestamp"] = df["Date"] + pd.to_timedelta(df["Time"])
    df = df.drop(["Date", "Time"], axis=1)
    df.to_excel(out_path, index=False)

    df = df[df["Site"] == pipe]
    df["Timestamp"], df["Site"] = df["Site"], df["Timestamp"]
    df = df.rename(columns={"Timestamp": "Temp", "Site": "Timestamp"})
    df = df.rename(columns={"Temp": "Site"})
    df.to_excel(out_path, index=True)

    merged = pd.concat([df1, df], ignore_index=True)
    merged = merged.drop(["Site"], axis=1)
    merged = merged.sort_values("Timestamp")
    merged["Time Difference"] = merged["Timestamp"].diff().dt.total_seconds() / 60
    merged.to_excel(out_path, index=False)
    merged = pd.read_excel(out_path)

    merged["Merge_WTM"] = np.nan
    values = []
    flag = False

    for index, row in merged.iterrows():
        if (
            pd.notna(row.get("WT_M"))
            and pd.notna(row["Time Difference"])
            and row["Time Difference"] <= 30
        ):
            values.append(float(row["WT_M"]))
            flag = True

        next_gap = merged.at[index + 1, "Time Difference"] if index + 1 < len(merged) else None
        if flag and next_gap is not None and row["Time Difference"] < next_gap:
            merged.at[index - 1, "Merge_WTM"] = sum(values) if index > 0 else np.nan
            values = []
            flag = False
        if flag and next_gap is not None and row["Time Difference"] >= next_gap:
            merged.at[index + 1, "Merge_WTM"] = sum(values)
            values = []
            flag = False

    merged = merged[merged["WT_M"].isna()]
    merged = merged.drop(["Time Difference", "WT_M"], axis=1)
    merged = merged.rename(columns={"Merge_WTM": pipe})
    merged.to_excel(out_path, index=False)

    workbook = openpyxl.load_workbook(out_path)
    worksheet = workbook.active
    for column in worksheet.columns:
        column_letter = openpyxl.utils.get_column_letter(column[0].column)
        header = str(column[0].value) if column[0].value else ""
        if header.lower() == "timestamp":
            worksheet.column_dimensions[column_letter].width = 22
        else:
            max_len = max((len(str(cell.value)) for cell in column if cell.value is not None), default=0)
            worksheet.column_dimensions[column_letter].width = max(max_len + 4, 12)
    workbook.save(out_path)
    workbook.close()

    return out_path
