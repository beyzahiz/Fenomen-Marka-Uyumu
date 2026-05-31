#!/usr/bin/env python3
"""Mevcut checkpoint'te engagement_rate + NFS (ML) günceller; nfs_*.pkl yazar."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from nfs_scoring import compute_nfs, save_nfs_artifacts

PIPELINE_DIR = ROOT / "pipeline"
NB_CHECKPOINT = ROOT / "notebooks" / "influencer_summary_checkpoint.pkl"
PIPE_CHECKPOINT = PIPELINE_DIR / "influencer_summary_checkpoint.pkl"
FGR_FLOOR = {"mega": 3.0, "makro": 1.5, "mikro": 0.5}


def _load_checkpoint() -> pd.DataFrame:
    for path in (NB_CHECKPOINT, PIPE_CHECKPOINT):
        if not path.exists():
            continue
        try:
            return pd.read_pickle(path)
        except Exception:
            try:
                return pickle.load(path.open("rb"))
            except Exception:
                continue
    raise FileNotFoundError("Checkpoint bulunamadı (notebooks/ veya pipeline/).")


def main() -> None:
    df = _load_checkpoint()
    print(f"Yüklendi: {len(df)} fenomen")

    if "avg_likes" in df.columns and "latest_followers" in df.columns:
        df["engagement_rate"] = (
            (df["avg_likes"].fillna(0) + df.get("avg_comments", 0).fillna(0))
            / df["latest_followers"].replace(0, np.nan)
            * 100
        ).fillna(0)
        print("✅ engagement_rate güncellendi (post başına ortalama)")

    if "FGR" in df.columns and "account_type" in df.columns:
        zero = df["FGR"] == 0
        df.loc[zero, "FGR"] = (
            df.loc[zero, "account_type"].map(FGR_FLOOR).fillna(0.5)
        )

    if "eng_auth" not in df.columns:
        df["eng_auth"] = df.get("total_likes", 0) + df.get("total_comments", 0)

    df, model, artifacts = compute_nfs(df, verbose=True)
    save_nfs_artifacts(PIPELINE_DIR, model, artifacts)

    for path in (NB_CHECKPOINT, PIPE_CHECKPOINT):
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(path)
        print(f"✅ Kaydedildi: {path}")
    print(f"   NFS aralığı: {df['NFS'].min():.1f} – {df['NFS'].max():.1f}")


if __name__ == "__main__":
    main()
