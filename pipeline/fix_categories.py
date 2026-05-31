# fix_categories.py — Checkpoint'teki influencer kategorilerini düzeltir.
#
# Çalıştırma:  python pipeline/fix_categories.py
#
# Sıra:
#   1. HARD_OVERRIDES — kamuoyunca bilinen figürler doğrudan kilitlenir
#   2. Template temizliği — pipeline'ın eklediği sahte etiket blokları kazınır
#   3. predict_and_validate_category — SBERT + güven eşiği ile yeniden sınıflandırma
#   4. Sonuçlar raporlanır, checkpoint ve influencer_profiles.csv yazılır

import sys, pickle, pathlib
import pandas as pd
from sentence_transformers import SentenceTransformer

sys.stdout.reconfigure(encoding="utf-8")

BASE = pathlib.Path(__file__).parent.parent
CKPT = BASE / "pipeline" / "influencer_summary_checkpoint.pkl"
PROF = BASE / "data" / "influencer_profiles.csv"

from pipeline.category_utils import (
    HARD_OVERRIDES, CAMPAIGN_TEXTS, CAMP_TO_TURK,
    predict_and_validate_category,
)

SBERT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def main() -> None:
    print("Checkpoint yükleniyor...")
    with open(CKPT, "rb") as f:
        df: pd.DataFrame = pickle.load(f)
    print(f"  {len(df)} influencer")

    print("SBERT yükleniyor...")
    model = SentenceTransformer(SBERT_MODEL)

    print("Kampanya embedding'leri hazırlanıyor...")
    camp_embs = {name: model.encode([text])[0] for name, text in CAMPAIGN_TEXTS.items()}

    changes, skipped = [], []

    for idx, row in df.iterrows():
        name    = row["influencer_name"]
        old_cat = row["category"]

        new_cat, score = predict_and_validate_category(
            influencer_name = name,
            raw_text        = row["clean_tags_all"],
            sbert_model     = model,
            camp_embeddings = camp_embs,
        )

        if new_cat == old_cat:
            continue

        source = "override" if name in HARD_OVERRIDES else f"SBERT({score:.2f})"
        if score == 0.0 and name not in HARD_OVERRIDES:
            skipped.append((name, old_cat, source))
            continue

        changes.append((name, old_cat, new_cat, source))
        df.at[idx, "category"] = new_cat

    # ── Rapor ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"Değişen: {len(changes)}   Atlanan: {len(skipped)}\n")

    for name, old, new, src in changes:
        print(f"  {name:<35} {old:<12} → {new:<12}  [{src}]")

    if skipped:
        print(f"\nAtlananlar (içerik yetersiz):")
        for name, cat, src in skipped:
            print(f"  {name:<35} {cat}  ({src})")

    # ── Kaydet ────────────────────────────────────────────────────────────────
    if not changes:
        print("\nDeğişiklik yok.")
        return

    with open(CKPT, "wb") as f:
        pickle.dump(df, f)
    print(f"\nCheckpoint güncellendi.")

    if PROF.exists():
        profiles = pd.read_csv(PROF)
        for name, _, new_cat, _ in changes:
            mask = profiles["influencer_name"] == name
            if mask.any():
                profiles.loc[mask, "category"] = new_cat
        profiles.to_csv(PROF, index=False)
        print("influencer_profiles.csv güncellendi.")


if __name__ == "__main__":
    main()
