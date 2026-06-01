# -*- coding: utf-8 -*-
"""
build_cf_matrix.py
==================
Influencer × Influencer kampanya benzerlik matrisini olusturur (item-based CF).
Mantik:
  Her fenomenin 6 Türkçe kampanya kategorisiyle olan SBERT benzerlik skorlari
  (sim_spor_kampanyasi, sim_moda_kampanyasi, ...) bir "kampanya profil vektoru" olusturur.
  Bu vektorler arasindaki cosine similarity, iki fenomenin ne kadar benzer
  kampanya profiline sahip oldugunu gosterir — item-based collaborative filtering.
Kullanim:
  python pipeline/build_cf_matrix.py
Cikti:
  pipeline/cf_similarity_matrix.pkl  —  DataFrame (135x135), index=influencer_name
"""

import pickle
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

PIPELINE_DIR = Path(__file__).parent

# ── Checkpoint yukle ─────────────────────────────────────────────────────────
print("Checkpoint yukleniyor...")
with open(PIPELINE_DIR / "influencer_summary_checkpoint.pkl", "rb") as f:
    inf_sum = pickle.load(f)

print(f"  {len(inf_sum)} fenomen yuklendi.")

# ── Kampanya profil matrisi ──────────────────────────────────────────────────
sim_cols = sorted([c for c in inf_sum.columns if c.startswith("sim_")])

if not sim_cols:
    raise ValueError("Checkpoint'te 'sim_' ile baslayan sutun bulunamadi. "
                     "Once analiz_pipeline.py calistirin.")

print(f"  Kampanya sutunlari ({len(sim_cols)}): {sim_cols}")

names  = inf_sum["influencer_name"].values
matrix = inf_sum[sim_cols].fillna(0).values          # shape: (N, 10)

# ── Cosine similarity matrisi ────────────────────────────────────────────────
print("CF benzerlik matrisi hesaplaniyor...")
cf_matrix = cosine_similarity(matrix)                # shape: (N, N)

cf_df = pd.DataFrame(cf_matrix, index=names, columns=names)
print(f"  Matris boyutu: {cf_df.shape}")

# Ornek kontrol
sample = inf_sum["influencer_name"].iloc[0]
top5   = cf_df[sample].sort_values(ascending=False).iloc[1:6]
print(f"\n  '{sample}' icin en benzer 5 fenomen (CF):")
for nm, sc in top5.items():
    print(f"    {nm:<30} {sc:.4f}")

# ── Kaydet ───────────────────────────────────────────────────────────────────
cf_df.index = pd.Index([str(c) for c in cf_df.index], dtype=object)
cf_df.columns = pd.Index([str(c) for c in cf_df.columns], dtype=object)

out_path = PIPELINE_DIR / "cf_similarity_matrix.pkl"
safe_path = PIPELINE_DIR / "cf_similarity_matrix_safe.pkl"
joblib.dump(cf_df, out_path)
joblib.dump(cf_df, safe_path)
print(f"\nKaydedildi: {out_path}")
print(f"Uyumlu matris kaydedildi: {safe_path}")
