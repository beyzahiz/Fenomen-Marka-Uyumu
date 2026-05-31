# =============================================================================
# pipeline/analiz_pipeline.py — Ana Veri ve Model Pipeline'ı
# =============================================================================
# GÖREV   : Ham CSV verilerini okuyup BERT duygu analizi, SBERT benzerlik
#           hesabı, K-Means sahte takipçi tespiti ve XGBoost/LightGBM
#           model eğitimini uçtan uca gerçekleştirir.
#
# ÇALIŞMA : python pipeline/analiz_pipeline.py
#           (TezBitirme/ kök dizininden veya pipeline/ içinden çalışır)
#
# GİRDİLER (data/ dizini):
#   influencer_profiles.csv   — 244 fenomen profili
#   influencer_posts.csv      — 11 292 gönderi
#   influencer_comments.csv   — 11 591 yorum
#
# ÇIKTILAR (pipeline/ dizini):
#   influencer_summary_checkpoint.pkl  — hesaplanmış tüm skorlar
#   best_model_xgb.pkl / lgbm.pkl      — eğitilmiş sınıflandırıcılar
#   label_encoder.pkl / feature_columns.pkl
#
# BAĞIMLILIKLAR:
#   comment_processor.py, influencer_features.py (aynı dizinde)
#   BERT: savasy/bert-base-turkish-sentiment-cased
#   SBERT: paraphrase-multilingual-MiniLM-L12-v2
# =============================================================================

import os
import re
import warnings
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib

from sklearn.preprocessing import MinMaxScaler, StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay, accuracy_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.pipeline import Pipeline
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")

# ── Dizin yapısı ─────────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent          # pipeline/
ROOT_DIR     = PIPELINE_DIR.parent            # TezBitirme/
DATA_DIR     = ROOT_DIR / "data"              # data/
BASE_DIR     = PIPELINE_DIR                   # geriye dönük uyumluluk için

PROFILES_CSV  = DATA_DIR / "influencer_profiles.csv"
POSTS_CSV     = DATA_DIR / "influencer_posts.csv"
CHECKPOINT    = PIPELINE_DIR / "influencer_summary_checkpoint.pkl"
COMMENTS_CSV  = DATA_DIR / "influencer_comments.csv"   # opsiyonel; yoksa atlanır

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 1 — VERİ YÜKLEME
# ════════════════════════════════════════════════════════════════════════════

print("=" * 65)
print("BÖLÜM 1 — VERİ YÜKLEME")
print("=" * 65)

if not PROFILES_CSV.exists():
    raise FileNotFoundError(f"Profil dosyası bulunamadı: {PROFILES_CSV}")
if not POSTS_CSV.exists():
    raise FileNotFoundError(f"Post dosyası bulunamadı: {POSTS_CSV}")

df_inf  = pd.read_csv(PROFILES_CSV)
df_post = pd.read_csv(POSTS_CSV)

print(f"✅ Profil tablosu yüklendi  : {len(df_inf)} fenomen")
print(f"✅ Post tablosu yüklendi    : {len(df_post)} gönderi")
print(f"\nProfil sütunları : {df_inf.columns.tolist()}")
print(f"Post sütunları   : {df_post.columns.tolist()}")

# ── Yorum verisi (opsiyonel) ─────────────────────────────────────────────────
_COMMENTS_AVAILABLE = COMMENTS_CSV.exists()
if _COMMENTS_AVAILABLE:
    print(f"\n✅ Yorum dosyası bulundu: {COMMENTS_CSV.name}")
    from comment_processor import load_comments, sample_top_comments
    _df_comments_raw     = load_comments(COMMENTS_CSV)
    _df_comments_sampled = sample_top_comments(_df_comments_raw)
    print(f"   {len(_df_comments_raw)} yorum yüklendi → {len(_df_comments_sampled)} örneklendi")
else:
    print(f"\nℹ️  Yorum dosyası bulunamadı ({COMMENTS_CSV.name}) — yorum katmanı devre dışı")

# ── Fenomen isimlerini anonimleştir (sentetik veri için; gerçek kullanıcı adları korunur) ──
df_inf = df_inf.reset_index(drop=True)
import re as _re
_counter = 1
_new_names = []
for name in df_inf["influencer_name"]:
    if _re.match(r"^@influencer\d+$", str(name)):
        _new_names.append(f"@influencer{_counter}")
        _counter += 1
    else:
        _new_names.append(name)  # gerçek kullanıcı adı, olduğu gibi bırak
df_inf["influencer_name"] = _new_names
df_inf["data_source"] = df_inf["influencer_name"].apply(
    lambda n: "synthetic" if _re.match(r"^@influencer\d+$", str(n)) else "instagram"
)

# ── Post verisi ön temizlik ───────────────────────────────────────────────────
df_post["category_new"] = df_post["hashtags"].fillna("diğer")

cols_to_drop = ["Post ID", "Influencer Handle"]
df_post.drop(columns=[c for c in cols_to_drop if c in df_post.columns], inplace=True)

if "Followers" in df_post.columns:
    df_post.drop(columns=["Followers"], inplace=True)

cols_to_remove = ["Eng. (Avg.)", "Eng. (Auth.)", "instagram name"]
df_post.drop(columns=cols_to_remove, errors="ignore", inplace=True)

if "country" in df_post.columns:
    df_post["country"] = df_post["country"].fillna("")

# Sütun adı standardizasyonu
df_post.columns = (
    df_post.columns
    .str.strip()
    .str.lower()
    .str.replace(r"[\s\.\(\)%]+", "_", regex=True)
)

print("\n✅ Post verisi temizlendi")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 2 — BİRLEŞTİRME VE ÖZELLİK MÜHENDİSLİĞİ
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 2 — VERİ BİRLEŞTİRME VE ÖZELLİK MÜHENDİSLİĞİ")
print("=" * 65)

merged = pd.merge(df_inf, df_post, on="influencer_name", how="inner")
merged["post_date"] = pd.to_datetime(merged["post_date"], errors="coerce")
merged = merged.sort_values(["influencer_name", "post_date"])

# ── Hashtag temizleme ─────────────────────────────────────────────────────────
def clean_tags(text):
    if pd.isna(text):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-zA-ZçğıöşüÇĞİÖŞÜ ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

merged["clean_tags"] = merged["hashtags"].apply(clean_tags)

# ── Kategori anahtar kelime tespiti ──────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "beauty_fashion"  : [
        "beauty","skincare","makeup","cosmetics","haircare","fashion","luxury_fashion",
        "streetwear","modest_fashion","outfit","accessories","jewelry","perfume",
        "ootd","style","moda","guzellik","makyaj","kombin","stil","cilt","sac",
        "spf","serum","krem","fondoten","ruj","parfum","taki","aksesuar",
    ],
    "lifestyle"       : [
        "lifestyle","daily_life","vlog","luxury_lifestyle","minimalism","productivity",
        "home_living","selfcare","relationship","motherhood","family","student_life",
        "yasam","rutin","minimalizm","motivasyon","kisisel","anne","bebek",
        "cocuk","hamilelik","evdekor","yuva","iliski","ogrenci",
    ],
    "fitness_health"  : [
        "fitness","gym","bodybuilding","pilates","yoga","wellness","healthy_lifestyle",
        "weight_loss","nutrition","diet","supplements","mental_health","motivation",
        "spor","antrenman","egzersiz","kosu","saglik","beslenme","meditasyon",
        "diyet","vucut","kas","kalori","protein","psikoloji",
    ],
    "food_gastronomy" : [
        "food","recipes","cooking","restaurant","street_food","gourmet","coffee",
        "desserts","healthy_food","vegan","baking","yemek","tarif","lezzet",
        "mutfak","kahve","pasta","tatli","restoran","cafe","gurme","vejetaryen",
    ],
    "technology"      : [
        "technology","ai","machine_learning","software","programming","gadgets",
        "smartphones","gaming_pc","cybersecurity","robotics","startup","data_science",
        "teknoloji","yazilim","yapay","kodlama","uygulama","bilgisayar",
        "siber","veri","algoritma","egitim","education","ogrenme","akademik",
    ],
    "gaming"          : [
        "gaming","esports","twitch","fps_games","moba","minecraft","valorant",
        "league_of_legends","gta","roleplay","streaming","oyun","gamer","ps5",
        "xbox","playstation","stream","riot","steam","pubg","fortnite",
    ],
    "travel"          : [
        "travel","backpacking","hotels","aviation","camping","digital_nomad",
        "europe_travel","luxury_travel","vanlife","seyahat","gezi","tatil",
        "explore","wanderlust","kamp","roadtrip","ucak","otel","kesif",
    ],
    "finance_business": [
        "finance","investing","crypto","stock_market","entrepreneurship","startups",
        "passive_income","e_commerce","business","personal_finance","finans",
        "yatirim","kripto","borsa","girisim","isletme","ekonomi","butce",
    ],
    "entertainment"   : [
        "entertainment","comedy","memes","reaction","cinema","movies","series",
        "music","concerts","celebrity","eglence","komedi","sinema","film","dizi",
        "muzik","konser","dans","sarki","sanat","mizah",
    ],
    "sports"          : [
        "football","basketball","volleyball","motorsports","formula1","cycling",
        "swimming","boxing","martial_arts","athletics","futbol","basketbol",
        "voleybol","motor","bisiklet","yuzme","boks","atletizm","f1","nba",
    ],
}

# Eski kategori adlarini yeni sisteme esle (geriye donuk uyumluluk)
CATEGORY_LEGACY_MAP = {
    "moda"      : "beauty_fashion",
    "spor"      : "sports",
    "teknoloji" : "technology",
    "anne-bebek": "lifestyle",
    "oyun"      : "gaming",
    "yemek"     : "food_gastronomy",
    "lifestyle" : "lifestyle",
    "seyahat"   : "travel",
    "egitim"    : "technology",
    "saglik"    : "fitness_health",
    "eglence"   : "entertainment",
}

def detect_category(hashtags):
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in hashtags:
                return category
    return "diğer"

merged["auto_category"] = merged["clean_tags"].apply(detect_category)

# ── Fenomen bazında özet tablo ────────────────────────────────────────────────
influencer_summary = merged.groupby("influencer_name").agg(
    total_likes      = ("likes",            "sum"),
    total_comments   = ("comments",         "sum"),
    total_shares     = ("shares",           "sum"),
    avg_likes        = ("likes",            "mean"),
    avg_comments     = ("comments",         "mean"),
    post_count       = ("post_date",        "count"),
    latest_followers = ("followers_at_date","last"),
    oldest_followers = ("followers_at_date","first"),
    avg_post_reach   = ("post_reach",       "mean"),
    first_post       = ("post_date",        "min"),
    last_post        = ("post_date",        "max"),
    category         = ("category",         "first"),
    country          = ("country",          "first"),
    account_type     = ("account_type",     "first"),
    data_source      = ("data_source",      "first"),
).reset_index()

# Türetilmiş metrikler
influencer_summary["eng_auth"] = (
    influencer_summary["total_likes"] + influencer_summary["total_comments"]
)
influencer_summary["engagement_rate"] = (
    (influencer_summary["avg_likes"] + influencer_summary["avg_comments"])
    / influencer_summary["latest_followers"] * 100
)
influencer_summary["FGR"] = influencer_summary.apply(
    lambda r: (
        (r["latest_followers"] - r["oldest_followers"]) / r["oldest_followers"] * 100
        if r["oldest_followers"] > 0 else 0
    ),
    axis=1,
)
# FGR=0 olan fenomenler icin hesap tipine gore minimum deger (gercek verideki statik takipci sorunu)
_FGR_FLOOR = {"mega": 3.0, "makro": 1.5, "mikro": 0.5}
_zero_mask = influencer_summary["FGR"] == 0
influencer_summary.loc[_zero_mask, "FGR"] = (
    influencer_summary.loc[_zero_mask, "account_type"].map(_FGR_FLOOR).fillna(0.5)
)
influencer_summary["day_active"] = (
    (influencer_summary["last_post"] - influencer_summary["first_post"]).dt.days + 1
)
influencer_summary["posts_per_month"] = (
    influencer_summary["post_count"] / influencer_summary["day_active"] * 30
)
# NaN veya 0 olan posts_per_month icin hesap tipine gore varsayilan deger
_PPM_DEFAULT = {"mega": 15.0, "makro": 8.0, "mikro": 4.0}
_ppm_bad = influencer_summary["posts_per_month"].isna() | (influencer_summary["posts_per_month"] == 0)
influencer_summary.loc[_ppm_bad, "posts_per_month"] = (
    influencer_summary.loc[_ppm_bad, "account_type"].map(_PPM_DEFAULT).fillna(4.0)
)

# Kategori ve hashtag özeti
category_summary = merged.groupby("influencer_name").agg(
    clean_tags_all = ("clean_tags",    lambda x: " ".join(x.dropna())),
    top_category   = ("auto_category", lambda x: x.mode()[0] if len(x.mode()) > 0 else "diğer"),
).reset_index()

influencer_summary = influencer_summary.merge(category_summary, on="influencer_name", how="left")

# main_category: profil kategorisini yeni sisteme esle
influencer_summary["main_category"] = influencer_summary["category"].map(
    lambda c: CATEGORY_LEGACY_MAP.get(str(c).strip().lower(), str(c).strip().lower())
)

print(f"✅ influencer_summary: {len(influencer_summary)} fenomen")
print(f"Sütunlar: {influencer_summary.columns.tolist()}")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 3 — NFS (Numerical Fit Score) — ML ile öğrenilen ağırlıklar
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 3 — NFS (Ridge Regresyon, Veriden Öğrenilen Katsayılar)")
print("=" * 65)

from nfs_scoring import compute_nfs, save_nfs_artifacts

influencer_summary, nfs_ridge_model, nfs_artifacts = compute_nfs(
    influencer_summary, verbose=True
)
save_nfs_artifacts(PIPELINE_DIR, nfs_ridge_model, nfs_artifacts)
print(f"   NFS artefaktları kaydedildi: {PIPELINE_DIR.name}/nfs_*.pkl")

print(
    influencer_summary[
        ["influencer_name", "category", "engagement_rate", "FGR", "posts_per_month", "NFS"]
    ]
    .sort_values("NFS", ascending=False)
    .head(10)
    .to_string(index=False)
)

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 4 — SFS (Semantic Fit Score) — SBERT
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 4 — SFS HESAPLAMA (Anlamsal Uyum Puanı)")
print("=" * 65)

from sentence_transformers import SentenceTransformer
from numpy.linalg import norm as np_norm

print("SentenceTransformer modeli yükleniyor (ilk seferde ~500 MB indirir)...")
sbert_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

from category_seeds import append_seed_to_tags, prepend_seed_to_text

# Seyrek hashtag sorununu gider: profil kategorisi anahtar kelimelerini clean_tags_all'a ekle
influencer_summary["clean_tags_all"] = influencer_summary.apply(
    lambda r: append_seed_to_tags(str(r.get("clean_tags_all", "")), r.get("category", "")),
    axis=1,
)

def build_influencer_text(group):
    tags     = " ".join(group["clean_tags"].dropna().unique())
    captions = " ".join(group["caption"].dropna().unique())
    return (tags + " " + captions).strip()

influencer_texts = (
    merged.groupby("influencer_name")
    .apply(build_influencer_text)
    .reset_index()
)
influencer_texts.columns = ["influencer_name", "influencer_text"]

# Profil kategorisi tohumlarini SBERT girisine enjekte et.
# Seed 3x basina ekleniyor: gercek influencer postlari seyrek/konu-disi olabilir
# (orneg. @cznburak son postlarda araba hashtagi kullaniyor).
# 3x tekrar, SBERT ortalama havuzlamada seed tokenlarini hakimiyetini artiriyor.
_cat_map = influencer_summary.set_index("influencer_name")["category"].to_dict()
influencer_texts["influencer_text"] = influencer_texts.apply(
    lambda r: prepend_seed_to_text(
        str(r["influencer_text"]),
        _cat_map.get(r["influencer_name"], ""),
        repeat=3,
    ),
    axis=1,
)

# ── Yorum metnini SBERT inputuna ekle (varsa) ────────────────────────────────
if _COMMENTS_AVAILABLE:
    from comment_processor import aggregate_comments, build_enriched_influencer_text
    _agg_comments = aggregate_comments(_df_comments_sampled)          # influencer_name + aggregated_comments
    _agg_map = _agg_comments.set_index("influencer_name")["aggregated_comments"].to_dict()

    influencer_texts["influencer_text"] = influencer_texts.apply(
        lambda r: build_enriched_influencer_text(
            base_text            = r["influencer_text"],
            aggregated_comments  = _agg_map.get(r["influencer_name"], ""),
            comment_weight       = 0.30,   # yorumlar toplam token'ın ~%30'u
            max_comment_words    = 120,
        ),
        axis=1,
    )
    print("  ✅ Yorum metinleri SBERT inputuna eklendi (ağırlık: %30)")

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np_norm(a) * np_norm(b) + 1e-10))

BRAND_CAMPAIGNS = {
    "spor_kampanyasi": (
        "Spor giyim markasıyız. Fitness, spor salonu, koşu, yoga ve aktif yaşam tarzı "
        "içerikleri üreten fenomenlerle çalışmak istiyoruz. Antrenman rutinleri, spor "
        "beslenme önerileri, motivasyon içerikleri ve sağlıklı yaşam paylaşımları "
        "yapan içerik üreticileri arıyoruz."
    ),
    "moda_kampanyasi": (
        "Moda ve güzellik markasıyız. Stil önerileri, kombin paylaşımları, makyaj "
        "ve güzellik içerikleri üreten fenomenlerle çalışmak istiyoruz. Sokak modası, "
        "trend takibi, aksesuar ve kıyafet incelemeleri yapan içerik üreticileri arıyoruz."
    ),
    "teknoloji_kampanyasi": (
        "Teknoloji ve elektronik markasıyız. Cihaz incelemeleri, yazılım geliştirme, "
        "yapay zeka, kodlama ve dijital inovasyon içerikleri üreten fenomenlerle "
        "çalışmak istiyoruz. Ürün karşılaştırmaları ve teknoloji haberleri paylaşan "
        "içerik üreticileri arıyoruz."
    ),
    "yemek_kampanyasi": (
        "Gıda ve mutfak markasıyız. Yemek tarifleri, restoran incelemeleri, sağlıklı "
        "beslenme ve mutfak içerikleri üreten fenomenlerle çalışmak istiyoruz. "
        "Ev yemekleri, gurme deneyimler ve pratik tarifler paylaşan içerik "
        "üreticileri arıyoruz."
    ),
    "annebebek_kampanyasi": (
        "Anne ve bebek ürünleri markasıyız. Annelik deneyimleri, bebek bakımı, "
        "çocuk gelişimi ve aile yaşamı içerikleri üreten fenomenlerle çalışmak "
        "istiyoruz. Hamilelik süreci, emzirme, bebek beslenmesi ve ebeveynlik "
        "önerileri paylaşan içerik üreticileri arıyoruz."
    ),
    "oyun_kampanyasi": (
        "Oyun ve e-spor markasıyız. Oyun incelemeleri, canlı yayın, e-spor turnuvaları "
        "ve gaming setup içerikleri üreten fenomenlerle çalışmak istiyoruz. "
        "Strateji oyunları, FPS oyunları ve oyun dünyası haberleri paylaşan "
        "içerik üreticileri arıyoruz."
    ),
}

inf_texts_list      = influencer_texts["influencer_text"].astype(str).tolist()
influencer_embeddings = sbert_model.encode(inf_texts_list, show_progress_bar=True)
influencer_texts["sbert_embedding"] = [
    emb.astype(float).tolist() for emb in influencer_embeddings
]

for campaign_name, brand_text in BRAND_CAMPAIGNS.items():
    brand_embedding = sbert_model.encode([brand_text])[0]
    sims = [cosine_sim(emb, brand_embedding) for emb in influencer_embeddings]
    influencer_texts[f"sim_{campaign_name}"] = sims

sim_cols = [f"sim_{c}" for c in BRAND_CAMPAIGNS]
influencer_summary = influencer_summary.merge(
    influencer_texts[["influencer_name", "sbert_embedding"] + sim_cols],
    on="influencer_name",
    how="left",
)

print("✅ SFS (kampanya benzerlik skorları) hesaplandı")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 5 — DUYGU ANALİZİ (BERT)
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 5 — DUYGU ANALİZİ (BERT Türkçe)")
print("=" * 65)

from transformers import pipeline as hf_pipeline

print("BERT modeli yükleniyor (savasy/bert-base-turkish-sentiment-cased)...")
sentiment_pipeline = hf_pipeline(
    "sentiment-analysis",
    model="savasy/bert-base-turkish-sentiment-cased",
)

# Fenomen basina max 30 post ornekle — 11k yerine ~6k metin, 2x hizli
_SENT_SAMPLE = 30
_sent_frames = []
for _inf_name, _grp in merged.groupby("influencer_name"):
    _sent_frames.append(_grp.sample(min(len(_grp), _SENT_SAMPLE), random_state=42))
merged_sent = pd.concat(_sent_frames, ignore_index=True)

texts = merged_sent["caption"].fillna("").apply(lambda x: str(x)[:512]).tolist()
_labels, _scores = [], []
_CHUNK = 256
for _i in range(0, len(texts), _CHUNK):
    _res = sentiment_pipeline(texts[_i:_i+_CHUNK], truncation=True, batch_size=32)
    _labels.extend(r["label"] for r in _res)
    _scores.extend(r["score"]  for r in _res)
    print(f"  Duygu analizi: {min(_i+_CHUNK, len(texts))}/{len(texts)}", flush=True)

merged_sent["sentiment_label"] = _labels
merged_sent["sentiment_score"]  = _scores

print(f"✅ {len(merged_sent)} post için duygu analizi tamamlandı")
print("\nDuygu dağılımı:")
print(merged_sent["sentiment_label"].value_counts())

merged_sent["signed_score"] = merged_sent.apply(
    lambda r: r["sentiment_score"] if r["sentiment_label"] == "positive" else -r["sentiment_score"],
    axis=1,
)

sentiment_summary = merged_sent.groupby("influencer_name").apply(
    lambda g: pd.Series({
        "total_posts"          : len(g),
        "positive_count"       : (g["sentiment_label"] == "positive").sum(),
        "negative_count"       : (g["sentiment_label"] == "negative").sum(),
        "positive_ratio"       : (g["sentiment_label"] == "positive").mean() * 100,
        "negative_ratio"       : (g["sentiment_label"] == "negative").mean() * 100,
        "avg_sentiment_score"  : g["sentiment_score"].mean(),
        "avg_signed_sentiment" : g["signed_score"].mean(),
    })
).reset_index()

influencer_summary = influencer_summary.merge(
    sentiment_summary[
        ["influencer_name","positive_ratio","negative_ratio",
         "avg_sentiment_score","avg_signed_sentiment"]
    ],
    on="influencer_name",
    how="left",
)

# ── Yorum duygu metrikleri (varsa) ───────────────────────────────────────────
if _COMMENTS_AVAILABLE:
    from comment_processor import analyze_comment_sentiment
    print("\n  Yorum sentiment analizi çalıştırılıyor...")
    comment_sentiment_df = analyze_comment_sentiment(
        df_sampled         = _df_comments_sampled,
        sentiment_pipeline = sentiment_pipeline,
        batch_size         = 32,
    )
    influencer_summary = influencer_summary.merge(
        comment_sentiment_df[[
            "influencer_name",
            "positive_comment_ratio",
            "negative_comment_ratio",
            "neutral_comment_ratio",
            "avg_comment_sentiment",
            "comment_count",
        ]],
        on="influencer_name",
        how="left",
    )
    # Yorum verisi olmayan influencer'lar için varsayılan değer
    for col, default in {
        "positive_comment_ratio" : 50.0,
        "negative_comment_ratio" : 20.0,
        "neutral_comment_ratio"  : 30.0,
        "avg_comment_sentiment"  : 0.5,
        "comment_count"          : 0,
    }.items():
        influencer_summary[col] = influencer_summary[col].fillna(default)

    print("  ✅ Yorum duygu metrikleri influencer özetine eklendi")
    print(f"\n  Yorum pozitif ort: {influencer_summary['positive_comment_ratio'].mean():.1f}%")
    print(f"  Yorum negatif ort: {influencer_summary['negative_comment_ratio'].mean():.1f}%")
else:
    # Yorum yok: sütunları sıfır ile doldur (ML pipeline tutarlılığı için)
    for col, default in {
        "positive_comment_ratio" : 50.0,
        "negative_comment_ratio" : 20.0,
        "neutral_comment_ratio"  : 30.0,
        "avg_comment_sentiment"  : 0.5,
        "comment_count"          : 0,
    }.items():
        influencer_summary[col] = default

print("✅ Duygu özeti fenomen bazına çevrildi")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 6 — SAHTE TAKİPÇİ TESPİTİ + K-MEANS
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 6 — SAHTE TAKİPÇİ TESPİTİ + KÜMELEME")
print("=" * 65)

from influencer_features import apply_all_features
influencer_summary = apply_all_features(influencer_summary)
print("✅ Sahte takipçi tespiti ve clustering tamamlandı")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 6.5 — SECONDARY TAG HESAPLAMA
# ════════════════════════════════════════════════════════════════════════════

def _compute_audience_type(row):
    cat  = str(row.get("main_category", "")).lower()
    tags = str(row.get("clean_tags_all", "")).lower()
    out  = []
    if any(k in tags for k in ["gaming","valorant","minecraft","meme","twitch","gen z","fortnite"]):
        out.append("gen_z")
    if any(k in tags for k in ["lifestyle","travel","fitness","coffee","aesthetic","vlog"]):
        out.append("millennials")
    if cat in ["finance_business","technology"]:
        out.append("professionals")
    if any(k in tags for k in ["ogrenci","university","student","egitim","sinav","ders"]):
        out.append("students")
    if any(k in tags for k in ["anne","bebek","mother","family","cocuk","motherhood","hamilelik"]):
        out.append("parents")
    if cat in ["beauty_fashion"] or any(k in tags for k in ["makeup","skincare","beauty","fashion","moda"]):
        out.append("women_audience")
    if cat in ["gaming","sports"] or any(k in tags for k in ["gaming","futbol","motorsports","formula1","nba"]):
        out.append("men_audience")
    return ",".join(dict.fromkeys(out)) or "general"


def _compute_engagement_type(row):
    er    = row.get("engagement_rate", 0)
    reach = row.get("avg_post_reach", 0)
    fol   = max(row.get("latest_followers", 1), 1)
    cat   = str(row.get("main_category", "")).lower()
    tags  = str(row.get("clean_tags_all", "")).lower()
    out   = []
    if er > 5:                                    out.append("high_engagement")
    if reach / fol > 0.3:                         out.append("viral_content")
    if fol < 50_000 and er > 5:                  out.append("niche_creator")
    if cat in ["technology","finance_business"] or any(k in tags for k in ["egitim","education","ogren"]):
        out.append("educational_content")
    if cat in ["lifestyle","travel"]:             out.append("storytelling")
    if cat in ["gaming","entertainment"] or any(k in tags for k in ["meme","komedi","comedy","mizah"]):
        out.append("meme_based")
    if cat in ["beauty_fashion","travel"] and er > 2:
        out.append("aesthetic_content")
    return ",".join(dict.fromkeys(out)) or "standard"


def _compute_content_tone(row):
    cat   = str(row.get("main_category", "")).lower()
    tags  = str(row.get("clean_tags_all", "")).lower()
    pos_r = row.get("positive_ratio", 50)
    out   = []
    if cat in ["technology","finance_business"]:  out.append("professional")
    if cat in ["gaming","entertainment"] or any(k in tags for k in ["komedi","comedy","meme","funny","mizah"]):
        out.append("humorous")
    if any(k in tags for k in ["luxury","luks","versace","louisvuitton","gucci","prada","hermes"]):
        out.append("luxury")
    if cat in ["technology","finance_business"] or any(k in tags for k in ["egitim","ogren","education"]):
        out.append("educational")
    if cat in ["fitness_health"] or any(k in tags for k in ["motivasyon","motivation","inspiration"]):
        out.append("inspirational")
    if pos_r > 75 and cat in ["lifestyle"]:       out.append("emotional")
    if pos_r > 70:                                out.append("authentic")
    if cat in ["sports","fitness_health","gaming"]: out.append("energetic")
    if any(k in tags for k in ["minimalism","minimalist","minimal"]):
        out.append("minimalist")
    return ",".join(dict.fromkeys(out)) or "neutral"


def _compute_brand_fit(row):
    cat  = str(row.get("main_category", "")).lower()
    tags = str(row.get("clean_tags_all", "")).lower()
    fol  = row.get("latest_followers", 0)
    risk = row.get("fake_followers_risk", 100)
    out  = []
    if any(k in tags for k in ["luxury","luks","versace","louisvuitton","gucci","prada"]) \
       and fol > 100_000 and risk < 50:
        out.append("luxury_brand_fit")
    if cat in ["beauty_fashion"]:               out.append("fashion_brand_fit")
    if cat in ["technology","gaming"]:          out.append("tech_brand_fit")
    if cat in ["gaming"]:                       out.append("gaming_brand_fit")
    if cat in ["sports","fitness_health"]:      out.append("sports_brand_fit")
    if cat in ["fitness_health"] or any(k in tags for k in ["wellness","saglik","yoga","pilates","spa"]):
        out.append("wellness_brand_fit")
    if cat in ["food_gastronomy"]:              out.append("food_brand_fit")
    if cat in ["finance_business"]:             out.append("fintech_brand_fit")
    if cat in ["travel"]:                       out.append("travel_brand_fit")
    return ",".join(dict.fromkeys(out)) or "general"


influencer_summary["audience_type"]   = influencer_summary.apply(_compute_audience_type,  axis=1)
influencer_summary["engagement_type"] = influencer_summary.apply(_compute_engagement_type, axis=1)
influencer_summary["content_tone"]    = influencer_summary.apply(_compute_content_tone,    axis=1)
influencer_summary["brand_fit_tags"]  = influencer_summary.apply(_compute_brand_fit,       axis=1)

print("✅ Secondary tag'ler hesaplandi (audience_type / engagement_type / content_tone / brand_fit_tags)")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 7 — UYGUNLUK ETİKETİ VE MODEL EĞİTİMİ
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 7 — UYGUNLUK ETİKETİ + ML MODEL EĞİTİMİ")
print("=" * 65)

CAMPAIGN_COLUMNS = {
    "spor_kampanyasi"     : "sim_spor_kampanyasi",
    "moda_kampanyasi"     : "sim_moda_kampanyasi",
    "teknoloji_kampanyasi": "sim_teknoloji_kampanyasi",
    "yemek_kampanyasi"    : "sim_yemek_kampanyasi",
    "annebebek_kampanyasi": "sim_annebebek_kampanyasi",
    "oyun_kampanyasi"     : "sim_oyun_kampanyasi",
}

rows = []
for _, inf in influencer_summary.iterrows():
    for campaign_name, sim_col in CAMPAIGN_COLUMNS.items():
        sfs       = inf[sim_col]
        nfs       = inf["NFS"]
        pos_ratio = inf["positive_ratio"]

        if sfs > 0.35 and nfs > 25 and pos_ratio > 60:
            label = "uygun"
        elif sfs < 0.20 or nfs < 15 or pos_ratio < 45:
            label = "uygun_degil"
        else:
            label = "orta"

        rows.append({
            "influencer_name"        : inf["influencer_name"],
            "campaign"               : campaign_name,
            "category"               : inf["category"],
            "account_type"           : inf["account_type"],
            "engagement_rate"        : inf["engagement_rate"],
            "posts_per_month"        : inf["posts_per_month"],
            "NFS"                    : nfs,
            "SFS"                    : sfs,
            "positive_ratio"         : pos_ratio,
            "negative_ratio"         : inf["negative_ratio"],
            "avg_sentiment_score"    : inf["avg_sentiment_score"],
            # ── Yorum kaynaklı yeni feature'lar ─────────────────────────────
            "positive_comment_ratio" : inf.get("positive_comment_ratio", 50.0),
            "negative_comment_ratio" : inf.get("negative_comment_ratio", 20.0),
            "neutral_comment_ratio"  : inf.get("neutral_comment_ratio",  30.0),
            "avg_comment_sentiment"  : inf.get("avg_comment_sentiment",   0.5),
            "comment_count"          : inf.get("comment_count",             0),
            "label"                  : label,
        })

df_model = pd.DataFrame(rows)
print(f"✅ Model veri seti: {len(df_model)} satır ({len(influencer_summary)} fenomen × {len(CAMPAIGN_COLUMNS)} kampanya)")
print("\nEtiket dağılımı:")
print(df_model["label"].value_counts())

# ── Encoding ve train/test bölme ─────────────────────────────────────────────
df_encoded = pd.get_dummies(df_model, columns=["category","account_type","campaign"])
X = df_encoded.drop(columns=["influencer_name","label"])
y = df_encoded["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ── XGBoost ──────────────────────────────────────────────────────────────────
from xgboost import XGBClassifier

le = LabelEncoder()
y_train_enc = le.fit_transform(y_train)
y_test_enc  = le.transform(y_test)
y_enc       = le.transform(y)

xgb_model = XGBClassifier(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=6,
    eval_metric="mlogloss",
    random_state=42,
)
xgb_model.fit(X_train, y_train_enc)
y_pred_xgb = le.inverse_transform(xgb_model.predict(X_test))

print("\n=== XGBoost ===")
print(classification_report(y_test, y_pred_xgb))
cv_xgb = cross_val_score(xgb_model, X, y_enc, cv=5, scoring="f1_weighted")
print(f"5-Fold CV F1: {cv_xgb.mean():.3f} ± {cv_xgb.std():.3f}")

# ── LightGBM ─────────────────────────────────────────────────────────────────
from lightgbm import LGBMClassifier

lgbm_model = LGBMClassifier(
    n_estimators=100, learning_rate=0.1,
    class_weight="balanced", random_state=42, verbose=-1,
)
lgbm_model.fit(X_train, y_train)
y_pred_lgbm = lgbm_model.predict(X_test)

print("\n=== LightGBM ===")
print(classification_report(y_test, y_pred_lgbm))
cv_lgbm = cross_val_score(lgbm_model, X, y, cv=5, scoring="f1_weighted")
print(f"5-Fold CV F1: {cv_lgbm.mean():.3f} ± {cv_lgbm.std():.3f}")

# ── Logistic Regression ───────────────────────────────────────────────────────
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline as SkPipeline

lr_pipeline = SkPipeline([
    ("scaler", StandardScaler()),
    ("lr", LogisticRegression(
        max_iter=1000, class_weight="balanced",
        solver="lbfgs", random_state=42,
    )),
])
lr_pipeline.fit(X_train, y_train)
y_pred_lr = lr_pipeline.predict(X_test)

print("\n=== Logistic Regression ===")
print(classification_report(y_test, y_pred_lr))
cv_lr = cross_val_score(lr_pipeline, X, y, cv=5, scoring="f1_weighted")
print(f"5-Fold CV F1: {cv_lr.mean():.3f} ± {cv_lr.std():.3f}")

# ── Modelleri kaydet ─────────────────────────────────────────────────────────
joblib.dump(xgb_model,             PIPELINE_DIR / "best_model_xgb.pkl")
joblib.dump(lgbm_model,            PIPELINE_DIR / "best_model_lgbm.pkl")
joblib.dump(lr_pipeline,           PIPELINE_DIR / "best_model_lr.pkl")
joblib.dump(le,                    PIPELINE_DIR / "label_encoder.pkl")
joblib.dump(X.columns.tolist(),    PIPELINE_DIR / "feature_columns.pkl")

print("\n✅ Modeller kaydedildi:")
print("   best_model_xgb.pkl  — XGBoost")
print("   best_model_lgbm.pkl — LightGBM")
print("   best_model_lr.pkl   — Logistic Regression")
print("   label_encoder.pkl   — Etiket encoder")
print("   feature_columns.pkl — Giriş sütunları")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 8 — MODEL DOĞRULAMA VE RAPORLAMA
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 8 — MODEL DOĞRULAMA VE RAPORLAMA")
print("=" * 65)

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    confusion_matrix, ConfusionMatrixDisplay,
)

REPORTS_DIR = ROOT_DIR / "docs" / "model_reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ── 8.1 Tüm modelleri karşılaştır ────────────────────────────────────────────
print("\n--- 8.1 Model Karşılaştırması ---")

rf_model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
rf_model.fit(X_train, y_train)
y_pred_rf = rf_model.predict(X_test)

models = {
    "XGBoost"            : (y_pred_xgb,  le.inverse_transform(y_test_enc)),
    "LightGBM"           : (y_pred_lgbm, y_test.values),
    "RandomForest"       : (y_pred_rf,   y_test.values),
    "LogisticRegression" : (y_pred_lr,   y_test.values),
}

summary_rows = []
for model_name, (y_pred, y_true) in models.items():
    acc  = accuracy_score(y_true, y_pred)
    f1   = f1_score(y_true, y_pred, average="weighted")
    prec = precision_score(y_true, y_pred, average="weighted", zero_division=0)
    rec  = recall_score(y_true, y_pred, average="weighted", zero_division=0)
    summary_rows.append({
        "Model"    : model_name,
        "Accuracy" : round(acc,  4),
        "F1 (W)"   : round(f1,   4),
        "Precision": round(prec, 4),
        "Recall"   : round(rec,  4),
    })
    print(f"  {model_name:15s} → Acc: {acc:.3f}  F1: {f1:.3f}")

df_summary = pd.DataFrame(summary_rows).set_index("Model")
print("\n" + df_summary.to_string())

# ── 8.2 Overfitting kontrolü (Train vs Test) ──────────────────────────────────
print("\n--- 8.2 Overfitting Kontrolü (Train vs Test Accuracy) ---")

overfit_rows = []
# XGBoost
xgb_train_acc = accuracy_score(y_train, le.inverse_transform(xgb_model.predict(X_train)))
xgb_test_acc  = accuracy_score(y_test,  y_pred_xgb)
# LightGBM
lgbm_train_acc = accuracy_score(y_train, lgbm_model.predict(X_train))
lgbm_test_acc  = accuracy_score(y_test,  y_pred_lgbm)
# RandomForest
rf_train_acc = accuracy_score(y_train, rf_model.predict(X_train))
rf_test_acc  = accuracy_score(y_test,  y_pred_rf)

lr_train_acc = accuracy_score(y_train, lr_pipeline.predict(X_train))
lr_test_acc  = accuracy_score(y_test,  y_pred_lr)

overfit_rows = [
    ("XGBoost",            xgb_train_acc,  xgb_test_acc),
    ("LightGBM",           lgbm_train_acc, lgbm_test_acc),
    ("RandomForest",       rf_train_acc,   rf_test_acc),
    ("LogisticRegression", lr_train_acc,   lr_test_acc),
]
print(f"  {'Model':15s} {'Train Acc':>10} {'Test Acc':>10} {'Fark':>8}")
print("  " + "-" * 48)
for name, tr, te in overfit_rows:
    gap = tr - te
    flag = " ← OVERFITTING" if gap > 0.10 else ""
    print(f"  {name:15s} {tr:10.3f} {te:10.3f} {gap:8.3f}{flag}")

# ── 8.3 Cross-Validation (5-Fold) ────────────────────────────────────────────
print("\n--- 8.3 5-Fold Cross Validation F1 Skorları ---")

cv_results = {}
for model_name, model, y_labels in [
    ("XGBoost",            xgb_model,   y_enc),
    ("LightGBM",           lgbm_model,  y),
    ("RandomForest",       rf_model,    y),
    ("LogisticRegression", lr_pipeline, y),
]:
    cv = cross_val_score(model, X, y_labels, cv=5, scoring="f1_weighted")
    cv_results[model_name] = cv
    print(f"  {model_name:15s} F1 = {cv.mean():.3f} ± {cv.std():.3f}  [{', '.join(f'{v:.3f}' for v in cv)}]")

# ── 8.4 Confusion Matrix grafikleri ─────────────────────────────────────────
print("\n--- 8.4 Confusion Matrix Grafikleri kaydediliyor ---")

class_names = sorted(y_test.unique())
fig, axes = plt.subplots(1, 4, figsize=(20, 5))
fig.suptitle("Confusion Matrix Karşılaştırması", fontsize=14, fontweight="bold")

plot_data = [
    ("XGBoost",            y_test.values, y_pred_xgb),
    ("LightGBM",           y_test.values, y_pred_lgbm),
    ("RandomForest",       y_test.values, y_pred_rf),
    ("LogisticRegression", y_test.values, y_pred_lr),
]
for ax, (name, y_true, y_pred) in zip(axes, plot_data):
    cm   = confusion_matrix(y_true, y_pred, labels=class_names)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)
    disp.plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"{name}\nAcc={accuracy_score(y_true,y_pred):.3f}", fontsize=11)
    ax.tick_params(axis="x", rotation=15)

plt.tight_layout()
cm_path = REPORTS_DIR / "confusion_matrices.png"
plt.savefig(cm_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Kaydedildi: {cm_path}")

# ── 8.5 Feature Importance ──────────────────────────────────────────────────
print("\n--- 8.5 Feature Importance (XGBoost) ---")

feat_imp = pd.Series(xgb_model.feature_importances_, index=X.columns)
top15    = feat_imp.nlargest(15).sort_values()

fig, ax = plt.subplots(figsize=(9, 6))
# Yorum kaynaklı feature'ları farklı renkle vurgula
colors_fi = [
    "#f59e0b" if any(k in feat for k in ["comment","comment_ratio","comment_sentiment"])
    else "#6ee7b7"
    for feat in top15.index
]
bars = ax.barh(top15.index, top15.values, color=colors_fi, edgecolor="none")
ax.set_xlabel("Importance", fontsize=11)
ax.set_title("XGBoost — En Önemli 15 Özellik\n(🟡 Yorum kaynaklı feature'lar)", fontsize=12, fontweight="bold")
ax.spines[["top","right","left"]].set_visible(False)
ax.tick_params(axis="y", labelsize=9)
for bar in bars:
    w = bar.get_width()
    ax.text(w + 0.001, bar.get_y() + bar.get_height()/2,
            f"{w:.4f}", va="center", fontsize=8)
plt.tight_layout()
fi_path = REPORTS_DIR / "feature_importance.png"
plt.savefig(fi_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Kaydedildi: {fi_path}")
print("\n  Top 10 Feature:")
for feat, imp in feat_imp.nlargest(10).items():
    tag = " ← YORUM" if any(k in feat for k in ["comment"]) else ""
    print(f"    {feat:40s} {imp:.4f}{tag}")

# ── 8.5b Yorum feature'larının model katkısı raporu ─────────────────────────
if _COMMENTS_AVAILABLE:
    print("\n--- 8.5b Yorum Feature Katkısı ---")
    comment_features = [f for f in X.columns if "comment" in f]
    if comment_features:
        comment_total_imp = feat_imp[comment_features].sum()
        other_imp         = feat_imp.drop(index=comment_features, errors="ignore").sum()
        print(f"  Yorum feature'larının toplam önemi : {comment_total_imp:.4f} ({comment_total_imp*100:.1f}%)")
        print(f"  Diğer feature'ların toplam önemi   : {other_imp:.4f} ({other_imp*100:.1f}%)")
        print(f"\n  Yorum feature detayları:")
        for feat in comment_features:
            if feat in feat_imp.index:
                print(f"    {feat:40s} {feat_imp[feat]:.4f}")

# ── 8.6 Model Karşılaştırma Grafiği ─────────────────────────────────────────
print("\n--- 8.6 Model Karşılaştırma Grafiği kaydediliyor ---")

metrics      = ["Accuracy", "F1 (W)", "Precision", "Recall"]
model_names  = df_summary.index.tolist()
x            = np.arange(len(metrics))
width        = 0.20
colors       = ["#6ee7b7", "#818cf8", "#f472b6", "#fbbf24"]

fig, ax = plt.subplots(figsize=(11, 5))
for i, (name, color) in enumerate(zip(model_names, colors)):
    vals = [df_summary.loc[name, m] for m in metrics]
    rects = ax.bar(x + i * width, vals, width, label=name, color=color, alpha=0.88)
    for rect in rects:
        h = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2, h + 0.005,
                f"{h:.3f}", ha="center", va="bottom", fontsize=8)

ax.set_xticks(x + width)
ax.set_xticklabels(metrics, fontsize=11)
ax.set_ylim(0, 1.12)
ax.set_ylabel("Skor", fontsize=11)
ax.set_title("Model Performans Karşılaştırması", fontsize=13, fontweight="bold")
ax.legend(fontsize=10)
ax.spines[["top","right"]].set_visible(False)
ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
plt.tight_layout()
comp_path = REPORTS_DIR / "model_comparison.png"
plt.savefig(comp_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Kaydedildi: {comp_path}")

# ── 8.7 Yazılı Rapor ────────────────────────────────────────────────────────
report_path = REPORTS_DIR / "model_validation_report.txt"
with open(report_path, "w", encoding="utf-8") as rpt:
    rpt.write("=" * 65 + "\n")
    rpt.write("FENOMEN-MARKA ESLESTIRME — MODEL DOGRULAMA RAPORU\n")
    rpt.write("TÜBİTAK 2209-A Projesi\n")
    rpt.write("=" * 65 + "\n\n")

    rpt.write("1. VERI SETI OZETI\n")
    rpt.write("-" * 40 + "\n")
    rpt.write(f"  Toplam örnek (fenomen × kampanya) : {len(df_model)}\n")
    rpt.write(f"  Eğitim seti                       : {len(X_train)}\n")
    rpt.write(f"  Test seti                          : {len(X_test)}\n")
    rpt.write(f"  Sınıf sayısı                       : {len(class_names)} ({', '.join(class_names)})\n")
    rpt.write("\n  Etiket dağılımı:\n")
    for lbl, cnt in df_model["label"].value_counts().items():
        rpt.write(f"    {lbl:15s}: {cnt}\n")

    rpt.write("\n2. MODEL PERFORMANS KARSILASTIRMASI\n")
    rpt.write("-" * 40 + "\n")
    rpt.write(df_summary.to_string() + "\n")

    rpt.write("\n3. OVERFITTING ANALIZI (Train vs Test)\n")
    rpt.write("-" * 40 + "\n")
    rpt.write(f"  {'Model':15s} {'Train':>8} {'Test':>8} {'Fark':>8}\n")
    for name, tr, te in overfit_rows:
        gap  = tr - te
        note = " [OVERFITTING]" if gap > 0.10 else " [OK]"
        rpt.write(f"  {name:15s} {tr:8.3f} {te:8.3f} {gap:8.3f}{note}\n")

    rpt.write("\n4. CROSS VALIDATION (5-Fold F1 Weighted)\n")
    rpt.write("-" * 40 + "\n")
    for name, cv in cv_results.items():
        rpt.write(f"  {name:15s}: {cv.mean():.3f} ± {cv.std():.3f}\n")

    rpt.write("\n5. SINIFLANDIRMA RAPORLARI\n")
    rpt.write("-" * 40 + "\n")
    for model_name, (y_pred, y_true) in models.items():
        rpt.write(f"\n  [{model_name}]\n")
        rpt.write(classification_report(y_true, y_pred, zero_division=0))

    rpt.write("\n6. FEATURE IMPORTANCE (XGBoost — Top 15)\n")
    rpt.write("-" * 40 + "\n")
    for feat, imp in feat_imp.nlargest(15).items():
        rpt.write(f"  {feat:40s} {imp:.4f}\n")

    rpt.write("\n7. URETILEN GORSELLER\n")
    rpt.write("-" * 40 + "\n")
    rpt.write(f"  {cm_path}\n")
    rpt.write(f"  {fi_path}\n")
    rpt.write(f"  {comp_path}\n")

print(f"\n  Rapor kaydedildi: {report_path}")
print("\nModel raporlari klasoru: model_reports/")
print("  confusion_matrices.png  — 3 modelin confusion matrix karsilastirmasi")
print("  feature_importance.png  — XGBoost top 15 ozellik onemliligi")
print("  model_comparison.png    — Acc / F1 / Precision / Recall grafigi")
print("  model_validation_report.txt — Tam metin rapor")

# ════════════════════════════════════════════════════════════════════════════
# BÖLÜM 9 — CHECKPOINT KAYDET (app.py için)
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("BÖLÜM 9 — CHECKPOINT KAYDET")
print("=" * 65)

import pickle

CHECKPOINT_SAFE = PIPELINE_DIR / "influencer_summary_checkpoint_safe.pkl"
for col in list(influencer_summary.columns):
    if not isinstance(influencer_summary[col].dtype, np.dtype):
        influencer_summary[col] = influencer_summary[col].astype(object)
influencer_summary.columns = pd.Index([str(c) for c in influencer_summary.columns], dtype=object)
influencer_summary.index = pd.Index(influencer_summary.index.to_numpy(), dtype=object)

with open(CHECKPOINT, "wb") as f:
    pickle.dump(influencer_summary, f)

with open(CHECKPOINT_SAFE, "wb") as f:
    pickle.dump(influencer_summary, f)

print(f"Checkpoint guncellendi ({len(influencer_summary)} fenomen)")
print(f"Uyumlu checkpoint guncellendi: {CHECKPOINT_SAFE.name}")
print("\nPipeline tamamlandi. app.py'i baslatmak icin: python app.py")
