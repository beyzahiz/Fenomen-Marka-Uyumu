from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score
from sklearn.preprocessing import MinMaxScaler

NFS_FEATURE_COLS = ["engagement_rate", "FGR", "posts_per_month"]
NFS_SCALED_COLS = [
    "engagement_rate_scaled",
    "FGR_scaled",
    "posts_per_month_scaled",
]


def compute_nfs(
    df: pd.DataFrame,
    *,
    verbose: bool = True,
    **kwargs,
) -> tuple[pd.DataFrame, Ridge, dict[str, Any]]:
    out = df.copy()

    missing = [c for c in NFS_FEATURE_COLS if c not in out.columns]
    if missing:
        raise KeyError(f"NFS özellikleri eksik: {missing}")

    features = out[NFS_FEATURE_COLS].fillna(0).astype(float)

    # Her feature'ı 0-100'e normalize et
    scaler = MinMaxScaler(feature_range=(0, 100))
    scaled = scaler.fit_transform(features)
    scaled_df = pd.DataFrame(
        scaled,
        columns=NFS_SCALED_COLS,
        index=out.index,
    )
    for col in NFS_SCALED_COLS:
        out[col] = scaled_df[col]

    # Korelasyon bazlı ağırlık
    corrs = features.corrwith(features["engagement_rate"]).abs().fillna(0)
    weight_sum = corrs.sum() or 1.0
    weights = corrs / weight_sum

    # NFS = ağırlıklı ortalama
    nfs_raw = sum(
        weights[col] * out[scaled_col]
        for col, scaled_col in zip(NFS_FEATURE_COLS, NFS_SCALED_COLS)
    )
    out["NFS"] = np.clip(nfs_raw, 0, 100).round(2)
    out["nfs_label"] = out["NFS"]

    learned_weights = {
        col: round(float(weights[col]), 4) for col in NFS_FEATURE_COLS
    }

    train_r2 = float(r2_score(out["engagement_rate"], out["NFS"]))

    if verbose:
        print("✅ NFS — Korelasyon bazlı ağırlıklı skor")
        print(f"   Özellikler: {NFS_FEATURE_COLS}")
        print(f"   Korelasyon bazlı ağırlıklar: {learned_weights}")
        print(f"   Train R² (engagement_rate ~ NFS): {train_r2:.3f}")

    artifacts: dict[str, Any] = {
        "scaler": scaler,
        "learned_weights": learned_weights,
        "feature_cols": NFS_FEATURE_COLS,
        "scaled_cols": NFS_SCALED_COLS,
        "train_r2": train_r2,
    }

    # Pipeline uyumluluğu için dummy Ridge model
    dummy_model = Ridge(alpha=1.0)
    dummy_model.fit(out[NFS_SCALED_COLS], out["NFS"])

    return out, dummy_model, artifacts


def save_nfs_artifacts(
    pipeline_dir: Path,
    nfs_model: Ridge,
    artifacts: dict[str, Any],
) -> None:
    pipeline_dir = Path(pipeline_dir)
    joblib.dump(nfs_model, pipeline_dir / "nfs_ridge_model.pkl")
    joblib.dump(artifacts["scaler"], pipeline_dir / "nfs_feature_scaler.pkl")
    joblib.dump(artifacts, pipeline_dir / "nfs_model_meta.pkl")