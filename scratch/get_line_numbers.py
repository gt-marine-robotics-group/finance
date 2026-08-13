import os
import pandas as pd

XLSX_PATH = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)

df = pd.read_excel(XLSX_PATH, sheet_name="Bills")
df = df.dropna(subset=["Bill Title", "Item Name"])
df["Bill Title"] = df["Bill Title"].astype(str).str.strip()
df["Bill Item ID"] = pd.to_numeric(df["Bill Item ID"], errors="coerce")
df["Bill No."] = pd.to_numeric(df["Bill No."], errors="coerce")

valid_df = df[df["Bill Item ID"] > 0]

summary = []

for bill_title, group in valid_df.groupby("Bill Title", sort=False):
    bill_no = group["Bill No."].iloc[0]
    b_no_str = str(int(bill_no)) if pd.notnull(bill_no) else "N/A"
    
    print("=" * 100)
    print(f"📋 Bill Title: {bill_title} (Bill #{b_no_str})")
    print("=" * 100)
    header = f"{'Line ID':<10} | {'Budget Section':<25} | {'Item Name':<45} | {'Qty':<5} | {'Unit Cost':<10} | {'Total Cost'}"
    print(header)
    print("-" * len(header))
    
    for _, row in group.iterrows():
        line_id = int(row["Bill Item ID"]) if pd.notnull(row["Bill Item ID"]) else "N/A"
        section = str(row.get("Budget Section", "")).strip()
        name = str(row["Item Name"]).strip()
        qty = row.get("Quantity", 1)
        cost = row.get("Cost", 0.0)
        total = row.get("Total Cost", 0.0)
        
        try:
            cost_str = f"${float(cost):.2f}"
        except Exception:
            cost_str = f"${cost}"
            
        try:
            total_str = f"${float(total):.2f}"
        except Exception:
            total_str = f"${total}"
            
        print(f"{line_id:<10} | {section[:24]:<25} | {name[:44]:<45} | {qty:<5} | {cost_str:<10} | {total_str}")
    print("\n")
