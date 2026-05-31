# QA Validation Report

Bu rapor, Fenomen-Marka Eslestirme sistemi icin Yazilim Muhendisligi ve Kalite Guvence (QA) test kosumlarini belgeler.
Kapsam: React arayuzu, Flask API, MongoDB entegrasyonu, SBERT tabanli anlamsal eslestirme ve XGBoost karar katmani.

- Toplam test: 16
- Basarili: 16
- Basarisiz: 0
- Basari orani: 100.0%

## Test Ozeti

| Test ID | Kategori | Senaryo | Beklenen Sonuc | Gerceklesen Sonuc | Metrik | Durum |
|---|---|---|---|---|---|---|
| TS-01 | Unit | clean_commercial_noise ticari gurultu temizleme | Reklam/ticaret kelimeleri atilir, semantik moda kelimeleri kalir | degil makyaj skincare kombin guzellik serum |  | PASS |
| TS-02 | Unit | Hard override: @ardasaatci | SBERT sonucu ne olursa olsun kategori spor olur | spor, confidence=1.0 |  | PASS |
| TS-03 | Unit | Tier katsayisi hesaplama | mega=+5.0, makro=+2.0, mikro=0.0 | mega=5.0, makro=2.0, mikro=0.0 |  | PASS |
| TS-04 | Unit | Skor normalizasyonu | 105 ham skor 100.0'a clip edilir | 100.0 |  | PASS |
| TS-05 | Integration | Flask API + model yukleme health check | /stats 200 doner ve 244 profil yukludur | status=200, total=244, sources={'instagram': 144, 'synthetic': 100} |  | PASS |
| TS-06 | Integration | MongoDB veri kaynagi entegrasyonu | /influencers source=mongodb ve data_source alanlari doner | source=mongodb, count=5 |  | PASS |
| TS-07 | Integration | React-Flask JSON sozlesmesi icin POST /recommend paketi | JSON icinde isim, skor, kategori, ml_label ve data_source alanlari vardir | status=200, first=@influencer77 |  | PASS |
| TS-08 | Algorithmic | Semantic search leakage kontrolu | Moda ve teknoloji sorgularinda Top-5 kendi dikeyinde kalir | leakage yok |  | PASS |
| TS-09 | Algorithmic | XGBoost metrik raporu uretimi | Accuracy, Precision, Recall, F1 metrikleri raporda bulunur | report_exists=True, size=2496 | docs/model_reports/model_validation_report.txt | PASS |
| TS-10 | Algorithmic | Sentetik vs gercek veri ayrimi | Moda Top-5 icinde gercek Instagram orani yuksektir ve sentetik manipule etmez | instagram_top5_ratio=1.00 |  | PASS |
| TS-11 | Boundary | Bos kampanya metni | 400 Bad Request doner | status=400, error=brand_text en az 10 karakter olmali |  | PASS |
| TS-12 | Boundary | Anlamsiz/kisa kampanya metni | 400 Bad Request doner | status=400, error=brand_text en az 10 karakter olmali |  | PASS |
| TS-13 | Boundary | Asiri uzun kampanya metni | Sistem OOM olmadan 200 doner ve oneriler uretilir | status=200, count=5, elapsed_ms=3038.6 | 3038.6 ms | PASS |
| TS-14 | Load | API latency / inference speed | 5 ardışık istek basarili ve p50 < 5000 ms | p50=2488.3 ms, max=2523.9 ms | p50=2488.3 ms | PASS |
| TS-15 | Load | 10 eszamanli istek | Success rate >= 95%, timeout yok | success=10/10, p95=4490.7 ms, total=4550.1 ms | success_rate=100.00% | PASS |
| TS-16 | Load | 50 eszamanli istek | Success rate >= 95%, timeout yok | success=50/50, p95=16166.0 ms, total=16224.1 ms | success_rate=100.00% | PASS |

## Akademik Degerlendirme Notlari

- Unit test katmani, veri on isleme ve deterministik karar kurallarinin izole dogrulamasini yapar.
- Integration test katmani, MongoDB, Flask endpointleri ve JSON sozlesmesinin birlikte calistigini kanitlar.
- Algorithmic validation katmani, anlamsal arama sızıntısını ve XGBoost metrik raporunun varligini kontrol eder.
- Boundary test katmani, bos/gecersiz/asiri uzun girdilerde sistemin kontrollu davrandigini dogrular.
- Load test katmani, gelistirme ortami uzerinde latency ve eszamanli istek toleransini olcer.

Not: 100+ eszamanli kullanici icin JMeter/Locust ile ayrica production benzeri WSGI ortaminda test onerilir; bu rapor yerel Flask gelistirme sunucusu uzerindeki kanit kosumudur.
