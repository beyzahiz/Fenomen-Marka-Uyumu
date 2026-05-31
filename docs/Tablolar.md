# Tez İçin Kullanılabilecek Tablolar

Bu dosya, tez metnine doğrudan alınabilecek tablo taslaklarını tek yerde toplamak için hazırlanmıştır. Tablolar; geliştirme süreci raporu, model doğrulama çıktıları, QA test sonuçları ve proje mimarisi üzerinden derlenmiştir.

> Not: Tezde numaralandırma yaparken bu dosyadaki "Tablo A/B/C" başlıklarını kendi tez sıralamana göre "Tablo 3.1, Tablo 3.2..." biçiminde güncelleyebilirsin.

---

## Tablo A - Veri Kaynağı Dağılımı

| Veri Kaynağı | Kayıt Sayısı | Kullanım Amacı |
|---|---:|---|
| Instagram kaynaklı gerçek profiller | 144 | Nihai öneri kalitesini gerçek sosyal medya verisi üzerinde test etmek |
| Sentetik kontrol profilleri | 100 | Model geliştirme, dengeleme ve kontrollü test senaryoları |
| Toplam | 244 | Fenomen-marka eşleştirme sisteminin ana veri kümesi |

---

## Tablo B - Veri Setinde Kullanılan Temel Alanlar

| Veri Alanı | Açıklama | Sistemdeki Kullanım Amacı |
|---|---|---|
| `username` | Fenomen hesabı | Profil kimliği ve sonuç listesi gösterimi |
| `category` | İçerik kategorisi | Sert kategori kontrolü ve alaka doğrulama |
| `followers` | Takipçi sayısı | Erişim potansiyeli ve hesap ölçeği belirleme |
| `engagement_rate` | Etkileşim oranı | Performans değerlendirmesi |
| `clean_tags_all` | Temizlenmiş metin havuzu | SBERT ve TF-IDF/KFS katmanlarının metinsel girdisi |
| `positive_ratio` | Pozitif duygu oranı | İçerik tonunu temsil eden yardımcı ML girdisi |
| `negative_ratio` | Negatif duygu oranı | İçerik tonunu temsil eden yardımcı ML girdisi |
| `avg_sentiment_score` | Ortalama duygu skoru | İçerik dilinin genel duygu yönelimi |
| `fake_risk` | Sahte takipçi / güvenilirlik riski | Risk cezası ve marka güvenliği kontrolü |
| `data_source` | Instagram veya sentetik kaynak bilgisi | Gerçek/sentetik veri ayrımı ve sonuç adaleti |
| `ml_label` | XGBoost uygunluk çıktısı | Açıklanabilir yapay zekâ etiketi |

---

## Tablo C - Ölçülebilir Bilimsel Hedefler

| Hedef | Ölçüt / Beklenen Sonuç |
|---|---|
| Fenomen verilerinden anlamlı öznitelik çıkarımı | Profil, etkileşim, kategori ve metinsel içerik alanlarından model girdilerinin üretilmesi |
| Yapay zekâ modelinin doğruluk oranı | Accuracy, precision, recall ve F1-score metrikleri ile model başarımının raporlanması |
| NLP tabanlı anlamsal eşleştirme başarımı | SBERT ve TF-IDF tabanlı metinsel temsil katmanlarıyla marka-fenomen uyumunun ölçülmesi |
| Prototip sistemin kullanıcı tarafında doğrulanması | Farklı kampanya senaryolarında önerilerin kategori ve marka uyumu açısından incelenmesi |

---

## Tablo D - Veri Ön İşleme Adımları

| Ön İşleme Adımı | Amaç | Model Üzerindeki Etki |
|---|---|---|
| Küçük harfe dönüştürme | Yazım biçimi farklılıklarını azaltmak | Aynı kelimelerin tek biçimde temsil edilmesi |
| Ticari gürültü temizleme | Reklam, kampanya ve jenerik ifadeleri azaltmak | SBERT benzerliğinin gerçek semantik içeriğe odaklanması |
| Hashtag sadeleştirme | Sosyal medya etiketlerini anlamlı metin sinyaline dönüştürmek | TF-IDF ve SBERT için daha temiz metin temsili |
| Eksik değer doldurma | Model girişlerinde hata oluşmasını engellemek | Fail-safe ve kesintisiz tahmin |
| Kategori doğrulama | Yanlış kategori sızıntısını azaltmak | Hard Relevance Layer için güvenilir kategori alanı |

---

## Tablo E - Öznitelik Katmanları

| Öznitelik Katmanı | Kullanılan Yöntem | Ölçtüğü Sinyal | Sistemdeki Rolü |
|---|---|---|---|
| SFS | Sentence-BERT + Cosine Similarity | Marka metni ile fenomen içeriği arasındaki anlamsal yakınlık | Ana semantik eşleştirme sinyali |
| KFS | TF-IDF + Cosine Similarity | Kampanya anahtar ifadelerinin fenomen metninde temsil edilme düzeyi | Açıklanabilir kelime tabanlı destek sinyali |
| NFS | Niş / kategori uygunluğu | Fenomenin içerik dikeyinin kampanya alanıyla uyumu | Alaka ve uzmanlık kontrolü |
| CFS | Kampanya / kitle uyumu | Kampanya profili ile fenomen kitlesi arasındaki uyum | Marka hedef kitlesi ile eşleştirme |
| Risk sinyalleri | `fake_risk` ve benzeri sayısal alanlar | Güvenilirlik ve kalite riski | Düşük güvenilirlik durumunda ceza uygulama |
| Duygu oranları | Pozitif / negatif oranlar | İçerik tonuna ilişkin sayısal gösterge | Yardımcı model girdisi |

---

## Tablo F - Yapay Zekâ Destekli Karar Mimarisi

| Mimari Katman | Girdi | Sistem İçindeki Görev | Çıktı |
|---|---|---|---|
| SBERT Semantik Katmanı | Marka metni ve fenomen içerikleri | Anlamsal yakınlığı hesaplar | SFS |
| TF-IDF / KFS Katmanı | Kampanya anahtar ifadeleri ve temizlenmiş fenomen metni | Kelime/ifade temsil düzeyini ölçer | KFS skoru |
| XGBoost Karar Katmanı | Sayısal ve metinsel öznitelikler | Fenomenin uygunluk durumunu sınıflandırır | `ml_label` |
| Kategori / Niş Katmanı | Fenomen kategorisi ve kampanya dikeyi | Kategori uyumunu kontrol eder | NFS |
| Kampanya / Kitle Katmanı | Kampanya profili ve fenomen kitle sinyalleri | Hedef kitle uyumunu değerlendirir | CFS |
| Risk Katmanı | `fake_risk` ve güvenilirlik göstergeleri | Düşük güvenilirlikte skoru cezalandırır | Risk cezası |
| Hard Relevance Layer | Kategori uyumsuzluğu | Alakasız profillerin üst sıralara çıkmasını engeller | Filtrelenmiş öneri listesi |
| Arayüz / XAI Katmanı | Final skor ve `ml_label` | Kullanıcıya açıklanabilir sonuç sunar | AI uygunluk rozeti ve öneri kartı |

---

## Tablo G - Makine Öğrenmesi Modellerinin Sistemdeki Rolü

| Model | Kullanım Amacı | Avantajı | Sistemdeki Rolü |
|---|---|---|---|
| XGBoost | Ana uygunluk sınıflandırması | Tablosal verilerde yüksek başarı, hızlı çıkarım ve farklı öznitelikleri birlikte değerlendirme | Ana karar destek modeli olarak `ml_label` ve uygunluk skoru üretir |
| LightGBM | Karşılaştırmalı model | Hızlı eğitim ve gradyan artırma tabanlı alternatif yapı | Benchmark amacıyla test edilmiştir |
| Random Forest | Karşılaştırmalı model | Topluluk öğrenmesi ile overfitting riskini azaltma | Model karşılaştırmasında referans topluluk yöntemi olarak kullanılmıştır |
| Logistic Regression | Referans model | Basit, açıklanabilir ve doğrusal karar sınırı sunma | Temel karşılaştırma modeli olarak kullanılmıştır |

---

## Tablo H - Model Performans Karşılaştırması

| Model | Accuracy | F1 (Weighted) | Precision | Recall |
|---|---:|---:|---:|---:|
| XGBoost | 0.998 | 0.998 | 0.998 | 0.998 |
| LightGBM | 0.994 | 0.994 | 0.994 | 0.994 |
| RandomForest | 0.998 | 0.998 | 0.998 | 0.998 |

---

## Tablo I - Overfitting Analizi

| Model | Train Skoru | Test Skoru | Fark | Durum |
|---|---:|---:|---:|---|
| XGBoost | 0.999 | 0.998 | 0.002 | OK |
| LightGBM | 1.000 | 0.994 | 0.006 | OK |
| RandomForest | 1.000 | 0.998 | 0.002 | OK |

---

## Tablo J - 5-Fold Cross Validation Sonuçları

| Model | Ortalama Skor | Standart Sapma |
|---|---:|---:|
| XGBoost | 0.993 | ±0.004 |
| LightGBM | 0.995 | ±0.003 |
| RandomForest | 0.989 | ±0.006 |

---

## Tablo K - XGBoost Sınıflandırma Raporu

| Sınıf | Precision | Recall | F1-Score | Support |
|---|---:|---:|---:|---:|
| orta | 0.99 | 1.00 | 1.00 | 175 |
| uygun | 1.00 | 1.00 | 1.00 | 40 |
| uygun_degil | 1.00 | 1.00 | 1.00 | 273 |
| accuracy |  |  | 1.00 | 488 |
| macro avg | 1.00 | 1.00 | 1.00 | 488 |
| weighted avg | 1.00 | 1.00 | 1.00 | 488 |

---

## Tablo L - Feature Importance İlk 15 Özellik

| Sıra | Özellik | Önem Skoru |
|---:|---|---:|
| 1 | SFS | 0.6492 |
| 2 | NFS | 0.2741 |
| 3 | positive_ratio | 0.0455 |
| 4 | negative_comment_ratio | 0.0095 |
| 5 | avg_sentiment_score | 0.0052 |
| 6 | category_yemek | 0.0034 |
| 7 | neutral_comment_ratio | 0.0029 |
| 8 | account_type_makro | 0.0028 |
| 9 | posts_per_month | 0.0019 |
| 10 | positive_comment_ratio | 0.0015 |
| 11 | avg_comment_sentiment | 0.0014 |
| 12 | engagement_rate | 0.0014 |
| 13 | comment_count | 0.0010 |
| 14 | account_type_mega | 0.0003 |
| 15 | negative_ratio | 0.0000 |

---

## Tablo M - QA Test Kategorileri

| Test Kategorisi | Test Edilen Boyut | Beklenen Sonuç | Gerçekleşen Sonuç | Durum |
|---|---|---|---|---|
| Birim Testleri | Veri ön işleme, hard override, tier katsayısı ve skor normalizasyonu | Fonksiyonların tekil olarak doğru çalışması | Tüm kontroller başarıyla tamamlandı | Başarılı |
| Entegrasyon Testleri | Flask API, MongoDB, model yükleme ve JSON sözleşmesi | Servislerin birlikte hatasız çalışması | API ve MongoDB entegrasyonu doğrulandı | Başarılı |
| Algoritmik Doğrulama | Moda/teknoloji gibi farklı kampanya sorguları | Kategori sızıntısının olmaması | Semantic leakage gözlenmedi | Başarılı |
| Sınır Durum Testleri | Boş, geçersiz ve aşırı uzun kampanya metinleri | Sistemin kontrollü hata vermesi veya güvenli yanıt üretmesi | 400 hata yanıtları ve uzun metinlerde güvenli işlem doğrulandı | Başarılı |
| Yük ve Latency Testleri | Ardışık ve eşzamanlı API istekleri | Sistemin istekleri zaman aşımı olmadan karşılaması | 10/10 ve 50/50 eşzamanlı istek başarılı | Başarılı |

---

## Tablo N - Ayrıntılı QA Test Sonuçları

| Test ID | Kategori | Senaryo | Beklenen Sonuç | Gerçekleşen Sonuç | Durum |
|---|---|---|---|---|---|
| TS-01 | Unit | `clean_commercial_noise` ticari gürültü temizleme | Reklam/ticaret kelimeleri atılır | Gürültü temizlendi, semantik kelimeler kaldı | PASS |
| TS-02 | Unit | Hard override: `@ardasaatci` | Kategori kesin olarak spor olur | spor, confidence=1.0 | PASS |
| TS-03 | Unit | Tier katsayısı hesaplama | mega=+5.0, makro=+2.0, mikro=0.0 | Beklenen bonuslar doğrulandı | PASS |
| TS-04 | Unit | Skor normalizasyonu | 105 ham skor 100.0'a clip edilir | 100.0 | PASS |
| TS-05 | Integration | Flask API + model yükleme health check | `/stats` 200 döner ve 244 profil yüklüdür | 244 profil, 144 Instagram, 100 sentetik | PASS |
| TS-06 | Integration | MongoDB veri kaynağı entegrasyonu | `/influencers` source=mongodb döner | MongoDB entegrasyonu doğrulandı | PASS |
| TS-07 | Integration | React-Flask JSON sözleşmesi | JSON içinde isim, skor, kategori, `ml_label`, `data_source` alanları vardır | Sözleşme doğrulandı | PASS |
| TS-08 | Algorithmic | Semantic search leakage kontrolü | Moda ve teknoloji sorgularında Top-5 kendi dikeyinde kalır | Leakage yok | PASS |
| TS-09 | Algorithmic | XGBoost metrik raporu üretimi | Accuracy, Precision, Recall, F1 metrikleri raporda bulunur | Rapor üretildi | PASS |
| TS-10 | Algorithmic | Sentetik vs gerçek veri ayrımı | Moda Top-5 içinde gerçek Instagram oranı yüksek olur | Instagram Top-5 oranı 1.00 | PASS |
| TS-11 | Boundary | Boş kampanya metni | 400 Bad Request döner | 400 döndü | PASS |
| TS-12 | Boundary | Anlamsız/kısa kampanya metni | 400 Bad Request döner | 400 döndü | PASS |
| TS-13 | Boundary | Aşırı uzun kampanya metni | Sistem OOM olmadan 200 döner | 200 OK, öneriler üretildi | PASS |
| TS-14 | Load | API latency / inference speed | Ardışık istekler başarılı olur | p50 yaklaşık 2.49 sn | PASS |
| TS-15 | Load | 10 eşzamanlı istek | Success rate >= %95 | 10/10 başarılı | PASS |
| TS-16 | Load | 50 eşzamanlı istek | Success rate >= %95 | 50/50 başarılı | PASS |

---

## Tablo O - Yük ve Latency Ölçümleri

| Test | Ölçülen Değer | Sonuç |
|---|---:|---|
| Ardışık API isteği p50 latency | ~2.49 saniye | Başarılı |
| Aşırı uzun metin yanıt süresi | ~3.04 saniye | Başarılı |
| 10 eşzamanlı istek | 10/10 başarılı | Başarılı |
| 50 eşzamanlı istek | 50/50 başarılı | Başarılı |
| Moda Top-5 Instagram oranı | 1.00 | Başarılı |
| Toplam MongoDB kayıt sayısı | 244 | Başarılı |

---

## Tablo P - Sistem Bileşenleri ve Kullanılan Teknolojiler

| Bileşen | Araç / Teknoloji | Kullanım Amacı |
|---|---|---|
| Programlama dili | Python, JavaScript | Veri analizi, backend ve arayüz geliştirme |
| Backend | Flask REST API | Öneri endpointleri ve model servisi |
| Frontend | React | Kullanıcı arayüzü, öneri kartları ve XAI rozetleri |
| Veritabanı | MongoDB | Fenomen profil verilerinin saklanması |
| NLP - Semantik Benzerlik | Sentence-Transformers / SBERT | Marka-fenomen anlamsal uyum skoru |
| NLP - Anahtar Kelime Desteği | TF-IDF / KFS | Açıklanabilir anahtar ifade uyumu |
| Makine öğrenmesi | XGBoost, LightGBM, RandomForest, Logistic Regression | Uygunluk sınıflandırması ve model karşılaştırması |
| Veri işleme | Pandas, NumPy | Veri temizleme, normalizasyon ve öznitelik çıkarımı |
| Model/veri yedekleme | `.pkl` checkpoint dosyaları | MongoDB kapalıyken fallback çalışma |
| Dağıtım | Docker / Docker Compose | Konteynerleştirme ve taşınabilir çalışma |

---

## Tablo Q - Arayüzde Gösterilen Açıklanabilirlik Alanları

| Arayüz Alanı | Kaynak / Model | Kullanıcıya Sağladığı Açıklama |
|---|---|---|
| Final Score | Sıralama motoru | Fenomenin genel öneri sırasındaki gücünü gösterir |
| AI Uygunluk Analizi Durumu | XGBoost `ml_label` | Fenomenin kampanya için uygun, orta veya uygun değil durumunu açıklar |
| Semantik Uyum | SBERT / SFS | Marka metni ile fenomen içeriği arasındaki anlam yakınlığını gösterir |
| Kampanya Uyumu | CFS / kampanya profili | Fenomenin hedef kampanya profiline ne kadar uyduğunu gösterir |
| Veri Kaynağı | `data_source` | Profilin gerçek Instagram mı sentetik mi olduğunu gösterir |
| Risk göstergesi | `fake_risk` | Marka güvenliği açısından potansiyel güvenilirlik riskini açıklar |

---

## Tablo R - Tezde Kullanılabilecek Kaynak Eşleştirme Tablosu

| Teknik Kavram | Tezde Kullanılacağı Yer | Önerilen Kaynak |
|---|---|---|
| Sentence-BERT | 3.4 Öznitelik Çıkarımı ve Doğal Dil İşleme | Reimers & Gurevych, 2019 |
| TF-IDF | 3.4 Öznitelik Çıkarımı ve Doğal Dil İşleme | Salton & Buckley, 1988 |
| Cosine Similarity | 3.4 Öznitelik Çıkarımı ve Doğal Dil İşleme | Manning, Raghavan & Schütze, 2008 |
| XGBoost | 3.5 Makine Öğrenmesi ve Karar Destek Modelleri | Chen & Guestrin, 2016 |
| LightGBM | 3.5 Makine Öğrenmesi ve Karar Destek Modelleri | Ke et al., 2017 |
| QA / yazılım testleri | 3.7 Model Başarımının Değerlendirilmesi | Proje içi test raporu |

