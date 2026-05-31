# category_utils.py — Influencer kategori belirleme yardımcı modülü.
#
# Dışarıdan import edilebilen 3 bileşen:
#   clean_commercial_noise(text)                     → ticari gürültü temizleme
#   predict_and_validate_category(name, text, ...)   → SBERT + güven eşiği + override
#   HARD_OVERRIDES                                   → bilinen figürlerin kilitli kategorileri
#
# Kullanım örneği:
#   from pipeline.category_utils import predict_and_validate_category, HARD_OVERRIDES

import re
import numpy as np
from numpy.linalg import norm
from typing import Optional

# ── Kampanya tanımları ────────────────────────────────────────────────────────
CAMPAIGN_TEXTS: dict[str, str] = {
    "beauty_fashion"  : "guzellik moda kisisel stil skincare makyaj parfum kiyafet kombin trend kozmetik",
    "lifestyle"       : "kisisel gelisim yasam tarzi motivasyon mindset hedef aliskanlık uretkenlik ic huzur",
    "fitness_health"  : "spor antrenman kas kilo kondisyon beslenme diyetisyen protein pilates atletizm",
    "food_gastronomy" : "yemek tarif restoran mutfak lezzet gastronomi gurme pisme",
    "technology"      : "teknoloji yazilim yapay zeka kodlama dijital siber guvenlik gadget",
    "gaming"          : "oyun e-spor gaming twitch konsol mobil oyun youtuber",
    "travel"          : "seyahat tatil tur destinasyon otel backpacking gezi macera",
    "finance_business": "borsa hisse kripto yatirim finans girisimcilik ekonomi muhasebe",
    "entertainment"   : "film dizi muzik eglence komedi sinema konser youtuber sarkici",
    "sports"          : "futbol basketbol voleybol mac takim sampiyonluk atletizm sporcu",
    "anne-bebek"      : "bebek anne cocuk hamilelik dogum emzirme annelik parenting yenidogan",
    "egitim"          : "egitim ogrenme universite bilim kitap yks sinav kariyer ogrenci",
}

# Kampanya adı → checkpoint'teki Türkçe kategori adı
CAMP_TO_TURK: dict[str, str] = {
    "beauty_fashion"  : "moda",
    "lifestyle"       : "lifestyle",
    "fitness_health"  : "saglik",
    "food_gastronomy" : "yemek",
    "technology"      : "teknoloji",
    "gaming"          : "oyun",
    "travel"          : "seyahat",
    "finance_business": "finans",
    "entertainment"   : "eglence",
    "sports"          : "spor",
    "anne-bebek"      : "anne-bebek",
    "egitim"          : "egitim",
}

# ── Bilgi Dağarcığı (Knowledge Base) Override ────────────────────────────────
# Türkiye'de nişi kamuoyunca bilinen figürler.
# SBERT metni ne derse desin, bu sözlük önceliklidir.
HARD_OVERRIDES: dict[str, str] = {
    # Spor
    "@ardaguler"            : "spor",   # Real Madrid - halamadrid
    "@ardasaatci"           : "spor",   # Fitness / spor odakli icerik
    "@ardaturan"            : "spor",   # Galatasaray / milli futbolcu
    "@m10_official"         : "spor",   # Mesut Özil
    "@edaerdem14"           : "spor",   # Fenerbahçe basketbol
    "@burcues"              : "spor",   # Futbolcu
    "@caneryldrmm"          : "spor",   # Boksör
    # Oyun / YouTube
    "@tugkangonultas"       : "oyun",   # Elraenn
    "@orkunisitmak"         : "oyun",   # MLBB / gaming
    "@mesutcevik"           : "oyun",   # gaming
    # Eğlence / Medya
    "@jahrein"              : "eglence",
    "@canrtopcu"            : "eglence",
    "@merveozbeyofficial"   : "eglence", # Merve Özbey - şarkıcı
    "@caglasikel"           : "eglence", # TV celebrity
    "@murattatikofficial"   : "eglence",
    # Moda / Güzellik
    "@danlabilic"           : "moda",
    "@duyguozaslan"         : "moda",
    "@gardiropgurusu"       : "moda",
    "@mervenurakyuz"        : "moda",
    "@zeynep.okktay"        : "moda",
    "@zynpzeze"             : "moda",
    "@bagtubaa"             : "moda",
    # Yemek
    "@ardaturkmen"          : "yemek",  # Arda Türkmen - şef
    "@edakarabulut"         : "yemek",
    # Finans / Gayrimenkul yatırım
    "@londongyd"            : "finans",   # London/İstanbul konut yatırımı, borsa, kripto
    # Seyahat
    "@rotani_benimle_belirle": "seyahat",
    # Sağlık
    "@prof.dr.ferhatcekmez" : "saglik",
    # Eğitim
    "@beyzalkoc"            : "egitim",  # Beyza Alkoç - yazar
    # Lifestyle
    "@ferhatbora"           : "lifestyle",
    # Anne-bebek
    "@influencer100"        : "anne-bebek",
    "@influencer2"          : "anne-bebek",
    "@influencer25"         : "anne-bebek",
    "@influencer66"         : "anne-bebek",
    "@influencer71"         : "anne-bebek",
    "@influencer72"         : "anne-bebek",
}

# ── Ticari Gürültü Temizleme ──────────────────────────────────────────────────
# SBERT'in bu kelimeleri "finans/ticaret" kümesine çekmesini engellemek için
# SBERT'e gönderilmeden önce metinden kazınır.
_COMMERCIAL_PATTERNS: list[str] = [
    r"\breklam\b", r"\breklamde[gğ]il\b", r"\breklamyok\b",
    r"\bisbirli[gğ]i\b", r"\bi[sş]birli[gğ]i\b", r"\bi\s?u\s?fbirli\s?u\s?fi\b",
    r"\bortakl[iı]k\b", r"\bsponsored?\b", r"\bsponsoru?\b", r"\banzeige\b",
    r"\blink\b", r"\bindirim\b", r"\bkod(?:lu)?\b", r"\bkupon\b",
    r"\bkampanya\b", r"\bsat[iı]n\s?al\b", r"\bprofilimde\b", r"\bsepete\b",
    r"\btrendyol\b", r"\bhepsiburada\b",
    r"\bdavet\b", r"\bpr\b",
    r"\breels\b", r"\bstory\b", r"\bfyp\b", r"\bkesfet\b",
    r"\bdump\b", r"\btbt\b", r"\btbf\b",
    r"\bdekorasyon\b", r"\bev\b",
]
_COMMERCIAL_RE = re.compile("|".join(_COMMERCIAL_PATTERNS), re.IGNORECASE)

# Kategori template blokları (pipeline tarafından eklenen sahte etiketler)
_TEMPLATES: list[str] = [
    "futbol atletizm spor fitness antrenman takim mac gol kosu spor ekipmani sampiyonluk",
    "moda fashion style kombin guzellik makyaj trend kiyafet aksesuar skincare beauty parfum",
    "lifestyle yasam gunluk vlog motivasyon inspiration minimalizm deko ev yasam tarzi aliskanlık",
    "lifestyle yasam gunluk vlog motivasyon inspiration minimalizm",
]

CONFIDENCE_THRESHOLD = 0.35   # Bu değerin altında kalan sonuçlar güvenilmez
FALLBACK_CATEGORY    = "lifestyle"


def clean_commercial_noise(text: str) -> str:
    """
    Metindeki ticari ve generic kelimeleri ile kategori template bloklarını kaldırır.
    SBERT'in bu kelimeleri finans/ticaret kümesine çekmesini önler.
    """
    if not isinstance(text, str):
        return ""
    t = text
    for tmpl in _TEMPLATES:
        t = t.replace(tmpl, "")
    t = _COMMERCIAL_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (norm(a) * norm(b) + 1e-10))


def predict_and_validate_category(
    influencer_name: str,
    raw_text: str,
    sbert_model,
    camp_embeddings: dict[str, np.ndarray],
    min_words: int = 5,
) -> tuple[str, float]:
    """
    Bir influencer için kategori tahmin eder.

    Adımlar:
      1. HARD_OVERRIDES kontrolü — kilitli kategori varsa doğrudan döner.
      2. Ticari gürültü temizliği (clean_commercial_noise).
      3. İçerik yeterlilik kontrolü — çok kısaysa fallback döner.
      4. SBERT kosinüs benzerliği hesabı.
      5. Güven eşiği (CONFIDENCE_THRESHOLD) kontrolü — düşükse fallback döner.

    Dönüş: (türkçe_kategori, güven_skoru)
    """
    # 1 — Bilgi Dağarcığı Override
    if influencer_name in HARD_OVERRIDES:
        return HARD_OVERRIDES[influencer_name], 1.0

    # 2 — Ticari gürültü temizliği
    clean_text = clean_commercial_noise(raw_text)

    # 3 — İçerik yeterlilik kontrolü
    if len(clean_text.split()) < min_words:
        return FALLBACK_CATEGORY, 0.0

    # 4 — SBERT embedding + kosinüs skoru
    emb    = sbert_model.encode([clean_text])[0]
    scores = {camp: _cosine(emb, camp_emb) for camp, camp_emb in camp_embeddings.items()}
    best_camp   = max(scores, key=scores.get)
    best_score  = scores[best_camp]
    predicted   = CAMP_TO_TURK.get(best_camp, FALLBACK_CATEGORY)

    # 5 — Güven eşiği
    if best_score < CONFIDENCE_THRESHOLD:
        return FALLBACK_CATEGORY, best_score

    return predicted, best_score
