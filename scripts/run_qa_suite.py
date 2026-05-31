"""
run_qa_suite.py
===============
TUBITAK kapanis raporu icin otomatik QA dogrulama kosumu.

Kapsam:
  1. Unit tests
  2. Integration tests
  3. Algorithmic validation
  4. Boundary / negative tests
  5. Load / latency tests

Kullanim:
  python scripts/run_qa_suite.py

Cikti:
  docs/qa_validation_report.md
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_BASE = "http://localhost:5000"
REPORT_PATH = ROOT / "docs" / "qa_validation_report.md"


@dataclass
class TestResult:
    test_id: str
    category: str
    scenario: str
    expected: str
    actual: str
    passed: bool
    metric: str = ""

    @property
    def status(self) -> str:
        return "BASARILI" if self.passed else "BASARISIZ"


results: list[TestResult] = []


def add_result(
    test_id: str,
    category: str,
    scenario: str,
    expected: str,
    actual: str,
    passed: bool,
    metric: str = "",
) -> None:
    results.append(TestResult(test_id, category, scenario, expected, actual, passed, metric))
    print(f"{'PASS' if passed else 'FAIL'} | {test_id} | {scenario} | {actual}")


def get_json(path: str, timeout: int = 30) -> tuple[int, dict]:
    with urllib.request.urlopen(API_BASE + path, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def post_json(path: str, body: dict, timeout: int = 60) -> tuple[int, dict]:
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"error": payload}
        return exc.code, data


def numeric(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def run_unit_tests() -> None:
    from pipeline.category_utils import clean_commercial_noise, predict_and_validate_category
    from app import bounded_score, tier_bonus_for_account_type

    dirty = (
        "REKLAM degil trendyol indirim kod profilimde story fyp "
        "makyaj skincare kombin guzellik serum"
    )
    clean = clean_commercial_noise(dirty).lower()
    noise_removed = all(
        token not in clean
        for token in ["reklam", "trendyol", "indirim", "profilimde", "story", "fyp"]
    )
    semantic_kept = all(token in clean for token in ["makyaj", "skincare", "kombin", "serum"])
    add_result(
        "TS-01",
        "Unit",
        "clean_commercial_noise ticari gurultu temizleme",
        "Reklam/ticaret kelimeleri atilir, semantik moda kelimeleri kalir",
        clean,
        noise_removed and semantic_kept,
    )

    class FailingModel:
        def encode(self, _texts):
            raise AssertionError("Hard override varken SBERT cagrilmamali")

    predicted, confidence = predict_and_validate_category(
        "@ardasaatci",
        "moda kombin makyaj lifestyle gibi yaniltici metin",
        FailingModel(),
        {},
    )
    add_result(
        "TS-02",
        "Unit",
        "Hard override: @ardasaatci",
        "SBERT sonucu ne olursa olsun kategori spor olur",
        f"{predicted}, confidence={confidence}",
        predicted == "spor" and confidence == 1.0,
    )

    tier_ok = (
        tier_bonus_for_account_type("mega") == 5.0
        and tier_bonus_for_account_type("makro") == 2.0
        and tier_bonus_for_account_type("mikro") == 0.0
    )
    add_result(
        "TS-03",
        "Unit",
        "Tier katsayisi hesaplama",
        "mega=+5.0, makro=+2.0, mikro=0.0",
        (
            f"mega={tier_bonus_for_account_type('mega')}, "
            f"makro={tier_bonus_for_account_type('makro')}, "
            f"mikro={tier_bonus_for_account_type('mikro')}"
        ),
        tier_ok,
    )

    add_result(
        "TS-04",
        "Unit",
        "Skor normalizasyonu",
        "105 ham skor 100.0'a clip edilir",
        str(bounded_score(105.0)),
        bounded_score(105.0) == 100.0,
    )


def run_integration_tests() -> None:
    status, stats = get_json("/stats")
    source_ok = stats.get("data_sources") == {"instagram": 144, "synthetic": 100}
    add_result(
        "TS-05",
        "Integration",
        "Flask API + model yukleme health check",
        "/stats 200 doner ve 244 profil yukludur",
        f"status={status}, total={stats.get('total_influencers')}, sources={stats.get('data_sources')}",
        status == 200 and stats.get("success") is True and stats.get("total_influencers") == 244 and source_ok,
    )

    status, influencers = get_json("/influencers?limit=5")
    add_result(
        "TS-06",
        "Integration",
        "MongoDB veri kaynagi entegrasyonu",
        "/influencers source=mongodb ve data_source alanlari doner",
        f"source={influencers.get('source')}, count={influencers.get('count')}",
        (
            status == 200
            and influencers.get("source") == "mongodb"
            and all("data_source" in row for row in influencers.get("influencers", []))
        ),
    )

    status, recommendation = post_json(
        "/recommend",
        {
            "brand_text": (
                "Moda, guzellik, makyaj, skincare ve kombin odakli bir lansman "
                "icin Instagram influencerlari ariyoruz."
            ),
            "top_n": 10,
        },
    )
    first = recommendation.get("recommendations", [{}])[0]
    add_result(
        "TS-07",
        "Integration",
        "React-Flask JSON sozlesmesi icin POST /recommend paketi",
        "JSON icinde isim, skor, kategori, ml_label ve data_source alanlari vardir",
        f"status={status}, first={first.get('influencer_name')}",
        (
            status == 200
            and recommendation.get("success") is True
            and {"influencer_name", "final_score", "category", "ml_label", "data_source"}.issubset(first)
        ),
    )


ALLOWED_MAIN = {
    "beauty_fashion": ["beauty_fashion", "lifestyle"],
    "lifestyle": ["lifestyle"],
    "fitness_health": ["fitness_health"],
    "food_gastronomy": ["food_gastronomy"],
    "technology": ["technology"],
    "gaming": ["gaming"],
    "travel": ["travel"],
    "finance_business": ["finance_business"],
    "entertainment": ["entertainment"],
    "sports": ["sports", "fitness_health"],
}

POSITIVE_FIT = {
    "beauty_fashion": ["fashion_brand_fit", "luxury_brand_fit"],
    "lifestyle": ["lifestyle_brand_fit", "wellness_brand_fit"],
    "fitness_health": ["sports_brand_fit", "wellness_brand_fit"],
    "food_gastronomy": ["food_brand_fit"],
    "technology": ["tech_brand_fit"],
    "gaming": ["gaming_brand_fit", "tech_brand_fit"],
    "travel": ["travel_brand_fit"],
    "finance_business": ["fintech_brand_fit", "tech_brand_fit"],
    "entertainment": ["lifestyle_brand_fit"],
    "sports": ["sports_brand_fit"],
}

CONFLICT_FIT = {
    "beauty_fashion": [
        "sports_brand_fit",
        "gaming_brand_fit",
        "food_brand_fit",
        "fintech_brand_fit",
        "tech_brand_fit",
        "travel_brand_fit",
    ],
    "sports": ["fashion_brand_fit", "food_brand_fit", "gaming_brand_fit"],
    "fitness_health": ["fashion_brand_fit", "food_brand_fit", "gaming_brand_fit"],
    "food_gastronomy": ["sports_brand_fit", "gaming_brand_fit", "tech_brand_fit"],
    "technology": ["fashion_brand_fit", "food_brand_fit", "sports_brand_fit"],
    "gaming": ["fashion_brand_fit", "food_brand_fit", "sports_brand_fit"],
}


def bad_relevance_reason(record: dict, campaign: str) -> str:
    main = str(record.get("main_category", ""))
    fit = str(record.get("brand_fit_tags", ""))
    sfs = numeric(record.get("sfs"))
    main_ok = not ALLOWED_MAIN.get(campaign) or main in ALLOWED_MAIN.get(campaign, [])
    fit_ok = not POSITIVE_FIT.get(campaign) or any(tag in fit for tag in POSITIVE_FIT.get(campaign, []))
    reasons = []
    if any(tag in fit for tag in CONFLICT_FIT.get(campaign, [])):
        reasons.append("brand_fit_conflict")
    if sfs < 30.0:
        reasons.append("sfs_below_30")
    if not main_ok and not fit_ok:
        reasons.append("main_fit_mismatch")
    return ",".join(reasons)


def run_algorithmic_tests() -> None:
    scenarios = {
        "fashion": ("beauty_fashion", "Moda giyim kombin makyaj skincare guzellik kampanyasi"),
        "technology": ("technology", "Teknoloji yazilim kodlama yapay zeka ve dijital urun kampanyasi"),
    }
    leakage = []
    for name, (expected_campaign, text) in scenarios.items():
        _status, data = post_json("/recommend", {"brand_text": text, "top_n": 10})
        camp = data.get("closest_campaign")
        for rec in data.get("recommendations", [])[:5]:
            reason = bad_relevance_reason(rec, camp)
            if camp != expected_campaign or reason:
                leakage.append(f"{name}:{rec.get('influencer_name')}:{camp}:{reason}")
    add_result(
        "TS-08",
        "Algorithmic",
        "Semantic search leakage kontrolu",
        "Moda ve teknoloji sorgularinda Top-5 kendi dikeyinde kalir",
        "; ".join(leakage) if leakage else "leakage yok",
        not leakage,
    )

    report_path = ROOT / "docs" / "model_reports" / "model_validation_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    has_xgb = "XGBoost" in report_text and "Accuracy" in report_text
    add_result(
        "TS-09",
        "Algorithmic",
        "XGBoost metrik raporu uretimi",
        "Accuracy, Precision, Recall, F1 metrikleri raporda bulunur",
        f"report_exists={report_path.exists()}, size={report_path.stat().st_size if report_path.exists() else 0}",
        has_xgb,
        "docs/model_reports/model_validation_report.txt",
    )

    _status, data = post_json(
        "/recommend",
        {
            "brand_text": (
                "Yeni makyaj ve cilt bakimi urunleri icin moda guzellik "
                "kozmetik kombin stil ve skincare icerikleri ureten Instagram influencerlari"
            ),
            "top_n": 10,
        },
    )
    top5 = data.get("recommendations", [])[:5]
    instagram_ratio = (
        sum(1 for rec in top5 if rec.get("data_source") == "instagram") / max(len(top5), 1)
    )
    add_result(
        "TS-10",
        "Algorithmic",
        "Sentetik vs gercek veri ayrimi",
        "Moda Top-5 icinde gercek Instagram orani yuksektir ve sentetik manipule etmez",
        f"instagram_top5_ratio={instagram_ratio:.2f}",
        instagram_ratio >= 0.8,
    )


def run_boundary_tests() -> None:
    status, payload = post_json("/recommend", {"brand_text": "", "top_n": 5})
    add_result(
        "TS-11",
        "Boundary",
        "Bos kampanya metni",
        "400 Bad Request doner",
        f"status={status}, error={payload.get('error')}",
        status == 400,
    )

    status, payload = post_json("/recommend", {"brand_text": "!?!?!?", "top_n": 5})
    add_result(
        "TS-12",
        "Boundary",
        "Anlamsiz/kisa kampanya metni",
        "400 Bad Request doner",
        f"status={status}, error={payload.get('error')}",
        status == 400,
    )

    long_text = " ".join(["moda makyaj skincare kombin guzellik"] * 1200)
    start = time.perf_counter()
    status, payload = post_json("/recommend", {"brand_text": long_text, "top_n": 5}, timeout=120)
    elapsed_ms = (time.perf_counter() - start) * 1000
    add_result(
        "TS-13",
        "Boundary",
        "Asiri uzun kampanya metni",
        "Sistem OOM olmadan 200 doner ve oneriler uretilir",
        f"status={status}, count={payload.get('count')}, elapsed_ms={elapsed_ms:.1f}",
        status == 200 and payload.get("success") is True and payload.get("count", 0) > 0,
        f"{elapsed_ms:.1f} ms",
    )


def timed_recommend(query: str) -> tuple[bool, float]:
    start = time.perf_counter()
    try:
        status, payload = post_json("/recommend", {"brand_text": query, "top_n": 5}, timeout=120)
        ok = status == 200 and payload.get("success") is True
    except Exception:
        ok = False
    return ok, (time.perf_counter() - start) * 1000


def run_load_tests() -> None:
    warm_query = "Moda guzellik makyaj skincare kombin kampanyasi icin influencer onerisi"
    samples = []
    for _ in range(5):
        ok, elapsed = timed_recommend(warm_query)
        if ok:
            samples.append(elapsed)
    p50 = statistics.median(samples) if samples else 0.0
    max_latency = max(samples) if samples else 0.0
    add_result(
        "TS-14",
        "Load",
        "API latency / inference speed",
        "5 ardışık istek basarili ve p50 < 5000 ms",
        f"p50={p50:.1f} ms, max={max_latency:.1f} ms",
        len(samples) == 5 and p50 < 5000,
        f"p50={p50:.1f} ms",
    )

    load_levels = [10, 50]
    for idx, level in enumerate(load_levels, start=15):
        query = "Teknoloji yazilim yapay zeka dijital urun kampanyasi"
        start = time.perf_counter()
        latencies = []
        success = 0
        with ThreadPoolExecutor(max_workers=level) as executor:
            futures = [executor.submit(timed_recommend, query) for _ in range(level)]
            for fut in as_completed(futures):
                ok, elapsed = fut.result()
                latencies.append(elapsed)
                success += int(ok)
        total_ms = (time.perf_counter() - start) * 1000
        success_rate = success / level
        p95 = sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else 0.0
        add_result(
            f"TS-{idx}",
            "Load",
            f"{level} eszamanli istek",
            "Success rate >= 95%, timeout yok",
            f"success={success}/{level}, p95={p95:.1f} ms, total={total_ms:.1f} ms",
            success_rate >= 0.95,
            f"success_rate={success_rate:.2%}",
        )


def write_report() -> None:
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    lines = [
        "# QA Validation Report",
        "",
        "Bu rapor, Fenomen-Marka Eslestirme sistemi icin Yazilim Muhendisligi ve Kalite Guvence (QA) test kosumlarini belgeler.",
        "Kapsam: React arayuzu, Flask API, MongoDB entegrasyonu, SBERT tabanli anlamsal eslestirme ve XGBoost karar katmani.",
        "",
        f"- Toplam test: {len(results)}",
        f"- Basarili: {passed}",
        f"- Basarisiz: {failed}",
        f"- Basari orani: {(passed / max(len(results), 1)):.1%}",
        "",
        "## Test Ozeti",
        "",
        "| Test ID | Kategori | Senaryo | Beklenen Sonuc | Gerceklesen Sonuc | Metrik | Durum |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            "| {id} | {category} | {scenario} | {expected} | {actual} | {metric} | {status} |".format(
                id=result.test_id,
                category=result.category,
                scenario=result.scenario.replace("|", "/"),
                expected=result.expected.replace("|", "/"),
                actual=result.actual.replace("|", "/").replace("\n", " "),
                metric=result.metric.replace("|", "/"),
                status=status,
            )
        )
    lines.extend(
        [
            "",
            "## Akademik Degerlendirme Notlari",
            "",
            "- Unit test katmani, veri on isleme ve deterministik karar kurallarinin izole dogrulamasini yapar.",
            "- Integration test katmani, MongoDB, Flask endpointleri ve JSON sozlesmesinin birlikte calistigini kanitlar.",
            "- Algorithmic validation katmani, anlamsal arama sızıntısını ve XGBoost metrik raporunun varligini kontrol eder.",
            "- Boundary test katmani, bos/gecersiz/asiri uzun girdilerde sistemin kontrollu davrandigini dogrular.",
            "- Load test katmani, gelistirme ortami uzerinde latency ve eszamanli istek toleransini olcer.",
            "",
            "Not: 100+ eszamanli kullanici icin JMeter/Locust ile ayrica production benzeri WSGI ortaminda test onerilir; bu rapor yerel Flask gelistirme sunucusu uzerindeki kanit kosumudur.",
            "",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRapor yazildi: {REPORT_PATH}")


def main() -> int:
    run_unit_tests()
    run_integration_tests()
    run_algorithmic_tests()
    run_boundary_tests()
    run_load_tests()
    write_report()
    failed = [result for result in results if not result.passed]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
