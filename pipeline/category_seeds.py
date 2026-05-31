# Kategori tohum kelimeleri — SBERT / clean_tags_all (notebook + pipeline ortak)

CATEGORY_SEED: dict[str, str] = {
    "spor": "futbol atletizm spor fitness antrenman takim mac gol kosu spor ekipmani sampiyonluk",
    "moda": "moda fashion style kombin guzellik makyaj trend kiyafet aksesuar skincare beauty parfum",
    "yemek": "yemek tarif mutfak lezzet gastronomi restoran food recipe chef gurme kahvalti",
    "oyun": "gaming oyun esport gamer stream twitch pc console fps videogame replay",
    "teknoloji": "teknoloji tech gadget yapay zeka yazilim uygulama dijital inovasyon review unboxing",
    "saglik": "saglik wellness yoga pilates beslenme saglikli meditasyon terapi mental health",
    "lifestyle": "lifestyle yasam gunluk vlog motivasyon inspiration minimalizm dekorasyon ev",
    "seyahat": "seyahat travel tatil destinasyon kesfet gezi otel ucak macera worldtravel",
    "egitim": "egitim education school universite ogretmen bilim matematik ders kurs",
    "anne-bebek": "anne bebek annelik cocuk aile hamile dogum emzirme oyuncak pedagoji",
    "eglence": "muzik eglence konser dans film dizi komedi mizah sarki performans tiyatro",
}


def seed_for_category(category: str) -> str:
    return CATEGORY_SEED.get(str(category or ""), "")


def append_seed_to_tags(clean_tags_all: str, category: str) -> str:
    seed = seed_for_category(category)
    if not seed:
        return str(clean_tags_all or "").strip()
    return f"{clean_tags_all} {seed}".strip()


def prepend_seed_to_text(text: str, category: str, *, repeat: int = 3) -> str:
    seed = seed_for_category(category)
    if not seed:
        return str(text or "").strip()
    prefix = " ".join([seed] * repeat)
    return f"{prefix} {text}".strip()
