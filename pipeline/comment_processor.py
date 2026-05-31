# =============================================================================
# pipeline/comment_processor.py — Yorum Temizleme ve Analiz Modülü
# =============================================================================
# GÖREV   : influencer_comments.csv dosyasını okuyarak yorumları temizler,
#           örnekler ve her fenomen için duygu analizine hazır hale getirir.
#
# KULLANIM: analiz_pipeline.py tarafından import edilerek kullanılır;
#           bağımsız olarak da çalıştırılabilir.
#
# GİRDİ  : data/influencer_comments.csv
#   Beklenen sütunlar: influencer_name, comment_text, [comment_likes], [post_id]
#   Farklı sütun adları için COLUMN_MAP değişkenini düzenleyin.
#
# ÇIKTI  : Temizlenmiş ve gruplandırılmış yorum DataFrame'i
# =============================================================================

import re
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Sütun adı eşlemesi (CSV'nizin başlıklarına göre düzenleyin) ─────────────
COLUMN_MAP = {
    "influencer" : "influencer_name",   # zorunlu
    "text"       : "comment_text",       # zorunlu
    "likes"      : "comment_likes",      # opsiyonel; yoksa 0 atanır
    "post_id"    : "post_id",            # opsiyonel
}

# ── Türkçe stop-words (genişletilebilir) ────────────────────────────────────
TR_STOPWORDS = {
    "bir","bu","ve","de","da","ile","için","mi","mu","mı","mü",
    "ne","ya","ki","çok","daha","ben","sen","o","biz","siz","onlar",
    "ama","fakat","ancak","veya","ya","hem","gibi","kadar","bile",
    "var","yok","olan","olan","bu","şu","her","hiç","en","çok",
    "nasıl","neden","nerede","kim","ne","hangi","http","www",
}

# ── Konfigürasyon ─────────────────────────────────────────────────────────────
MAX_COMMENTS_PER_INFLUENCER = 100   # sentiment için örneklenen max yorum sayısı
MAX_WORDS_FOR_SBERT         = 120   # SBERT inputuna eklenen max kelime sayısı
MIN_COMMENT_CHARS           = 5     # bu kadardan kısa yorumlar atlanır


# ════════════════════════════════════════════════════════════════════════════
# 1. TEMİZLEME
# ════════════════════════════════════════════════════════════════════════════

# Emoji bloğunu kapsayan Unicode aralıkları
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "♀-♂"
    "☀-⭕"
    "‍⏏⏩⌚️〰"
    "]+",
    flags=re.UNICODE,
)
_URL_RE      = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE  = re.compile(r"@\w+")
_HASHTAG_RE  = re.compile(r"#\w+")
_REPEAT_RE   = re.compile(r"(.)\1{3,}")   # aaaaa → a


def clean_comment(text: str) -> str:
    """Tek bir yorum metnini normalize eder."""
    if not isinstance(text, str):
        return ""
    t = text.lower()
    t = _URL_RE.sub(" ", t)
    t = _MENTION_RE.sub(" ", t)
    t = _HASHTAG_RE.sub(" ", t)
    t = _EMOJI_RE.sub(" ", t)
    t = _REPEAT_RE.sub(r"\1", t)            # tekrar karakterleri kıs
    t = re.sub(r"[^a-zçğıöşüa-z0-9\s]", " ", t)
    tokens = [w for w in t.split() if w not in TR_STOPWORDS and len(w) > 1]
    return " ".join(tokens)


# ════════════════════════════════════════════════════════════════════════════
# 2. YÜKLEME VE ÖN İŞLEME
# ════════════════════════════════════════════════════════════════════════════

def load_comments(path: str | Path) -> pd.DataFrame:
    """
    CSV'yi yükler, sütunları normalleştirir ve temiz_yorum sütunu ekler.

    Returns
    -------
    pd.DataFrame  kolonlar: influencer_name, comment_text, comment_likes,
                            clean_comment, post_id (varsa)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Yorum dosyası bulunamadı: {path}")

    df = pd.read_csv(path, low_memory=False)
    logger.info(f"Yüklendi: {len(df)} yorum  |  {df.shape[1]} sütun")

    # Sütun adlarını normalize et
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Zorunlu sütunları bul
    for canonical, default in COLUMN_MAP.items():
        candidates = [c for c in df.columns if default.replace("_", "") in c.replace("_", "")]
        if default not in df.columns and candidates:
            df.rename(columns={candidates[0]: default}, inplace=True)

    if "influencer_name" not in df.columns:
        raise ValueError(
            "influencer_name sütunu bulunamadı. "
            "COLUMN_MAP['influencer'] değerini CSV başlığınıza göre güncelleyin."
        )
    if "comment_text" not in df.columns:
        raise ValueError(
            "comment_text sütunu bulunamadı. "
            "COLUMN_MAP['text'] değerini CSV başlığınıza göre güncelleyin."
        )

    # influencer_name '@' ile başlamalı
    df["influencer_name"] = df["influencer_name"].astype(str).str.strip()
    mask = ~df["influencer_name"].str.startswith("@")
    df.loc[mask, "influencer_name"] = "@" + df.loc[mask, "influencer_name"]

    # comment_likes yoksa 0
    if "comment_likes" not in df.columns:
        df["comment_likes"] = 0
    else:
        df["comment_likes"] = pd.to_numeric(df["comment_likes"], errors="coerce").fillna(0)

    # NaN metinleri at
    df = df.dropna(subset=["comment_text"]).copy()
    df["comment_text"] = df["comment_text"].astype(str)

    # Çok kısa yorumları at
    df = df[df["comment_text"].str.len() >= MIN_COMMENT_CHARS].copy()

    # Temizle
    df["clean_comment"] = df["comment_text"].apply(clean_comment)
    df = df[df["clean_comment"].str.strip() != ""].copy()

    logger.info(f"Temizleme sonrası: {len(df)} geçerli yorum")
    return df


# ════════════════════════════════════════════════════════════════════════════
# 3. ÖRNEKLEME
# ════════════════════════════════════════════════════════════════════════════

def sample_top_comments(
    df: pd.DataFrame,
    n: int = MAX_COMMENTS_PER_INFLUENCER,
) -> pd.DataFrame:
    """
    Her influencer için en etkileşimli N yorumu seçer.
    Strateji: comment_likes azalan → uzun yorum tercih (ikincil kriter).

    Returns
    -------
    pd.DataFrame  (aynı şema, her influencer için max N satır)
    """
    df = df.copy()
    df["_len"] = df["clean_comment"].str.split().str.len()

    sampled = (
        df.sort_values(["influencer_name", "comment_likes", "_len"], ascending=[True, False, False])
        .groupby("influencer_name", group_keys=False)
        .head(n)
        .drop(columns=["_len"])
        .reset_index(drop=True)
    )
    logger.info(
        f"Örnekleme: {len(df)} → {len(sampled)} yorum  "
        f"(influencer başı max {n})"
    )
    return sampled


# ════════════════════════════════════════════════════════════════════════════
# 4. AGREGASYON (influencer başına tek metin)
# ════════════════════════════════════════════════════════════════════════════

def aggregate_comments(df: pd.DataFrame) -> pd.DataFrame:
    """
    Her influencer için temiz yorumları tek bir metinde birleştirir.

    Returns
    -------
    pd.DataFrame  kolonlar: influencer_name, aggregated_comments, comment_count
    """
    agg = (
        df.groupby("influencer_name")["clean_comment"]
        .agg(
            aggregated_comments=lambda x: " ".join(x.dropna()),
            comment_count="count",
        )
        .reset_index()
    )
    return agg


def truncate_for_sbert(text: str, max_words: int = MAX_WORDS_FOR_SBERT) -> str:
    """
    SBERT token limitini aşmamak için yorumları max_words kelimeye kırp.
    SBERT paraphrase-multilingual-MiniLM-L12-v2 max 128 token; ~90-100 kelime güvenli.
    """
    words = str(text).split()
    return " ".join(words[:max_words])


# ════════════════════════════════════════════════════════════════════════════
# 5. DUYGU ANALİZİ
# ════════════════════════════════════════════════════════════════════════════

def analyze_comment_sentiment(
    df_sampled: pd.DataFrame,
    sentiment_pipeline,
    batch_size: int = 32,
) -> pd.DataFrame:
    """
    Örneklenmiş yorumlara Türkçe BERT sentiment uygular.

    Parameters
    ----------
    df_sampled         : sample_top_comments() çıktısı
    sentiment_pipeline : HuggingFace pipeline (savasy/bert-base-turkish-sentiment-cased)
    batch_size         : GPU/CPU belleği için batch boyutu

    Returns
    -------
    pd.DataFrame  kolonlar:
        influencer_name, positive_comment_ratio, negative_comment_ratio,
        neutral_comment_ratio, avg_comment_sentiment, comment_count
    """
    df = df_sampled.copy()

    # Batch sentiment
    texts = df["clean_comment"].tolist()
    labels, scores = [], []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            results = sentiment_pipeline(
                [t[:512] for t in batch],
                truncation=True,
                padding=True,
                batch_size=batch_size,
            )
            for r in results:
                labels.append(r["label"].lower())   # "positive" / "negative"
                scores.append(float(r["score"]))
        except Exception as e:
            logger.warning(f"Sentiment batch hatası (i={i}): {e}")
            labels.extend(["neutral"] * len(batch))
            scores.extend([0.5] * len(batch))

    df["comment_label"] = labels
    df["comment_score"] = scores

    # neutral = düşük güven skoru (iki sınıflı modelde eşik: 0.60)
    CONFIDENCE_THRESHOLD = 0.60
    df.loc[df["comment_score"] < CONFIDENCE_THRESHOLD, "comment_label"] = "neutral"

    # Influencer bazında özet
    def _summarize(g):
        total = len(g)
        pos   = (g["comment_label"] == "positive").sum()
        neg   = (g["comment_label"] == "negative").sum()
        neu   = (g["comment_label"] == "neutral").sum()
        return pd.Series({
            "positive_comment_ratio" : round(pos / total * 100, 2),
            "negative_comment_ratio" : round(neg / total * 100, 2),
            "neutral_comment_ratio"  : round(neu / total * 100, 2),
            "avg_comment_sentiment"  : round(g["comment_score"].mean(), 4),
            "comment_count"          : total,
        })

    summary = (
        df.groupby("influencer_name")
        .apply(_summarize)
        .reset_index()
    )
    logger.info(
        f"Sentiment tamamlandı: {len(summary)} influencer  |  "
        f"ort. pozitif: {summary['positive_comment_ratio'].mean():.1f}%"
    )
    return summary


# ════════════════════════════════════════════════════════════════════════════
# 6. SBERT METNİ OLUŞTURMA (ağırlıklı birleştirme)
# ════════════════════════════════════════════════════════════════════════════

def build_enriched_influencer_text(
    base_text: str,
    aggregated_comments: str,
    comment_weight: float = 0.30,
    max_comment_words: int = MAX_WORDS_FOR_SBERT,
) -> str:
    """
    Mevcut influencer metnini (hashtag + caption + seed) yorum metniyle birleştirir.

    Ağırlık mantığı:
    ─────────────────────────────────────────────────────────────
    SBERT ortalama havuzlama (mean pooling) kullanır.
    Toplam token sayısı üzerinden ağırlık:
      - base_text ~200-300 kelime → ~70% ağırlık
      - comments  max 120 kelime  → ~30% ağırlık
    Bu oran, post içeriğinin anlamsal baskınlığını korur;
    yorumlar kitle sinyalini (audience signal) hafifçe ekler.

    comment_weight parametresi:
      0.0 → yorumları dahil etme
      0.3 → varsayılan (~30% yorum katkısı)
      0.5 → eşit ağırlık (önerilmez; yorum gürültüsü artar)
    ─────────────────────────────────────────────────────────────
    """
    if not aggregated_comments or comment_weight == 0.0:
        return base_text

    # Kelime bazında oran kontrolü
    base_words    = base_text.split()
    comment_words = truncate_for_sbert(aggregated_comments, max_comment_words).split()

    # İstenen ağırlığa göre base'i kıs veya yorumu uzat
    target_comment_len = int(len(base_words) * comment_weight / (1 - comment_weight))
    comment_words = comment_words[:target_comment_len]

    enriched = base_text + " " + " ".join(comment_words)
    return enriched.strip()


# ════════════════════════════════════════════════════════════════════════════
# 7. ANA PIPELINE FONKSİYONU (analiz_pipeline.py tarafından çağrılır)
# ════════════════════════════════════════════════════════════════════════════

def process_comments(
    comments_path: str | Path,
    sentiment_pipeline,
    n_sample: int = MAX_COMMENTS_PER_INFLUENCER,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tek çağrıda tüm işlem zincirini çalıştırır.

    Returns
    -------
    sentiment_df   : influencer_name + sentiment sütunları (ML feature'ları için)
    aggregation_df : influencer_name + aggregated_comments (SBERT için)
    """
    print("  [comments] Yorum dosyası yükleniyor ve temizleniyor...")
    df_raw     = load_comments(comments_path)

    print(f"  [comments] Örnekleme (influencer başı max {n_sample})...")
    df_sampled = sample_top_comments(df_raw, n=n_sample)

    print("  [comments] Duygu analizi çalıştırılıyor (TR-BERT)...")
    sentiment_df = analyze_comment_sentiment(df_sampled, sentiment_pipeline)

    print("  [comments] Metin agregasyonu yapılıyor...")
    aggregation_df = aggregate_comments(df_sampled)

    print(f"  [comments] ✅ Tamamlandı: {len(sentiment_df)} influencer işlendi")
    return sentiment_df, aggregation_df


# ════════════════════════════════════════════════════════════════════════════
# BAĞIMSIZ TEST (python comment_processor.py çalıştırıldığında)
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    path = sys.argv[1] if len(sys.argv) > 1 else "influencer_comments.csv"
    print(f"Test dosyası: {path}")

    try:
        df_raw = load_comments(path)
        print(f"\nYüklenen yorum sayısı : {len(df_raw)}")
        print(f"Benzersiz influencer  : {df_raw['influencer_name'].nunique()}")
        print(f"\nÖrnek temiz yorumlar:")
        print(df_raw[["influencer_name", "clean_comment"]].head(5).to_string(index=False))

        df_sampled = sample_top_comments(df_raw)
        agg = aggregate_comments(df_sampled)
        print(f"\nAgregasyon örneği:")
        print(agg.head(3).to_string(index=False))

    except FileNotFoundError as e:
        print(f"HATA: {e}")
        print("Kullanım: python comment_processor.py influencer_comments.csv")
