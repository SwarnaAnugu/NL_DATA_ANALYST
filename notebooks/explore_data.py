import pandas as pd
from pathlib import Path

data_dir = Path("data")
csv_files = sorted(data_dir.glob("*.csv"))

for f in csv_files:
    df = pd.read_csv(f)
    print(f"\n=== {f.name} ===")
    print(f"rows: {len(df)}, columns: {len(df.columns)}")
    print(df.dtypes)
    print(df.head(2))