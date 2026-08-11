import pandas as pd

df = pd.read_csv("data/olist_order_reviews_dataset.csv")
print("total rows:", len(df))
print("unique review_ids:", df["review_id"].nunique())

dupe_ids = df[df.duplicated(subset=["review_id"], keep=False)]
print("\nrows involved in duplicates:", len(dupe_ids))
print(dupe_ids.sort_values("review_id").head(10))