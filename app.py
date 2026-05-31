# =============================================================================
# app.py — Flask REST API Sunucusu
# =============================================================================
# GÖREV   : Eğitilmiş modelleri ve checkpoint'i yükleyerek HTTP üzerinden
#           fenomen önerisi sunan REST API'yi ayağa kaldırır.
#
# ÇALIŞMA : python app.py  →  http://localhost:5000
#
# ENDPOINT'LER:
#   POST /recommend              → Marka metnine göre fenomen öner
#   GET  /influencers            → Tüm fenomen listesi (filtreli)
#   GET  /influencers/<n>/similar→ Benzer fenomenler (K-Means cluster)
#   GET  /campaigns              → 10 kampanya tanımı
#   GET  /stats                  → Sistem istatistikleri
#   GET  /                       → Frontend arayüzü
#
# BAĞIMLILIKLAR (pipeline/ dizininden yüklenir):
#   influencer_summary_checkpoint.pkl  — 244 fenomenin önceden hesaplanmış skorları
#   best_model_xgb.pkl / lgbm.pkl      — XGBoost & LightGBM sınıflandırıcıları
#   label_encoder.pkl / feature_columns.pkl
#
# SKOR FORMÜLLERİ:
#   NFS   = Ridge(engagement_rate, FGR, posts_per_month) → eng_auth etiketi (pipeline/nfs_scoring.py)
#   SFS   = cosine_sim(SBERT(marka), SBERT(fenomen)) × 100
#   BAS   = SFS×0.35 + NFS×0.30 + positive_ratio×0.25 + (100-fake_risk)×0.10
#   FINAL = SFS×0.35 + NFS×0.25 + CFS×0.20 + positive_ratio×0.10 + (100-fake_risk)×0.10
# =============================================================================

import os
import sys

# XGBoost + PyTorch/OpenMP ayni process'te coker (macOS SIGSEGV); once ayarla
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
# macOS MPS (Metal GPU) matris carpiminda SIGABRT — SBERT/PyTorch yalnizca CPU
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import pickle
import re
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from numpy.linalg import norm
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

# MongoDB destegi (opsiyonel — yoksa pkl ile calisir)
try:
    from db.mongo_client import get_collection, is_mongo_available
except ImportError:
    def get_collection(): return None
    def is_mongo_available(): return False

# ── Uygulama ve dizin ayarlari ──────────────────────────────────────────────
app = Flask(__name__, static_folder="frontend/static", template_folder="frontend")
CORS(app)

BASE_DIR     = Path(__file__).parent          # TezBitirme/ (root)
PIPELINE_DIR = BASE_DIR / "pipeline"         # pipeline/ — modeller ve checkpoint

# ── Kampanya sabitleri ───────────────────────────────────────────────────────
CAMPAIGN_NAMES = [
    "beauty_fashion",
    "lifestyle",
    "fitness_health",
    "food_gastronomy",
    "technology",
    "gaming",
    "travel",
    "finance_business",
    "entertainment",
    "sports",
]

CAMPAIGN_TEXTS = {
    "beauty_fashion"  : (
        "Guzellik, moda ve kisisel stil markasiyiz. "
        "Skincare urunleri, makyaj teknikleri, parfum, kiyafet, aksesuar, kombin onerileri, "
        "trend analizleri, moda haftasi, tasarimci markalar, kozmetik urunler."
    ),
    "lifestyle"       : (
        "Kisisel gelisim, yasam tarzi ve hayat koclugu markasiyiz. "
        "Oz gelisim, motivasyon, mindset degisimi, kisisel donusum, hedef belirleme, "
        "aliskanlık olusturma, uretkenlik, zaman yonetimi, ic ses, farkındalık, "
        "yasama anlam katma, ilham, pozitif dusunce, ruhsal gelisim, "
        "hayat felsefesi, minimalizm, ic huzur, denge, bilinc."
    ),
    "fitness_health"  : (
        "Spor, antrenman ve fiziksel saglik markasiyiz. "
        "Spor salonu egzersizleri, kas gelistirme, kilo verme, kondisyon, "
        "kosu, maraton, bisiklet, yuzme, diyetisyen, beslenme planlari, "
        "protein, suplemen, vücut gelistirme, atletik performans, "
        "pilates hareketleri, spor ekipmani incelemeleri."
    ),
    "food_gastronomy" : (
        "Gida, yemek ve gastronomi markasiyiz. "
        "Yemek tarifleri, mutfak ipuclari, restoran incelemeleri, gurme deneyimler, "
        "uluslararasi mutfaklar, sokak lezzetleri, yemek fotografi."
    ),
    "technology"      : (
        "Teknoloji, yazilim ve dijital inovasyon markasiyiz. "
        "Akilli cihaz incelemeleri, uygulama gelistirme, yapay zeka, makine ogrenmesi, "
        "kodlama, programlama, gadget, siber guvenlik, cloud."
    ),
    "gaming"          : (
        "Oyun, e-spor ve gaming kulturu markasiyiz. "
        "Oyun incelemeleri, canli yayin, Twitch, YouTube Gaming, e-spor turnuvalari, "
        "gaming ekipmani, konsol, PC, mobil oyun."
    ),
    "travel"          : (
        "Seyahat, turizm ve macera markasiyiz. "
        "Dunya turu, otel incelemeleri, ucuz bilet, destinasyon rehberleri, "
        "yurt disi tatil, kamp, backpacking, seyahat ipuclari."
    ),
    "finance_business": (
        "Finans, yatirim ve is dunyasi markasiyiz. "
        "Borsa, hisse senedi, kripto para, yatirim fonlari, portfoy yonetimi, "
        "butce planlama, girisimcilik, sirket kurma, is plani, B2B satis, "
        "kurumsal strateji, ekonomi haberleri, vergi, muhasebe."
    ),
    "entertainment"   : (
        "Eglence, medya ve pop kultur markasiyiz. "
        "Film izleme, dizi tavsiyesi, muzik, konser, stand-up, mizah, "
        "celebrity haberleri, sosyal medya trendi, viral icerik."
    ),
    "sports"          : (
        "Takim sporlari ve atletizm markasiyiz. "
        "Futbol, basketbol, voleybol, tenis, golf, maraton, olimpiyat, "
        "takim haberleri, stat, sampiyonluk, spor yorumculugu."
    ),
}

# Checkpoint kolonlari: sim_spor_kampanyasi, sim_moda_kampanyasi ...
SIM_COLS = [f"sim_{c}" for c in CAMPAIGN_NAMES]

# Hibrit kampanya tespiti: SBERT + keyword bonus
# Her eslesme raw cosine skoruna +0.05 ekler (softmax oncesi)
CAMPAIGN_KEYWORDS: dict[str, list[str]] = {
    "lifestyle"       : ["yasam", "hayat", "gelisim", "motivasyon", "donusum",
                         "mindset", "kisisel", "ruhsal", "ilham", "hedef",
                         "huzur", "denge", "farkındalık", "bilinc", "oz",
                         "coaching", "coach", "rehber", "felsefe", "anlam"],
    "finance_business": ["borsa", "hisse", "kripto", "bitcoin", "yatirim",
                         "finans", "girisim", "sirket", "ekonomi", "butce",
                         "fintech", "muhasebe", "gelir", "para", "kazanc",
                         "portfoy", "fon", "banka", "kredi", "vergi"],
    "fitness_health"  : ["spor", "antrenman", "fitness", "gym", "kas",
                         "protein", "diyetisyen", "beslenme", "kilo",
                         "egzersiz", "kondisyon", "atletizm", "vucut"],
    "beauty_fashion"  : ["moda", "kombin", "makyaj", "skincare", "trend",
                         "kiyafet", "guzellik", "parfum", "stil", "aksesuar"],
    "food_gastronomy" : ["yemek", "tarif", "restoran", "mutfak", "lezzet",
                         "gastronomi", "gurme", "pisme", "tatli", "kahve"],
    "technology"      : ["teknoloji", "yazilim", "kodlama", "yapay", "zeka",
                         "uygulama", "dijital", "siber", "robot", "otomasyon"],
    "gaming"          : ["oyun", "e-spor", "esport", "gaming", "twitch",
                         "konsol", "playstation", "xbox", "steam", "gamer"],
    "travel"          : ["seyahat", "tatil", "tur", "destinasyon", "ucus",
                         "otel", "vize", "pasaport", "gezi", "macera"],
    "entertainment"   : ["film", "dizi", "muzik", "eglence", "komedi",
                         "sinema", "konser", "youtuber", "tiktok", "reels"],
    "sports"          : ["futbol", "basketbol", "voleybol", "tenis", "mac",
                         "takim", "sampiyonluk", "lig", "gol", "basket"],
}

# ── Veri ve model yukleme ────────────────────────────────────────────────────
print("Veri ve modeller yukleniyor...")

_ckpt_candidates = [
    PIPELINE_DIR / "influencer_summary_checkpoint_safe.pkl",
    PIPELINE_DIR / "influencer_summary_checkpoint.pkl",
]
_ckpt_path = next((p for p in _ckpt_candidates if p.exists()), _ckpt_candidates[-1])
try:
    with open(_ckpt_path, "rb") as f:
        influencer_summary: pd.DataFrame = pickle.load(f)
    import os as _os
    _mtime = _os.path.getmtime(_ckpt_path)
    print(f"OK  Checkpoint yuklendi: {len(influencer_summary)} fenomen "
          f"(guncelleme: {pd.Timestamp(_mtime, unit='s').strftime('%Y-%m-%d %H:%M')})")
except FileNotFoundError:
    import sys as _sys
    print("HATA: Checkpoint bulunamadi. Once analiz_pipeline.py calistirin.", file=_sys.stderr)
    _sys.exit(1)
except Exception as _e:
    import sys as _sys
    print(f"HATA: Checkpoint yuklenemedi: {_e}", file=_sys.stderr)
    _sys.exit(1)

is_mongo_active = False
_mongo_col = None
try:
    _mongo_col = get_collection()
    is_mongo_active = _mongo_col is not None
except Exception as _e:
    print(f"UYARI: MongoDB kontrolu basarisiz ({_e}). pkl checkpoint aktif.")

# MongoDB varsa ana veri kaynagi olarak kullan; bos/kapaliysa pkl ile devam et.
if is_mongo_active:
    try:
        _mongo_count = _mongo_col.count_documents({})
        if _mongo_count > 0:
            _mongo_records = list(_mongo_col.find({}, {"_id": 0}))
            influencer_summary = pd.DataFrame(_mongo_records)
            print(f"OK  MongoDB veri kaynagi aktif: {_mongo_count} fenomen")
        else:
            print("UYARI: MongoDB koleksiyonu bos. pkl checkpoint aktif.")
    except Exception as _e:
        print(f"UYARI: MongoDB okuma basarisiz ({_e}). pkl checkpoint aktif.")

# Eksik sutunlari guveli tamamla
_defaults = {
    "estimated_gender"       : "belirsiz",
    "gender_confidence"      : 0.5,
    "risk_category"          : "bilinmiyor",
    "fake_followers_risk"    : 0.0,
    "similarity_cluster"     : 0,
    "positive_ratio"         : 50.0,
    "negative_ratio"         : 20.0,
    "avg_sentiment_score"    : 0.5,
    "main_category"          : "",
    "audience_type"          : "",
    "engagement_type"        : "",
    "content_tone"           : "",
    "brand_fit_tags"         : "",
    "clean_tags_all"         : "",
    "data_source"            : "unknown",
    # Yorum kaynaklı metrikler (influencer_comments.csv yoksa varsayılan)
    "positive_comment_ratio" : 50.0,
    "negative_comment_ratio" : 20.0,
    "neutral_comment_ratio"  : 30.0,
    "avg_comment_sentiment"  : 0.5,
    "comment_count"          : 0,
}
for col, val in _defaults.items():
    if col not in influencer_summary.columns:
        influencer_summary[col] = val

if "influencer_name" in influencer_summary.columns:
    inferred_source = influencer_summary["influencer_name"].astype(str).apply(
        lambda n: "synthetic" if re.match(r"^@influencer\d+$", n) else "instagram"
    )
    influencer_summary["data_source"] = np.where(
        influencer_summary["data_source"].isin(["instagram", "synthetic"]),
        influencer_summary["data_source"],
        inferred_source,
    )

# Eksik kampanya sim sutunlari sifirla
for c in SIM_COLS:
    if c not in influencer_summary.columns:
        influencer_summary[c] = 0.0

# ── ML Modeli yukle ──────────────────────────────────────────────────────────
_xgb_path  = PIPELINE_DIR / "best_model_xgb.pkl"
_le_path   = PIPELINE_DIR / "label_encoder.pkl"
_feat_path = PIPELINE_DIR / "feature_columns.pkl"

xgb_model      = joblib.load(_xgb_path)  if _xgb_path.exists()  else None
label_encoder  = joblib.load(_le_path)   if _le_path.exists()   else None
feature_columns = joblib.load(_feat_path) if _feat_path.exists() else None

if xgb_model:
    print("OK  XGBoost modeli yuklendi")
else:
    print("UYARI: XGBoost modeli bulunamadi -- analiz_pipeline.py calistirin")

# ── SentenceTransformer + kampanya embedding'lerini on-cache ─────────────────
_SBERT_DEVICE = "cpu"
sbert_model = SentenceTransformer(
    "paraphrase-multilingual-MiniLM-L12-v2",
    local_files_only=True,
    device=_SBERT_DEVICE,
)


def _sbert_encode(texts):
    """Marka/fenomen embedding — her zaman CPU (macOS MPS cokmesini onler)."""
    return sbert_model.encode(
        texts,
        show_progress_bar=False,
        convert_to_numpy=True,
        device=_SBERT_DEVICE,
    )

print("Kampanya embedding'leri hazirlaniyor...")
CAMPAIGN_EMBEDDINGS: dict[str, np.ndarray] = {
    name: _sbert_encode([text])[0]
    for name, text in CAMPAIGN_TEXTS.items()
}
print(f"OK  {len(influencer_summary)} fenomen yuklendi, API hazir\n")

print("Influencer embedding cache hazirlaniyor...")
_EMBEDDING_COL = "sbert_embedding"
if _EMBEDDING_COL in influencer_summary.columns:
    try:
        _INFLUENCER_EMBEDDINGS = np.vstack(
            influencer_summary[_EMBEDDING_COL]
            .apply(lambda x: np.asarray(x, dtype=np.float32))
            .to_numpy()
        )
        print(f"OK  Embedding cache yuklendi: {_INFLUENCER_EMBEDDINGS.shape}")
    except Exception as _e:
        print(f"UYARI: Kayitli embedding kullanilamadi ({_e}); acilista yeniden hesaplaniyor.")
        _INFLUENCER_EMBEDDINGS = _sbert_encode(
            influencer_summary["clean_tags_all"].fillna("").tolist(),
        ).astype(np.float32)
else:
    _INFLUENCER_EMBEDDINGS = _sbert_encode(
        influencer_summary["clean_tags_all"].fillna("").tolist(),
    ).astype(np.float32)
    print("UYARI: Checkpoint'te sbert_embedding yok; acilista tek sefer hesaplandi.")

_INFLUENCER_EMBEDDING_NORMS = np.linalg.norm(_INFLUENCER_EMBEDDINGS, axis=1) + 1e-10

# ── TF-IDF matrisi (KFS — Keyword Frequency Score) ───────────────────────────
# Her fenomenin clean_tags_all alanındaki kelime sıklığını öğrenir.
# Sorgu anında marka metni dönüştürülür; kelime örtüşmesi olan fenomenler öne çıkar.
print("TF-IDF matrisi hazirlaniyor (KFS)...")
_tfidf_vectorizer = TfidfVectorizer(
    max_features=5000,
    ngram_range=(1, 2),
    min_df=1,
    sublinear_tf=True,        # log(1+tf): sık tekrar eden kelimelerin ağırlığını dengeler
    token_pattern=r"(?u)\b\w+\b",
)
_tfidf_matrix = _tfidf_vectorizer.fit_transform(
    influencer_summary["clean_tags_all"].fillna("").tolist()
)
print(f"OK  TF-IDF: {_tfidf_matrix.shape[0]} fenomen x {_tfidf_matrix.shape[1]} terim")

# CF benzerlik matrisi yukle (opsiyonel — build_cf_matrix.py ile olusturulur)
_cf_matrix = None
_cf_matrix_candidates = [
    PIPELINE_DIR / "cf_similarity_matrix_safe.pkl",
    PIPELINE_DIR / "cf_similarity_matrix.pkl",
]
_cf_matrix_path = next((p for p in _cf_matrix_candidates if p.exists()), _cf_matrix_candidates[-1])
try:
    _cf_matrix = joblib.load(_cf_matrix_path)
    print(f"OK  CF matrisi yuklendi: {_cf_matrix.shape[0]}x{_cf_matrix.shape[1]}")
except FileNotFoundError:
    print("UYARI: CF matrisi bulunamadi. 'python pipeline/build_cf_matrix.py' calistirin.")
except Exception as _e:
    print(f"UYARI: CF matrisi yuklenemedi: {_e}")

if not is_mongo_active:
    print("MongoDB yeniden denenmedi; pkl modu aktif kalacak.")


# ════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSIYONLAR
# ════════════════════════════════════════════════════════════════════════════

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (norm(a) * norm(b) + 1e-10))


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def calculate_bas(sfs: float, nfs: float, positive_ratio: float, fake_risk: float) -> float:
    """
    BAS = SFS*0.35 + NFS*0.30 + PositiveRatio*0.25 + (100-FakeRisk)*0.10
    Tum girdiler 0-100 olceginde.
    """
    bas = (
        float(sfs)            * 0.35 +
        float(nfs)            * 0.30 +
        float(positive_ratio) * 0.25 +
        (100.0 - float(fake_risk)) * 0.10
    )
    return round(float(np.clip(bas, 0.0, 100.0)), 2)


def compute_brand_campaign_weights(
    brand_embedding: np.ndarray, brand_text: str = ""
) -> dict[str, float]:
    """
    Hibrit kampanya agirlik hesaplama:
      1) SBERT cosine benzerlik skoru (semantik)
      2) Keyword bonus (+0.05 / eslesme, maks 0.25 kampanya basi)
    Softmax ile normalize edilmis agirliklar doner.

    Kalibrasyon notu:
      Keyword bonus SBERT skorunu (0.1–0.7 arasi) DESTEKLEMELI,
      geride birakmamali. 0.12 katsayi + temperature=15 kombinasyonu
      3 kelime eslesiminde %99 dominasyona yol aciyordu (debug/campaign ile tespit).
      Duzeltme: katsayi 0.12 → 0.05, temperature 15 → 7.
    """
    raw_scores = np.array([
        cosine_sim(brand_embedding, CAMPAIGN_EMBEDDINGS[name])
        for name in CAMPAIGN_NAMES
    ])

    # Leksikal bonus — SBERT'in zayif kaldigi Turkce terimler icin destek
    # Her keyword eslesme +0.05, maks 0.25 (eskiden 0.12 / 0.60 — manipulasyon riski)
    if brand_text:
        brand_lower = brand_text.lower()
        for i, name in enumerate(CAMPAIGN_NAMES):
            matches = sum(1 for kw in CAMPAIGN_KEYWORDS.get(name, []) if kw in brand_lower)
            raw_scores[i] += min(matches * 0.05, 0.25)

    weights = _softmax(raw_scores * 7)   # temperature=7: ayirt edici ama %99 dominasyona izin vermez
    return {name: float(w) for name, w in zip(CAMPAIGN_NAMES, weights)}


def calculate_cfs(brand_weights: dict[str, float], row: pd.Series) -> float:
    """
    Collaborative Fit Score — kampanya uzayinda is birligi filtreleme.

    CFS = Σ brand_weight[k] * sim_kampanya[k] * 100

    Mantik:
      - Marka hangi kampanya turune yakin ise o kampanyada basarili olan
        fenomenler one cikartilir.
      - sim_kampanya[k]: fenomenin k kampanyasiyla SBERT benzerlik skoru.
      - brand_weight[k]: markanin k kampanyasina olan yakinligi (softmax).
    """
    cfs = sum(
        brand_weights.get(name, 0.0) * float(row.get(f"sim_{name}", 0.0))
        for name in CAMPAIGN_NAMES
    ) * 100.0
    return round(float(np.clip(cfs, 0.0, 100.0)), 2)


def calculate_final_score(
    sfs: float, nfs: float, cfs: float,
    positive_ratio: float, fake_risk: float
) -> float:
    """
    FINAL = SFS*0.45 + NFS*0.15 + CFS*0.20 + PositiveRatio*0.10 + (100-FakeRisk)*0.10

    Degisiklik: SFS agırlığı 0.35→0.45, NFS 0.25→0.15.
    Gerekce: NFS popülerlik olcer, semantik relevance değil.
    Yüksek takipçili ama alakasız fenomenler artık öne çıkmaz.

    Ek: SFS < 35 ise ceza katsayısı uygulanır (alakasız fenomen filtresi).
    """
    score = (
        float(sfs)            * 0.45 +
        float(nfs)            * 0.15 +
        float(cfs)            * 0.20 +
        float(positive_ratio) * 0.10 +
        (100.0 - float(fake_risk)) * 0.10
    )
    # Dusuk SFS cezasi: semantik uyumu zayif fenomenleri asagi it
    if float(sfs) < 35.0:
        penalty = (35.0 - float(sfs)) * 0.4   # maks ~14 puan ceza
        score = score - penalty
    return round(float(np.clip(score, 0.0, 100.0)), 2)


def predict_ml_label(row: pd.Series, campaign_name: str) -> str:
    """XGBoost modeliyle uygunluk etiketi tahmin eder."""
    if xgb_model is None or label_encoder is None or feature_columns is None:
        return "bilinmiyor"
    try:
        base = {
            "engagement_rate"    : row.get("engagement_rate", 0),
            "FGR"                : row.get("FGR", 0),
            "posts_per_month"    : row.get("posts_per_month", 0),
            "NFS"                : row.get("NFS", 0),
            "SFS"                : row.get("sfs", 0),
            "positive_ratio"     : row.get("positive_ratio", 50),
            "negative_ratio"     : row.get("negative_ratio", 20),
            "avg_sentiment_score": row.get("avg_sentiment_score", 0.5),
        }
        sample = {col: 0 for col in feature_columns}
        sample.update(base)
        for col in [
            f"category_{row.get('category','')}",
            f"account_type_{row.get('account_type','')}",
            f"campaign_{campaign_name}",
        ]:
            if col in sample:
                sample[col] = 1

        X_sample = pd.DataFrame([sample])[feature_columns]
        pred_enc = xgb_model.predict(X_sample)[0]
        return str(label_encoder.inverse_transform([pred_enc])[0])
    except Exception:
        return "bilinmiyor"


def ml_label_adjustment(label: str) -> float:
    """
    XGBoost kararini siralama skoruna kontrollu sekilde yansitir.

    Amac:
      - SBERT/NFS/CFS skoru yuksek olsa bile modelin "uygun_degil" dedigi
        profiller ilk siralara otomatik yerlesmesin.
      - "orta" sinyali tamamen elenmesin, sadece insan onayi gerektiren
        aday olarak bir miktar asagi insin.
    """
    return {
        "uygun": 0.0,
        "orta": -6.0,
        "uygun_degil": -18.0,
        "uygunsuz": -18.0,
        "bilinmiyor": 0.0,
    }.get(str(label), 0.0)


def _top_campaign(brand_weights: dict[str, float]) -> str:
    """En yuksek agirligi olan kampanya adini doner."""
    return max(brand_weights, key=lambda k: brand_weights[k])


TIER_BONUS: dict[str, float] = {"mega": 5.0, "makro": 2.0, "mikro": 0.0}


def tier_bonus_for_account_type(account_type: str) -> float:
    """Hesap tipi icin kosullu erisim olcegi bonusunu dondurur."""
    return TIER_BONUS.get(str(account_type).lower(), 0.0)


def bounded_score(score: float) -> float:
    """Skorlari karar araligi olan 0-100 bandinda tutar."""
    return round(float(np.clip(score, 0.0, 100.0)), 2)


# Kampanya turune gore kategori uyum bonusu (final_score'a eklenir, maks +10)
# Dogru kategorideki fenomenleri one cikarir, alakasiz kategorileri asagi iter
CAMPAIGN_CATEGORY_BONUS: dict[str, dict[str, float]] = {
    # Pozitif degerler: dogru kategori bonusu
    # Negatif degerler: yanlıs kategori cezası
    "beauty_fashion"  : {"moda": 12, "lifestyle": 2,  "spor": -8,  "yemek": -8,  "teknoloji": -6},
    "lifestyle"       : {"lifestyle": 12, "spor": -8, "yemek": -8, "oyun": -8,   "teknoloji": -5},
    "fitness_health"  : {"spor": 12, "saglik": 8, "lifestyle": 2,  "yemek": -6,  "oyun": -6},
    "food_gastronomy" : {"yemek": 12, "lifestyle": 2,  "spor": -6,  "oyun": -8,   "teknoloji": -6},
    "technology"      : {"teknoloji": 12, "oyun": 4,  "spor": -6,  "yemek": -8,  "moda": -4},
    "gaming"          : {"oyun": 12, "eglence": 6, "teknoloji": 4, "spor": -4,   "yemek": -8},
    "travel"          : {"seyahat": 12, "lifestyle": 4, "spor": -4,  "oyun": -8,   "yemek": -4},
    "finance_business": {"finans": 18, "egitim": 8, "teknoloji": 4, "lifestyle": 2, "spor": -6, "yemek": -8, "oyun": -8},
    "entertainment"   : {"eglence": 12, "lifestyle": 3, "spor": -4,  "yemek": -6,  "teknoloji": -4},
    "sports"          : {"spor": 14, "saglik": 4,  "lifestyle": -4, "yemek": -8,  "oyun": -6},
}

# ── Kampanya bazlı kategori izin listesi ────────────────────────────────────
# Her kampanya için hangi Türkçe kategoriler kabul edilir?
# "saglik" spor kampanyasında geçerli, "moda" geçersiz gibi.
# Boş liste = filtre yok (tüm kategoriler kabul).
CAMPAIGN_CATEGORY_ALLOWLIST: dict[str, list[str]] = {
    "sports"          : ["spor", "saglik"],
    "fitness_health"  : ["saglik", "spor"],
    "beauty_fashion"  : ["moda", "lifestyle", "eglence"],
    "lifestyle"       : ["lifestyle", "eglence", "saglik"],
    "food_gastronomy" : ["yemek", "lifestyle"],
    "technology"      : ["teknoloji", "oyun", "egitim"],
    "gaming"          : ["oyun", "teknoloji", "eglence"],
    "travel"          : ["seyahat", "lifestyle", "eglence"],
    "finance_business": ["finans", "teknoloji", "egitim", "lifestyle"],
    "entertainment"   : ["eglence", "lifestyle", "moda", "oyun"],
}

# Kampanya bazli ana nis dogrulamasi.
# category alani bazi profillerde genis etiket gibi davranabiliyor; bu ikinci
# kapi, main_category/brand_fit_tags sinyali kampanyayla celisiyorsa profili
# ilk siralardan uzak tutar.
CAMPAIGN_MAIN_CATEGORY_ALLOWLIST: dict[str, list[str]] = {
    "beauty_fashion"  : ["beauty_fashion", "lifestyle"],
    "lifestyle"       : ["lifestyle"],
    "fitness_health"  : ["fitness_health"],
    "food_gastronomy" : ["food_gastronomy"],
    "technology"      : ["technology"],
    "gaming"          : ["gaming"],
    "travel"          : ["travel"],
    "finance_business": ["finance_business"],
    "entertainment"   : ["entertainment"],
    "sports"          : ["sports", "fitness_health"],
}

CAMPAIGN_POSITIVE_BRAND_FIT: dict[str, list[str]] = {
    "beauty_fashion"  : ["fashion_brand_fit", "luxury_brand_fit"],
    "lifestyle"       : ["lifestyle_brand_fit", "wellness_brand_fit"],
    "fitness_health"  : ["sports_brand_fit", "wellness_brand_fit"],
    "food_gastronomy" : ["food_brand_fit"],
    "technology"      : ["tech_brand_fit"],
    "gaming"          : ["gaming_brand_fit", "tech_brand_fit"],
    "travel"          : ["travel_brand_fit"],
    "finance_business": ["fintech_brand_fit", "tech_brand_fit"],
    "entertainment"   : ["lifestyle_brand_fit"],
    "sports"          : ["sports_brand_fit"],
}

CAMPAIGN_CONFLICT_BRAND_FIT: dict[str, list[str]] = {
    "beauty_fashion"  : ["sports_brand_fit", "gaming_brand_fit", "food_brand_fit", "fintech_brand_fit", "tech_brand_fit", "travel_brand_fit"],
    "sports"          : ["fashion_brand_fit", "food_brand_fit", "gaming_brand_fit"],
    "fitness_health"  : ["fashion_brand_fit", "food_brand_fit", "gaming_brand_fit"],
    "food_gastronomy" : ["sports_brand_fit", "gaming_brand_fit", "tech_brand_fit"],
    "technology"      : ["fashion_brand_fit", "food_brand_fit", "sports_brand_fit"],
    "gaming"          : ["fashion_brand_fit", "food_brand_fit", "sports_brand_fit"],
}

# ── İçerik uzmanlık bonusu ──────────────────────────────────────────────────
# Marka metni belirli bir alt-kategori içerdiğinde, o alanda gerçek içerik
# üreten fenomenleri (template-tag'li genericlerin önüne) çıkarır.
# TEMPLATE_TAG: moda kategorisinde çoğu fenomende ortak olan genel etiket
_MODA_TEMPLATE = "moda fashion style kombin guzellik makyaj trend kiyafet aksesuar skincare beauty parfum"

SPECIALTY_TRIGGERS: dict[str, list[str]] = {
    "makeup": ["makyaj","kozmetik","fondoten","rimel","maskara","lipstick",
               "eyeliner","ruj","allık","makyajvideo","makyajsanatci",
               "kalicimakyaj","microblading","professionalmakeup","makeuptutor"],
    "skincare": ["ciltbakim","cilt bakim","serum","nemlendirici","kbeauty",
                 "k-beauty","retinol","spf","gunes kremi","cilt"],
    "hair": ["sacbakim","saç","sac boyama","keratin","biotin","saccekimi"],
}
# Marka metninde bu keyword'ler varsa o gruba özgü bonus aktif olur
SPECIALTY_BRAND_TRIGGERS: dict[str, list[str]] = {
    "makeup": ["makyaj","kozmetik","fondoten","rimel","maskara","lipstick",
               "ruj","allık","eyeliner","highlighter","kontur","bronz"],
    "skincare": ["cilt","serum","nemlendirici","spf","retinol","krem","losyon","tonik"],
    "hair": ["sac","saç","keratin","biotin","şampuan","sampuan","sac yagi"],
}

def _specialty_bonus(brand_text: str, clean_tags: str) -> float:
    """
    Marka metni belirli bir uzmanlık alanına işaret ediyorsa
    ve fenomenin unique tag prefixinde de o alan varsa +12 puan.
    Template-tag'li genericler bu bonusu almaz.
    """
    brand_lower = brand_text.lower()
    # Unique prefix: template'den önceki kısım (gerçek içerik)
    unique = str(clean_tags).replace(_MODA_TEMPLATE, "").strip().lower()

    bonus = 0.0
    for specialty, brand_kws in SPECIALTY_BRAND_TRIGGERS.items():
        if not any(kw in brand_lower for kw in brand_kws):
            continue
        tag_kws = SPECIALTY_TRIGGERS[specialty]
        if any(kw in unique for kw in tag_kws):
            bonus += 12.0  # gerçek uzman fenomeni
            break
    return bonus

_BRAND_FIT_KEYWORDS: dict[str, list[str]] = {
    "luxury_brand_fit"   : ["luxury", "premium", "exclusive", "high end", "lux", "prestige"],
    "fashion_brand_fit"  : ["fashion", "style", "outfit", "clothing", "moda", "trend", "kombin"],
    "tech_brand_fit"     : ["tech", "technology", "digital", "software", "gadget", "ai", "coding", "teknoloji"],
    "gaming_brand_fit"   : ["gaming", "game", "esport", "streamer", "twitch", "oyun", "e-spor"],
    "sports_brand_fit"   : ["sports", "fitness", "athlete", "gym", "workout", "spor", "atletizm"],
    "wellness_brand_fit" : ["wellness", "health", "saglik", "yoga", "pilates", "mental", "wellbeing"],
    "food_brand_fit"     : ["food", "gastronomy", "recipe", "restaurant", "yemek", "cooking", "mutfak"],
    "fintech_brand_fit"  : ["finance", "fintech", "investment", "borsa", "kripto", "yatirim", "bütçe", "finans", "girisim"],
    "travel_brand_fit"   : ["travel", "tourism", "destination", "adventure", "seyahat", "tur"],
    "lifestyle_brand_fit": ["yasam", "hayat", "motivasyon", "kisisel gelisim", "oz gelisim", "mindset",
                            "coaching", "hedef", "donusum", "felsefe", "minimalizm", "rutin", "ilham"],
}


def _brand_fit_bonus(brand_text: str, brand_fit_tags: str) -> float:
    """
    brand_fit_tags ile marka metni arasinda keyword eslesimi.
    Her eslesme icin +2 puan, maks +10.
    """
    if not brand_fit_tags:
        return 0.0
    brand_lower = brand_text.lower()
    tags_lower  = str(brand_fit_tags).lower()
    bonus = 0.0
    for tag_group, keywords in _BRAND_FIT_KEYWORDS.items():
        if tag_group in tags_lower:
            if any(kw in brand_lower for kw in keywords):
                bonus += 2.0
    return min(bonus, 10.0)


# ════════════════════════════════════════════════════════════════════════════
# ANA ONERI FONKSIYONU
# ════════════════════════════════════════════════════════════════════════════

def get_top_n(brand_text: str, top_n: int = 5) -> dict:
    df = influencer_summary.copy()

    # 1) Marka embedding + SFS
    # Influencer embedding'leri request sirasinda yeniden hesaplanmaz; uygulama
    # acilisinda/Mongo checkpoint'te hazirlanan matris kullanilir.
    brand_embedding = _sbert_encode([brand_text])[0]
    brand_norm = norm(brand_embedding) + 1e-10
    df["sfs"] = (
        (_INFLUENCER_EMBEDDINGS @ brand_embedding)
        / (_INFLUENCER_EMBEDDING_NORMS * brand_norm)
        * 100.0
    ).clip(0, 100).round(2)

    # 2) Kampanya agirliklari + CFS (hibrit: SBERT + keyword bonus)
    brand_weights   = compute_brand_campaign_weights(brand_embedding, brand_text)
    sim_matrix = df[SIM_COLS].fillna(0).to_numpy(dtype=float)
    weight_vec = np.array([brand_weights.get(name, 0.0) for name in CAMPAIGN_NAMES], dtype=float)
    df["cfs"] = (sim_matrix @ weight_vec * 100.0).clip(0, 100).round(2)

    # 3) BAS (geriye donuk uyumluluk)
    df["bas"] = (
        df["sfs"].astype(float) * 0.35
        + df["NFS"].astype(float) * 0.30
        + df["positive_ratio"].astype(float) * 0.25
        + (100.0 - df["fake_followers_risk"].astype(float)) * 0.10
    ).clip(0, 100).round(2)

    # 4) Final Score (CFS entegre, ana siralama kriteri)
    df["final_score"] = (
        df["sfs"].astype(float) * 0.45
        + df["NFS"].astype(float) * 0.15
        + df["cfs"].astype(float) * 0.20
        + df["positive_ratio"].astype(float) * 0.10
        + (100.0 - df["fake_followers_risk"].astype(float)) * 0.10
    )
    low_sfs_penalty = (35.0 - df["sfs"].astype(float)).clip(lower=0) * 0.4
    df["final_score"] = (df["final_score"] - low_sfs_penalty).clip(0, 100).round(2)

    # 4b) brand_fit bonus (+maks 10 puan)
    df["brand_fit_bonus"] = df["brand_fit_tags"].apply(
        lambda tags: _brand_fit_bonus(brand_text, str(tags))
    )
    df["final_score"] = (df["final_score"] + df["brand_fit_bonus"]).clip(upper=100.0).round(2)

    # 4d) İçerik uzmanlık bonusu: makyaj/cilt/saç gibi alt-kategoride
    #     gerçek içerik üreten fenomenleri template-tag'li genericlerin önüne çıkar
    df["specialty_bonus"] = df["clean_tags_all"].apply(
        lambda tags: _specialty_bonus(brand_text, str(tags))
    )
    df["final_score"] = (df["final_score"] + df["specialty_bonus"]).clip(upper=100.0).round(2)

    # 4e) KFS (Keyword Frequency Score) — TF-IDF tabanlı kelime sıklığı bonusu
    # Fenomenin hesabında marka metnindeki kelimeler ne sıklıkla geçiyorsa o kadar yüksek bonus.
    # Örn: marka "voleybol" yazarsa → hesabında 50x voleybol geçen fenomen maksimum bonus alır.
    # Normalize: en iyi eşleşen fenomene 1.0, diğerleri orantılı → max +10 puan.
    brand_tfidf  = _tfidf_vectorizer.transform([brand_text])
    kfs_raw      = sklearn_cosine(brand_tfidf, _tfidf_matrix).flatten()
    kfs_max      = kfs_raw.max() if kfs_raw.max() > 1e-9 else 1.0
    df["kfs"]    = (kfs_raw / kfs_max * 100).clip(0, 100).round(2)
    df["kfs_bonus"] = (kfs_raw / kfs_max * 10.0)  # max +10 puan
    df["final_score"] = (df["final_score"] + df["kfs_bonus"]).clip(upper=100.0).round(2)

    # 5) En yakin kampanya
    closest_camp = _top_campaign(brand_weights)
    allowed_cats = CAMPAIGN_CATEGORY_ALLOWLIST.get(closest_camp, [])
    if allowed_cats:
        df["category_match"] = df["category"].isin(allowed_cats)
    else:
        df["category_match"] = True

    main_allowed = CAMPAIGN_MAIN_CATEGORY_ALLOWLIST.get(closest_camp, [])
    positive_fit_tags = CAMPAIGN_POSITIVE_BRAND_FIT.get(closest_camp, [])
    conflict_fit_tags = CAMPAIGN_CONFLICT_BRAND_FIT.get(closest_camp, [])

    main_series = df["main_category"].fillna("").astype(str)
    fit_series = df["brand_fit_tags"].fillna("").astype(str)

    if main_allowed:
        df["main_category_match"] = main_series.isin(main_allowed)
    else:
        df["main_category_match"] = True

    if positive_fit_tags:
        df["brand_fit_match"] = fit_series.apply(
            lambda tags: any(tag in tags for tag in positive_fit_tags)
        )
    else:
        df["brand_fit_match"] = True

    if conflict_fit_tags:
        df["brand_fit_conflict"] = fit_series.apply(
            lambda tags: any(tag in tags for tag in conflict_fit_tags)
        )
    else:
        df["brand_fit_conflict"] = False

    semantic_floor = df["sfs"].astype(float) >= 30.0
    strong_semantic_campaign = (
        (df["sfs"].astype(float) >= 50.0)
        & (df["cfs"].astype(float) >= 45.0)
    )
    specialty_supported = (
        (df["specialty_bonus"].astype(float) > 0)
        & semantic_floor
        & (df["main_category_match"] | df["brand_fit_match"])
    )
    df["niche_match"] = (
        ((df["main_category_match"] | df["brand_fit_match"]) & semantic_floor)
        | strong_semantic_campaign
        | specialty_supported
    ) & ~df["brand_fit_conflict"]

    # Ilk siralar icin temel alaka kapisi. Bonuslar alakasiz adayi yukari tasimasin.
    df["semantic_match"] = df["sfs"].astype(float) >= 35.0
    df["relevance_ok"] = df["category_match"] & df["semantic_match"] & df["niche_match"]

    # 4c) Kampanya-kategori uyum bonusu
    # Dogru kategorideki fenomenleri one cikarir (orn: guzellikte moda > lifestyle)
    cat_bonus_map = CAMPAIGN_CATEGORY_BONUS.get(closest_camp, {})
    if cat_bonus_map:
        df["cat_bonus"] = df["category"].map(cat_bonus_map).fillna(0.0)
        df["final_score"] = (df["final_score"] + df["cat_bonus"]).clip(upper=100.0).round(2)

    # Ana nis/brand-fit celiskisi skorla da cezalandirilir. Boylece
    # "category=moda" olsa bile sports_brand_fit profili moda kampanyasinda
    # yukari tirmanamaz.
    df["niche_penalty"] = np.where(~df["niche_match"], 22.0, 0.0)
    df["final_score"] = (df["final_score"] - df["niche_penalty"]).clip(0, 100).round(2)

    # 5a) Tier katsayısı — mega fenomenlere erişim ölçeği bonusu
    # Büyük hesaplar markaya daha geniş kitleye erişim sağlar;
    # bu fark, semantik benzerliğin dışında ayrıca ölçülür.
    df["tier_bonus"] = np.where(
        df["relevance_ok"],
        df["account_type"].map(tier_bonus_for_account_type).fillna(0.0),
        0.0,
    )
    df["final_score"] = (df["final_score"] + df["tier_bonus"]).clip(upper=100.0).round(2)

    # 5b) Kategori filtresi — kampanya ile uyumsuz kategorileri listeden çıkar.
    # Eğer kampanya için izin listesi tanımlıysa sadece o kategoriler geçer.
    # İzin listesi boşsa filtre uygulanmaz (geriye dönük uyumluluk).
    allowed_cats = CAMPAIGN_CATEGORY_ALLOWLIST.get(closest_camp, [])
    if allowed_cats:
        df_filtered = df[df["category"].isin(allowed_cats)]
        # Filtre sonrası yeterli influencer yoksa izin listesini esnet
        if len(df_filtered) < top_n:
            df_filtered = df  # fallback: filtresiz devam
    else:
        df_filtered = df

    # Eski fallback filtresiz kalabiliyordu; ilk siralar icin alaka kapisini
    # burada tekrar uygula ve yalnizca kontrollu sekilde esnet.
    df_filtered = df[df["relevance_ok"]].copy()
    if len(df_filtered) < top_n:
        relaxed = df[df["niche_match"] & df["category_match"]].copy()
        df_filtered = (
            pd.concat([df_filtered, relaxed], ignore_index=True)
            .drop_duplicates("influencer_name")
        )
    if len(df_filtered) < top_n:
        df_filtered = df[df["semantic_match"] & df["niche_match"]].copy()
    if len(df_filtered) < top_n:
        # Eksik sayiyi doldurmak icin tum veri setine donmek alakasiz
        # profilleri tekrar yukari tasir. Bu durumda daha az ama tutarli
        # sonuc dondurmek, hatali oneriyi doldurmaktan daha dogru.
        df_filtered = df_filtered.copy()

    instagram_pool = df_filtered[df_filtered["data_source"] == "instagram"].copy()
    min_instagram_required = min(5, top_n)
    if len(instagram_pool) >= min_instagram_required:
        df_filtered = instagram_pool
    elif len(instagram_pool) > 0:
        synthetic_pool = df_filtered[df_filtered["data_source"] != "instagram"].copy()
        df_filtered = pd.concat([instagram_pool, synthetic_pool], ignore_index=True)
        df_filtered["source_priority"] = np.where(df_filtered["data_source"] == "instagram", 1, 0)
    else:
        df_filtered["source_priority"] = 0

    if "source_priority" not in df_filtered.columns:
        df_filtered["source_priority"] = np.where(df_filtered["data_source"] == "instagram", 1, 0)

    df_filtered["ml_label"] = df_filtered.apply(lambda r: predict_ml_label(r, closest_camp), axis=1)
    df_filtered["raw_final_score"] = df_filtered["final_score"]
    df_filtered["ai_adjustment"] = df_filtered["ml_label"].apply(ml_label_adjustment)
    df_filtered["final_score"] = (
        df_filtered["final_score"].astype(float) + df_filtered["ai_adjustment"].astype(float)
    ).clip(0, 100).round(2)
    df_filtered["source_bonus"] = np.where(df_filtered["data_source"] == "instagram", 3.0, 0.0)
    df_filtered["ranking_score"] = (
        df_filtered["final_score"].astype(float) + df_filtered["source_bonus"]
    ).clip(0, 100).round(2)

    top_df = (
        df_filtered
        .sort_values(["ranking_score", "final_score"], ascending=[False, False])
        .head(top_n)
        .copy()
    )

    # 6) Kampanya agirliklari — en yuksek 3 tane
    top3_camps = sorted(brand_weights.items(), key=lambda x: x[1], reverse=True)[:3]

    # 7) Sonuc alanlarini belirle
    base_cols = [
        "influencer_name", "category", "account_type",
        "NFS", "sfs", "cfs", "bas", "raw_final_score", "ai_adjustment", "final_score",
        "positive_ratio", "fake_followers_risk",
        "risk_category", "ml_label",
    ]
    optional_cols  = ["estimated_gender", "similarity_cluster", "country", "data_source",
                      "follower_count", "avg_engagement_rate"]
    tag_cols       = ["main_category", "audience_type", "engagement_type", "content_tone", "brand_fit_tags"]
    comment_cols   = ["positive_comment_ratio", "negative_comment_ratio",
                      "neutral_comment_ratio", "avg_comment_sentiment", "comment_count"]
    result_cols   = (
        base_cols
        + [c for c in optional_cols  if c in top_df.columns]
        + [c for c in tag_cols       if c in top_df.columns]
        + [c for c in comment_cols   if c in top_df.columns]
    )

    records = (
        top_df[result_cols]
        .rename(columns={"bas": "campaign_bas", "final_score": "final_score"})
        .to_dict(orient="records")
    )

    return {
        "recommendations"     : records,
        "brand_campaign_weights": {k: round(v, 4) for k, v in brand_weights.items()},
        "closest_campaign"    : closest_camp,
        "top3_campaigns"      : [{"campaign": k, "weight": round(v, 4)} for k, v in top3_camps],
    }


# ════════════════════════════════════════════════════════════════════════════
# FLASK ENDPOINT'LERI
# ════════════════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api", methods=["GET"])
def api_info():
    return jsonify({
        "message"  : "Fenomen-Marka Eslestirme API v3 — CFS Entegre",
        "endpoints": {
            "POST /recommend"                  : "Marka metni gonder, Top-N fenomen al (CFS entegre)",
            "GET  /influencers"                : "Tum fenomenleri listele",
            "GET  /influencers?category=X"     : "Kategoriye gore filtrele",
            "GET  /influencers/<name>/similar" : "Benzer fenomenleri bul (K-Means cluster)",
            "GET  /stats"                      : "Istatistikleri goster",
            "GET  /campaigns"                  : "Kampanya embedding agirliklarini goster",
        },
        "formulas": {
            "NFS"         : "Ridge(engagement_rate, FGR, posts_per_month) — eng_auth etiketli ML skoru",
            "SFS"         : "cosine_sim(marka_embedding, fenomen_embedding) * 100",
            "CFS"         : "SUM(brand_weight[k] * sim_kampanya[k]) * 100",
            "BAS"         : "SFS*0.35 + NFS*0.30 + PositiveRatio*0.25 + (100-FakeRisk)*0.10",
            "FINAL_SCORE" : "SFS*0.35 + NFS*0.25 + CFS*0.20 + PositiveRatio*0.10 + (100-FakeRisk)*0.10",
        },
    })


@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json(silent=True)

    if not data or "brand_text" not in data:
        return jsonify({"error": "brand_text alani gerekli"}), 400

    brand_text = str(data["brand_text"]).strip()
    if len(brand_text) < 10:
        return jsonify({"error": "brand_text en az 10 karakter olmali"}), 400

    top_n = max(1, min(int(data.get("top_n", 5)), 50))

    try:
        result = get_top_n(brand_text, top_n=top_n)
        return jsonify({
            "success"              : True,
            "brand_text"           : brand_text,
            "count"                : len(result["recommendations"]),
            "closest_campaign"     : result["closest_campaign"],
            "top3_campaigns"       : result["top3_campaigns"],
            "brand_campaign_weights": result["brand_campaign_weights"],
            "formulas": {
                "BAS"         : "SFS*0.35 + NFS*0.30 + PositiveRatio*0.25 + (100-FakeRisk)*0.10",
                "FINAL_SCORE" : "SFS*0.35 + NFS*0.25 + CFS*0.20 + PositiveRatio*0.10 + (100-FakeRisk)*0.10",
            },
            "recommendations"      : result["recommendations"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/debug/campaign", methods=["POST"])
def debug_campaign():
    """
    Kampanya sınıflandırma kararının matematiksel adımlarını döndürür.

    Body: { "brand_text": "..." }

    Döndürür:
      sbert_cosine      — Ham SBERT cosine skorları (10 kampanya)
      keyword_matches   — Her kampanya için eşleşen keyword'ler ve bonus miktarı
      raw_score         — SBERT cosine + keyword bonus (softmax öncesi)
      softmax_weights   — Normalize edilmiş olasılıklar (%)
      winner            — Kazanan kampanya ve kazanma farkı
    """
    data = request.get_json(silent=True)
    if not data or "brand_text" not in data:
        return jsonify({"error": "brand_text alani gerekli"}), 400

    brand_text = str(data["brand_text"]).strip()
    if len(brand_text) < 3:
        return jsonify({"error": "brand_text cok kisa"}), 400

    brand_lower     = brand_text.lower()
    brand_embedding = _sbert_encode([brand_text])[0]

    # ── Adım 1: SBERT ham cosine skorları ─────────────────────────────────────
    sbert_scores = {
        name: round(float(cosine_sim(brand_embedding, CAMPAIGN_EMBEDDINGS[name])), 6)
        for name in CAMPAIGN_NAMES
    }

    # ── Adım 2: Keyword eşleşmeleri ve bonus hesabı ────────────────────────────
    keyword_detail = {}
    raw_scores     = np.array([sbert_scores[n] for n in CAMPAIGN_NAMES], dtype=float)

    for i, name in enumerate(CAMPAIGN_NAMES):
        kws      = CAMPAIGN_KEYWORDS.get(name, [])
        matched  = [kw for kw in kws if kw in brand_lower]
        bonus    = round(min(len(matched) * 0.05, 0.25), 4)
        raw_scores[i] += bonus
        keyword_detail[name] = {
            "keywords_checked" : len(kws),
            "matched"          : matched,
            "match_count"      : len(matched),
            "bonus_added"      : bonus,
        }

    # ── Adım 3: Softmax (sıcaklık=7) ─────────────────────────────────────────
    weights_arr = _softmax(raw_scores * 7)
    softmax_weights = {
        name: round(float(w) * 100, 4)   # yüzde olarak
        for name, w in zip(CAMPAIGN_NAMES, weights_arr)
    }

    # ── Adım 4: Kazanan ve rakamsal fark ──────────────────────────────────────
    sorted_weights = sorted(softmax_weights.items(), key=lambda x: x[1], reverse=True)
    winner_name, winner_pct = sorted_weights[0]
    runner_name, runner_pct = sorted_weights[1]

    # ── Tam tablo: her kampanya için tüm değerler ──────────────────────────────
    full_table = []
    for name in CAMPAIGN_NAMES:
        sbert_val   = sbert_scores[name]
        kw          = keyword_detail[name]
        raw_val     = round(float(sbert_val + kw["bonus_added"]), 6)
        softmax_val = softmax_weights[name]
        full_table.append({
            "campaign"       : name,
            "sbert_cosine"   : sbert_val,
            "kw_matched"     : kw["matched"],
            "kw_count"       : kw["match_count"],
            "kw_bonus"       : kw["bonus_added"],
            "raw_score"      : raw_val,
            "softmax_pct"    : softmax_val,
        })
    full_table.sort(key=lambda x: x["softmax_pct"], reverse=True)

    return jsonify({
        "brand_text"      : brand_text,
        "steps": {
            "step1_sbert_cosine" : dict(sorted(sbert_scores.items(),  key=lambda x: x[1], reverse=True)),
            "step2_kw_bonuses"   : {n: {"matched": keyword_detail[n]["matched"],
                                        "bonus":   keyword_detail[n]["bonus_added"]}
                                    for n in CAMPAIGN_NAMES},
            "step3_raw_scores"   : dict(zip(CAMPAIGN_NAMES, [round(float(v),6) for v in raw_scores])),
            "step4_softmax_pct"  : dict(sorted(softmax_weights.items(), key=lambda x: x[1], reverse=True)),
        },
        "winner": {
            "campaign"   : winner_name,
            "softmax_pct": winner_pct,
            "margin_over_2nd": round(winner_pct - runner_pct, 4),
            "runner_up"  : runner_name,
        },
        "full_table" : full_table,
    })


@app.route("/influencers", methods=["GET"])
def list_influencers():
    """
    Fenomen listesi — MongoDB varsa oradan, yoksa pkl'den.
    Query parametreleri:
      category     : kategori filtresi
      min_nfs      : minimum NFS skoru
      max_risk     : maksimum sahte takipci riski (0-100)
      sort_by      : NFS | BAS | positive_ratio (varsayilan: NFS)
      limit        : max kac fenomen (varsayilan: 50)
    """
    category  = request.args.get("category",  None)
    min_nfs   = float(request.args.get("min_nfs",   0))
    max_risk  = float(request.args.get("max_risk",  100))
    sort_by   = request.args.get("sort_by",   "NFS")
    limit     = min(int(request.args.get("limit", 50)), 200)

    # ── MongoDB yolu ──────────────────────────────────────────
    if _mongo_col is not None:
        query = {
            "NFS"               : {"$gte": min_nfs},
            "fake_followers_risk": {"$lte": max_risk},
        }
        if category:
            query["category"] = {"$regex": category, "$options": "i"}

        sort_field = sort_by if sort_by in ("NFS", "positive_ratio") else "NFS"
        cursor = _mongo_col.find(
            query,
            {"_id": 0, "influencer_name": 1, "category": 1,
             "account_type": 1, "NFS": 1, "positive_ratio": 1,
             "risk_category": 1, "fake_followers_risk": 1,
             "data_source": 1},
        ).sort(sort_field, -1).limit(limit)

        records = list(cursor)
        return jsonify({"success": True, "source": "mongodb",
                        "count": len(records), "influencers": records})

    # ── pkl fallback ──────────────────────────────────────────
    df = influencer_summary.copy()
    if category:
        df = df[df["category"].str.lower() == category.lower()]
    df = df[df["NFS"] >= min_nfs]
    df = df[df["fake_followers_risk"] <= max_risk]

    df["BAS"] = df.apply(
        lambda r: calculate_bas(0, r["NFS"], r["positive_ratio"], r["fake_followers_risk"]),
        axis=1,
    )
    sort_col = sort_by if sort_by in ("NFS", "BAS", "positive_ratio") else "NFS"
    cols     = ["influencer_name", "category", "account_type",
                "NFS", "BAS", "positive_ratio", "risk_category", "fake_followers_risk"]
    result   = df[cols].sort_values(sort_col, ascending=False).head(limit)

    return jsonify({
        "success"    : True,
        "source"     : "pkl",
        "count"      : len(result),
        "influencers": result.to_dict(orient="records"),
    })


@app.route("/influencers/<string:name>/similar", methods=["GET"])
def similar_influencers(name: str):
    """
    Benzer fenomenleri doner.
    CF matrisi varsa item-based collaborative filtering kullanir;
    yoksa K-Means cluster'ina fallback yapar.
    """
    df  = influencer_summary
    row = df[df["influencer_name"].str.lower() == name.lower()]

    if row.empty:
        return jsonify({"error": f"'{name}' bulunamadi"}), 404

    actual_name = row.iloc[0]["influencer_name"]

    # ── Item-based CF: benzerlik matrisi ──────────────────────────
    if _cf_matrix is not None and actual_name in _cf_matrix.index:
        sim_series = _cf_matrix[actual_name].drop(labels=[actual_name])
        top_names  = sim_series.sort_values(ascending=False).head(10).index.tolist()
        top_scores = sim_series.sort_values(ascending=False).head(10).values.tolist()

        similar_df = df[df["influencer_name"].isin(top_names)].copy()
        similar_df["cf_similarity"] = similar_df["influencer_name"].map(
            dict(zip(top_names, top_scores))
        )
        cols = ["influencer_name", "category", "account_type", "NFS",
                "positive_ratio", "risk_category", "cf_similarity"]
        result = similar_df[[c for c in cols if c in similar_df.columns]] \
                            .sort_values("cf_similarity", ascending=False)

        return jsonify({
            "success"      : True,
            "influencer"   : actual_name,
            "method"       : "item_based_cf",
            "similar_count": len(result),
            "similar"      : result.to_dict(orient="records"),
        })

    # ── Fallback: K-Means cluster ─────────────────────────────────
    cluster_id = int(row.iloc[0]["similarity_cluster"])
    similar    = df[
        (df["similarity_cluster"] == cluster_id) &
        (df["influencer_name"].str.lower() != name.lower())
    ]

    cols = ["influencer_name", "category", "account_type", "NFS",
            "positive_ratio", "risk_category", "similarity_cluster"]
    result = similar[[c for c in cols if c in similar.columns]] \
                     .sort_values("NFS", ascending=False).head(10)

    return jsonify({
        "success"      : True,
        "influencer"   : actual_name,
        "method"       : "kmeans_cluster",
        "cluster_id"   : cluster_id,
        "similar_count": len(result),
        "similar"      : result.to_dict(orient="records"),
    })


@app.route("/debug/tags", methods=["GET"])
def debug_tags():
    """Her influencer'ın clean_tags_all içinde finans keyword'lerini tara."""
    fin_kws = ["borsa","hisse","kripto","yatirim","finans","ekonomi","muhasebe",
               "girisim","para","faiz","dolar","euro","piyasa","fon","portfoy"]
    results = []
    for _, row in influencer_summary.iterrows():
        tags = str(row.get("clean_tags_all","")).lower()
        hits = [k for k in fin_kws if k in tags]
        if hits:
            results.append({
                "name": row["influencer_name"],
                "category": row["category"],
                "account_type": row.get("account_type",""),
                "hits": hits,
                "tags_snippet": tags[:200],
            })
    results.sort(key=lambda x: len(x["hits"]), reverse=True)
    return jsonify({"count": len(results), "matches": results})


@app.route("/stats", methods=["GET"])
def stats():
    df = influencer_summary

    avg_bas = round(
        calculate_bas(
            sfs           = 50.0,
            nfs           = float(df["NFS"].mean()),
            positive_ratio= float(df["positive_ratio"].mean()),
            fake_risk     = float(df["fake_followers_risk"].mean()),
        ), 2,
    )

    # Kampanya bazinda ortalama sim skorlari
    camp_avg = {}
    for c in SIM_COLS:
        if c in df.columns:
            camp_avg[c.replace("sim_", "")] = round(float(df[c].mean()), 4)

    return jsonify({
        "success"           : True,
        "total_influencers" : int(len(df)),
        "categories"        : df["category"].value_counts().to_dict(),
        "account_types"     : df["account_type"].value_counts().to_dict()
                              if "account_type" in df.columns else {},
        "data_sources"      : df["data_source"].value_counts().to_dict()
                              if "data_source" in df.columns else {},
        "avg_NFS"           : round(float(df["NFS"].mean()), 2),
        "avg_BAS"           : avg_bas,
        "avg_engagement"    : round(float(df["engagement_rate"].mean()), 2)
                              if "engagement_rate" in df.columns else None,
        "risk_distribution" : df["risk_category"].value_counts().to_dict()
                              if "risk_category" in df.columns else {},
        "cluster_distribution": df["similarity_cluster"].value_counts().sort_index().to_dict()
                              if "similarity_cluster" in df.columns else {},
        "campaign_avg_scores": camp_avg,
    })


@app.route("/campaigns", methods=["GET"])
def campaigns():
    """6 kampanya icin ortalama fenomen uyum skorlarini doner."""
    df = influencer_summary
    result = []
    for name in CAMPAIGN_NAMES:
        col = f"sim_{name}"
        top_inf = (
            df[["influencer_name", "category", col]]
            .sort_values(col, ascending=False)
            .head(5)
            .rename(columns={col: "similarity"})
            .to_dict(orient="records")
        ) if col in df.columns else []

        result.append({
            "campaign"         : name,
            "description"      : CAMPAIGN_TEXTS[name],
            "avg_similarity"   : round(float(df[col].mean()), 4) if col in df.columns else 0,
            "top_influencers"  : top_inf,
        })

    return jsonify({"success": True, "campaigns": result})


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _default_port = 5001 if sys.platform == "darwin" else 5000
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", _default_port)))
