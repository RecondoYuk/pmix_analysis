"""
Merge menu_mix_daily_aggregated.csv with MenuItemMasterName_0.xlsx
- Replace ItemName with master "Item Name"
- Add Product Class, Revenue Category, and Item Group
- Save enriched data to Excel and CSV
"""

import pandas as pd
from pathlib import Path

def main(
    mix_csv_path=r"C:\Users\cshelton.BEAVERRUN\OneDrive - Beaver Run Resort\Desktop\Python Projects\Menu_Mixes\menu_mix_daily_aggregated.csv",
    master_xlsx_path=r"C:\Users\cshelton.BEAVERRUN\OneDrive - Beaver Run Resort\Desktop\Python Projects\24-25 Electronic Journals\MenuItemMasterName_0.xlsx",
    out_xlsx_path="menu_mix_daily_enriched.xlsx",
    out_csv_path="menu_mix_daily_enriched.csv",
):
    # --- Load the menu mix (keep everything as string to avoid ID mismatches) ---
    df_mix = pd.read_csv(mix_csv_path, dtype=str)
    df_mix.columns = [c.strip() for c in df_mix.columns]

    # Normalize ItemID column name (handle common variants)
    if "Item ID" in df_mix.columns and "ItemID" not in df_mix.columns:
        df_mix = df_mix.rename(columns={"Item ID": "ItemID"})
    elif "ItemId" in df_mix.columns and "ItemID" not in df_mix.columns:
        df_mix = df_mix.rename(columns={"ItemId": "ItemID"})

    if "ItemID" not in df_mix.columns:
        raise ValueError("Could not find 'ItemID' (or 'Item ID') in the menu mix CSV.")

    # Clean ItemID values
    df_mix["ItemID"] = df_mix["ItemID"].astype(str).str.strip()

    # --- Load master Excel with messy header ---
    # Row 7 is the header (0-indexed header=6) and we only need specific columns:
    # A=Product Class (header is blank), C=Item ID, D=Item Name, J=Default Revenue Category, L=Item Group
    df_master = pd.read_excel(
        master_xlsx_path,
        header=6,
        usecols="A,C,D,J,L",
        dtype=str,
        engine="openpyxl",
    )

    # Standardize column names
    rename_map = {}
    for col in df_master.columns:
        if str(col).startswith("Unnamed"):
            rename_map[col] = "Product Class"  # Column A
    rename_map["Item ID"] = "ItemID"
    rename_map["Item Name"] = "Item Name"
    rename_map["Default Revenue Category"] = "Revenue Category"
    rename_map["Item Group"] = "Item Group"
    df_master = df_master.rename(columns=rename_map)

    # Forward-fill Product Class in case the report leaves blanks within a group
    if "Product Class" in df_master.columns:
        df_master["Product Class"] = df_master["Product Class"].ffill()

    # Keep only the columns we actually need
    needed = ["ItemID", "Item Name", "Revenue Category", "Item Group", "Product Class"]
    df_master = df_master[[c for c in needed if c in df_master.columns]].copy()

    # Clean/prepare master keys
    df_master = df_master.dropna(subset=["ItemID"])
    df_master["ItemID"] = df_master["ItemID"].astype(str).str.strip()

    # --- Merge (left join to keep all rows from the menu mix) ---
    df_out = df_mix.merge(df_master, on="ItemID", how="left")

    # Replace or create ItemName using master "Item Name"
    if "Item Name" in df_out.columns:
        if "ItemName" in df_out.columns:
            # Use master name when present; otherwise keep original
            df_out["ItemName"] = df_out["Item Name"].where(df_out["Item Name"].notna(), df_out["ItemName"])
        else:
            df_out["ItemName"] = df_out["Item Name"]
        df_out = df_out.drop(columns=["Item Name"])

    # Optional: put the new columns right after ItemName for convenience
    new_cols = [c for c in ["Product Class", "Revenue Category", "Item Group"] if c in df_out.columns]
    if "ItemName" in df_out.columns:
        cols = list(df_out.columns)
        for nc in new_cols:
            if nc in cols:
                cols.remove(nc)
        insert_at = cols.index("ItemName") + 1
        cols = cols[:insert_at] + new_cols + cols[insert_at:]
        df_out = df_out[cols]

    # --- Save outputs ---
    df_out.to_excel(out_xlsx_path, index=False)
    df_out.to_csv(out_csv_path, index=False, encoding="utf-8-sig")

    # Basic diagnostics
    matched = df_out["ItemName"].notna().sum() if "ItemName" in df_out.columns else 0
    unmatched = df_out[df_out.get("ItemName").isna()]["ItemID"].nunique() if "ItemName" in df_out.columns else 0
    print(f"Rows in menu mix: {len(df_mix)}")
    print(f"Rows with ItemName after merge: {matched}")
    print(f"Unique ItemIDs without a matching name: {unmatched}")

if __name__ == "__main__":
    main()
