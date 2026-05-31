# -*- coding: utf-8 -*-
"""
mongo_sync.py
=============
analiz_pipeline.py calistiktan sonra uretilen checkpoint'i
MongoDB'ye upsert eder.

Kullanim:
  python db/mongo_sync.py
  # veya pipeline sonunda otomatik cagirilir
"""
import pickle
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_DIR = Path(__file__).parent.parent / "pipeline"
CKPT_CANDIDATES = [
    PIPELINE_DIR / "influencer_summary_checkpoint_safe.pkl",
    PIPELINE_DIR / "influencer_summary_checkpoint.pkl",
]
CKPT_PATH = next((p for p in CKPT_CANDIDATES if p.exists()), CKPT_CANDIDATES[-1])


def _mongo_safe_value(value):
    if isinstance(value, np.ndarray):
        return [_mongo_safe_value(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_mongo_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _mongo_safe_value(v) for k, v in value.items()}
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if isinstance(value, np.generic):
        return _mongo_safe_value(value.item())
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value


def sync(mongo_uri: str = None):
    try:
        from pymongo import MongoClient, UpdateOne
    except ImportError:
        print("pymongo yuklu degil. 'pip install pymongo' calistirin.")
        return False

    # Checkpoint yukle
    if not CKPT_PATH.exists():
        print(f"HATA: Checkpoint bulunamadi: {CKPT_PATH}")
        return False

    print(f"Checkpoint yukleniyor: {CKPT_PATH}")
    with open(CKPT_PATH, "rb") as f:
        inf_sum: pd.DataFrame = pickle.load(f)
    if "data_source" not in inf_sum.columns:
        inf_sum["data_source"] = inf_sum["influencer_name"].astype(str).apply(
            lambda n: "synthetic" if re.match(r"^@influencer\d+$", n) else "instagram"
        )
    print(f"  {len(inf_sum)} fenomen yuklendi.")

    # MongoDB baglantisi
    import os
    uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.server_info()  # baglanti kontrolu

    col = client["influencer_db"]["processed_influencers"]

    # Indeksler
    col.create_index("influencer_name", unique=True)
    col.create_index("category")
    col.create_index("NFS")
    col.create_index("positive_ratio")
    col.create_index("fake_followers_risk")
    col.create_index("data_source")

    # Upsert islemleri
    ops = []
    now = datetime.now(timezone.utc)
    for _, row in inf_sum.iterrows():
        # NaN degerleri None'a cevir (MongoDB JSON uyumlu)
        doc = {k: _mongo_safe_value(v) for k, v in row.items()}
        doc["synced_at"] = now

        ops.append(UpdateOne(
            filter={"influencer_name": doc["influencer_name"]},
            update={"$set": doc},
            upsert=True,
        ))

    result = col.bulk_write(ops, ordered=False)
    print(f"MongoDB sync tamamlandi:")
    print(f"  Eklendi  : {result.upserted_count}")
    print(f"  Guncellendi: {result.modified_count}")
    print(f"  Koleksiyon : influencer_db.processed_influencers")

    client.close()
    return True


if __name__ == "__main__":
    ok = sync()
    sys.exit(0 if ok else 1)
