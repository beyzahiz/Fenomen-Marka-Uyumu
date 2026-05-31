# =============================================================================
# pipeline/generate_synthetic_comments.py — Gönderi bazlı sentetik yorum üretimi
# =============================================================================
# GÖREV   : influencer_posts.csv içindeki her gönderi için, caption/kategori
#           bağlamında sentetik yorum üretir; mevcut yorumlarla birleştirir.
#
# ÇALIŞMA : TezBitirme/ kökünden:
#             python pipeline/generate_synthetic_comments.py
#
# GİRDİ   : data/influencer_posts.csv
#           data/influencer_profiles.csv (kategori)
#           data/influencer_comments.csv (varsa — korunur)
#
# ÇIKTI   : data/influencer_comments.csv (yedek: influencer_comments.csv.bak)
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import random
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POSTS_CSV = DATA / "influencer_posts.csv"
PROFILES_CSV = DATA / "influencer_profiles.csv"
COMMENTS_CSV = DATA / "influencer_comments.csv"
BACKUP_CSV = DATA / "influencer_comments.csv.bak"

# Gönderi başına üretilecek yorum sayısı (posts.comments metrik değil, metin sayısı)
DEFAULT_COMMENTS_PER_POST = 6
MAX_COMMENTS_PER_POST = 15
MIN_COMMENTS_PER_POST = 2
SEED = 42

# Kategori → pozitif / nötr / negatif şablon havuzları (Türkçe, doğal varyasyon)
TEMPLATES: dict[str, dict[str, list[str]]] = {
    "spor": {
        "positive": [
            "Harika performans, devam et!",
            "Bu antrenman motivasyon verici",
            "Kesinlikle deneyeceğim, çok faydalı",
            "Sporcu ruhun gerçekten ilham veriyor",
        ],
        "neutral": [
            "İlgili içerik, teşekkürler",
            "Bunu kaydettim sonra bakarım",
            "Farklı bir açı da eklenebilir bence",
        ],
        "negative": [
            "Bence biraz abartılı olmuş",
            "Beklentimi tam karşılamadı",
        ],
    },
    "moda": {
        "positive": [
            "Kombin çok şık olmuş",
            "Bu stili çok beğendim",
            "Nereden aldın merak ettim",
            "Trendlere uygun harika paylaşım",
        ],
        "neutral": ["Güzel ama bana göre değil", "Fiyat bilgisi olsa iyi olur"],
        "negative": ["Bu sezon biraz eski kalmış", "Renk seçimi pek tutmadı"],
    },
    "saglik": {
        "positive": [
            "Sağlıklı yaşam için çok doğru öneriler",
            "Bunu rutinime ekleyeceğim",
            "Bilimsel ve anlaşılır anlatım",
        ],
        "neutral": ["Doktora danışmak lazım tabii", "Deneyip yorumlarım"],
        "negative": ["Herkes için geçerli olmayabilir", "Biraz genel kalmış"],
    },
    "yemek": {
        "positive": [
            "Çok lezzetli görünüyor tarifi paylaşır mısın",
            "Akşam yapacağım kesin",
            "Sunum da harika olmuş",
        ],
        "neutral": ["Malzemeleri yazarsan sevinirim", "Farklı sos da dene"],
        "negative": ["Bana ağır geldi", "Porsiyon küçük kalmış"],
    },
    "teknoloji": {
        "positive": [
            "Detaylı inceleme için teşekkürler",
            "Tam aradığım bilgi",
            "Karşılaştırma çok işime yaradı",
        ],
        "neutral": ["Fiyat performans nasıl", "Alternatif model var mı"],
        "negative": ["Biraz teknik kalmış", "Eksik özellik var gibi"],
    },
    "oyun": {
        "positive": [
            "Gameplay muhteşem",
            "Bu oyunu kesin oynayacağım",
            "E-spor tarafı da güzel anlatılmış",
        ],
        "neutral": ["Hangi platformda oynuyorsun", "Sunucu lag var mı"],
        "negative": ["Oyun biraz eski kaldı", "Mekanikler zayıf bence"],
    },
    "lifestyle": {
        "positive": [
            "Çok ilham verici paylaşım",
            "Hayatına bayıldım",
            "Minimal ve şık",
        ],
        "neutral": ["Günlük rutin videosu da gelsin", "Mekan neresi"],
        "negative": ["Bana göre değil", "Biraz yüzeysel kalmış"],
    },
    "default": {
        "positive": [
            "Harika içerik eline sağlık",
            "Çok beğendim paylaşım için teşekkürler",
            "Devamını bekliyorum",
            "Gerçekten faydalı oldu",
        ],
        "neutral": [
            "Güzel paylaşım",
            "Not aldım teşekkürler",
            "Daha fazla detay olsa iyi olur",
        ],
        "negative": [
            "Pek benim tarzım değil",
            "Beklentimi karşılamadı",
        ],
    },
}

CAPTION_HOOKS = [
    "Bu paylaşım için ",
    "Videodaki ",
    "Gönderideki ",
    "",
]


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(s)).strip("_")
    return s[:40] or "post"


def make_post_id(row: pd.Series, idx: int) -> str:
    base = f"{row['influencer_name']}_{row.get('post_date', 'nodate')}_{idx}"
    return _slug(base.replace("@", ""))


def _caption_hint(caption: str, max_words: int = 4) -> str:
    if not isinstance(caption, str) or not caption.strip():
        return ""
    words = re.sub(r"#\S+", "", caption).split()
    words = [w for w in words if len(w) > 2][:max_words]
    if not words:
        return ""
    return " ".join(words).lower()


def _pick_template(category: str, rng: random.Random) -> tuple[str, str]:
    pool = TEMPLATES.get(category, TEMPLATES["default"])
    weights = [0.62, 0.28, 0.10]  # pozitif / nötr / negatif
    label = rng.choices(["positive", "neutral", "negative"], weights=weights)[0]
    text = rng.choice(pool[label])
    return label, text


def _build_comment(
    category: str,
    caption: str,
    rng: random.Random,
) -> str:
    _, base = _pick_template(category, rng)
    hint = _caption_hint(caption)
    if hint and rng.random() < 0.35:
        hook = rng.choice(CAPTION_HOOKS)
        return f"{hook}{hint} konusu çok iyi — {base}"
    return base


def comments_count_for_post(post_comments_metric: float, rng: random.Random) -> int:
    """posts.comments sütunu (etkileşim sayısı) → üretilecek metin yorum adedi."""
    if pd.isna(post_comments_metric) or post_comments_metric <= 0:
        return MIN_COMMENTS_PER_POST
    # Log ölçek: 10 yorum → ~4 metin, 1000 → ~8, çok büyük → cap
    import math

    n = int(MIN_COMMENTS_PER_POST + math.log10(max(post_comments_metric, 1)) * 1.8)
    n = max(MIN_COMMENTS_PER_POST, min(n, MAX_COMMENTS_PER_POST))
    if post_comments_metric < 50:
        n = min(n, DEFAULT_COMMENTS_PER_POST)
    return n


def generate_post_comments(
    posts: pd.DataFrame,
    profiles: pd.DataFrame,
    per_post: int | None,
    rng: random.Random,
    max_posts: int | None,
) -> pd.DataFrame:
    cat_map = profiles.set_index("influencer_name")["category"].to_dict()
    rows: list[dict] = []

    work = posts.reset_index(drop=True)
    if max_posts:
        work = work.head(max_posts)

    for idx, row in work.iterrows():
        post_id = make_post_id(row, idx)
        category = cat_map.get(row["influencer_name"], "lifestyle")
        n = per_post if per_post is not None else comments_count_for_post(row.get("comments", 0), rng)

        for j in range(n):
            text = _build_comment(category, row.get("caption", ""), rng)
            likes = rng.randint(0, max(5, int((row.get("likes") or 0) // max(n * 50, 1))))
            rows.append({
                "post_id": post_id,
                "influencer_name": row["influencer_name"],
                "post_date": row.get("post_date", ""),
                "comment_text": text,
                "comment_likes": likes,
                "data_source": "synthetic_post",
                "sentiment_hint": _pick_template(category, rng)[0],
            })

    return pd.DataFrame(rows)


def load_existing_comments() -> pd.DataFrame:
    if not COMMENTS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(COMMENTS_CSV, low_memory=False)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if "data_source" not in df.columns:
        df["data_source"] = "legacy"
    if "post_id" not in df.columns:
        df["post_id"] = ""
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Gönderi bazlı sentetik yorum üret")
    parser.add_argument("--per-post", type=int, default=None, help="Sabit yorum/gönderi (yoksa otomatik)")
    parser.add_argument("--max-posts", type=int, default=None, help="Test için ilk N gönderi")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if not POSTS_CSV.exists():
        raise FileNotFoundError(f"Gönderi dosyası yok: {POSTS_CSV}")

    posts = pd.read_csv(POSTS_CSV, low_memory=False)
    profiles = pd.read_csv(PROFILES_CSV) if PROFILES_CSV.exists() else pd.DataFrame()

    print(f"Gönderi sayısı: {len(posts)}")
    new_df = generate_post_comments(
        posts, profiles, args.per_post, rng, args.max_posts
    )
    print(f"Üretilen yorum: {len(new_df)}")

    existing = load_existing_comments()
    if len(existing):
        if not args.no_backup:
            existing.to_csv(BACKUP_CSV, index=False)
            print(f"Yedek: {BACKUP_CSV}")
        # Önceki sentetik gönderi yorumlarını sil (yeniden üretimde çift kayıt olmasın)
        mask_post = existing["data_source"].astype(str) == "synthetic_post"
        existing = existing[~mask_post]
        # Fenomen havuzu yorumları (post_id boş / legacy)
        legacy = existing[existing["post_id"].astype(str).str.len() == 0].copy()
        if "post_date" not in legacy.columns:
            legacy["post_date"] = ""
        if "sentiment_hint" not in legacy.columns:
            legacy["sentiment_hint"] = ""
        combined = pd.concat([legacy, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(COMMENTS_CSV, index=False)
    print(f"Kaydedildi: {COMMENTS_CSV}  ({len(combined)} satır)")
    print(
        "Sonraki adım: python pipeline/analiz_pipeline.py  "
        "(duygu analizi + checkpoint güncelleme)"
    )


if __name__ == "__main__":
    main()
