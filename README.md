# Yapay Zekâ Destekli Fenomen–Marka Eşleştirme Sistemi

**TÜBİTAK 2209-A Üniversite Öğrencileri Araştırma Projeleri Destekleme Programı**

Bir markanın metin açıklamasını alıp, 100 fenomenlik veri tabanından en uygun influencer'ları semantik benzerlik, sayısal performans, işbirlikçi filtreleme, duygu analizi ve sahte takipçi riski birleştirerek sıralayan uçtan uca bir yapay zekâ sistemi.

---

## İçindekiler

1. [Sistem Mimarisi ve Dosya Yapısı](#1-sistem-mimarisi-ve-dosya-yapısı)
2. [Skor Formülleri ve Algoritmalar](#2-skor-formülleri-ve-algoritmalar)
3. [Makine Öğrenmesi Pipeline](#3-makine-öğrenmesi-pipeline)
4. [Model Doğrulama Sonuçları](#4-model-doğrulama-sonuçları)
5. [API Endpointleri](#5-api-endpointleri)
6. [Frontend Mimarisi](#6-frontend-mimarisi)
7. [Kurulum ve Çalıştırma](#7-kurulum-ve-çalıştırma)
8. [Docker ile Dağıtım](#8-docker-ile-dağıtım)
9. [CSV Dışa Aktarma](#9-csv-dışa-aktarma)
10. [Karşılaşılan Hatalar ve Çözümler](#10-karşılaşılan-hatalar-ve-çözümler)

---

## 1. Sistem Mimarisi ve Dosya Yapısı

```
TezBitirme/
│
├── app.py                          # Flask REST API — tüm endpoint'ler burada
├── analiz_pipeline.py              # Tek seferlik analiz pipeline'ı (pkl üretir)
├── influencer_features.py          # Özellik mühendisliği yardımcı fonksiyonları
├── _validate_models.py             # Bağımsız model doğrulama scripti
│
├── frontend/
│   ├── index.html                  # Ana HTML sayfası
│   └── static/
│       ├── app.js                  # Vanilla JavaScript — tüm UI mantığı
│       └── style.css               # CSS Design System (dark theme)
│
├── *.pkl                           # Eğitilmiş modeller ve önbellek dosyaları
│   ├── best_model_xgb.pkl          # XGBoost modeli
│   ├── label_encoder.pkl           # Etiket kodlayıcı
│   ├── feature_columns.pkl         # Model özellik sütunları
│   ├── kmeans_model.pkl            # K-Means kümeleme modeli
│   └── influencer_summary_checkpoint.pkl  # Fenomen özet verisi
│
├── model_reports/                  # Model doğrulama çıktıları
│   ├── confusion_matrices.png      # Karmaşıklık matrisleri
│   ├── feature_importance.png      # Özellik önem sıralaması
│   ├── model_comparison.png        # Model karşılaştırma grafiği
│   └── model_validation_report.txt # Detaylı metin raporu
│
├── Dockerfile                      # Docker imaj tanımı
├── docker-compose.yml              # Docker Compose servisleri
├── .dockerignore                   # Docker build hariç tutulanlar
├── requirements.txt                # Geliştirme bağımlılıkları
├── requirements-prod.txt           # Üretim bağımlılıkları (sürüm sabitlenmiş)
└── start.bat                       # Windows kolay başlatma scripti
```

### Bileşenler Arası Veri Akışı

```
analiz_pipeline.py
    └─► *.pkl dosyaları (modeller + fenomen verileri)
            └─► app.py yükler (başlangıçta bir kez)
                    └─► /recommend endpoint'i
                            ├─► SBERT embedding (marka metni)
                            ├─► SFS hesaplama (cosine similarity)
                            ├─► CFS hesaplama (softmax agirliklar)
                            ├─► NFS (pkl'den önceden hesaplı)
                            ├─► XGBoost tahmin (ml_label)
                            └─► JSON yanit → frontend/app.js → UI
```

---

## 2. Skor Formülleri ve Algoritmalar

Sistem beş bileşeni birleştirerek iki farklı skor üretir.

### 2.1 NFS — Sayısal Performans Skoru (Numerical Fit Score)

Fenomenin ham sayısal metriklerini 0–100 aralığına normalize eden skor:

```
NFS = (engagement_rate × 0.50 + FGR × 0.30 + posts_per_month × 0.20) × 100
```

- **engagement_rate**: Gönderi başına ortalama etkileşim oranı
- **FGR** (Follower Growth Rate): Takipçi büyüme hızı
- **posts_per_month**: Aylık gönderi sayısı (normalize edilmiş)

> NFS, `analiz_pipeline.py` içinde hesaplanır ve checkpoint'e kaydedilir. İstek anında yeniden hesaplanmaz.

---

### 2.2 SFS — Semantik Uyum Skoru (Semantic Fit Score)

Marka metni ile fenomenin biyografi/içerik metni arasındaki SBERT cosine benzerliği:

```
SFS = cosine_similarity(embed(marka_metni), embed(fenomen_metni)) × 100
```

**Model:** `paraphrase-multilingual-MiniLM-L12-v2` (Türkçe destekli, 512 boyut)

- Fenomen embedding'leri `analiz_pipeline.py`'da önceden hesaplanır ve kaydedilir
- Marka embedding'i her istek anında hesaplanır (yaklasik 0.1–0.3 sn)
- Cosine similarity formülü: `(A·B) / (||A|| × ||B||)`

---

### 2.3 CFS — İşbirlikçi Uyum Skoru (Collaborative Fit Score)

6 kampanya şablonunu kullanan bir tür işbirlikçi filtreleme mekanizması:

**Adım 1 — Kampanya Embedding'leri (başlangıçta bir kez hesaplanır):**
```python
CAMPAIGN_TEXTS = {
    "spor_kampanyasi"     : "fitness spor antrenman...",
    "moda_kampanyasi"     : "moda trend stil...",
    "teknoloji_kampanyasi": "teknoloji yazilim...",
    "yemek_kampanyasi"    : "yemek tarif lezzet...",
    "annebebek_kampanyasi": "anne bebek cocuk...",
    "oyun_kampanyasi"     : "oyun e-spor gaming...",
}
```

**Adım 2 — Marka–Kampanya Ağırlıkları (softmax normalize):**
```
raw[k]    = cosine_sim(marka_embedding, kampanya_embedding[k])
weight[k] = exp(raw[k] × 10) / toplam_exp   # sicaklik parametresi = 10
```

**Adım 3 — CFS Hesabı:**
```
CFS = toplam(weight[k] × sim_kampanya[k]) × 100
```

Burada `sim_kampanya[k]`, fenomenin ilgili kampanya şablonuna olan SBERT benzerliğidir (analiz_pipeline'da önceden hesaplı).

> CFS'nin mantığı: Marka hangi kampanya tipine ne kadar yakınsa (softmax ağırlıklar), o kampanyada güçlü fenomenlere daha fazla puan verir. Bu, "benzer markaların tercih ettiği fenomenleri öner" fikrinin formülasyonudur.

---

### 2.4 BAS — Marka Uyum Skoru (Brand Affinity Score)

CFS'siz temel skor — fenomenin genel performansını ölçer:

```
BAS = SFS×0.35 + NFS×0.30 + PositiveRatio×0.25 + (100−FakeRisk)×0.10
```

| Bileşen | Ağırlık | Açıklama |
|---------|---------|----------|
| SFS | %35 | Semantik metin benzerliği |
| NFS | %30 | Sayısal performans |
| PositiveRatio | %25 | BERT duygu analizinden pozitif yorum oranı |
| (100−FakeRisk) | %10 | Sahte takipçi riski terslemesi |

---

### 2.5 Final Score — Kampanyaya Özel Nihai Skor

CFS dahil, kampanyaya özelleştirilmiş skor:

```
Final = SFS×0.30 + NFS×0.25 + CFS×0.25 + PositiveRatio×0.10 + (100−FakeRisk)×0.10
```

| Bileşen | Ağırlık | Değişim |
|---------|---------|---------|
| SFS | %30 | BAS'a göre -5 puan |
| NFS | %25 | BAS'a göre -5 puan |
| **CFS** | **%25** | **Yeni eklenen kampanya boyutu** |
| PositiveRatio | %10 | BAS'a göre -15 puan |
| (100−FakeRisk) | %10 | Aynı |

---

### 2.6 Duygu Analizi

Her fenomenin yorumları `transformers` pipeline ile analiz edilir:

```python
from transformers import pipeline
sentiment = pipeline(
    "sentiment-analysis",
    model="nlptown/bert-base-multilingual-uncased-sentiment"
)
```

- 1–5 yıldız çıktısı → pozitif (4–5 yıldız) / nötr (3) / negatif (1–2) sınıflandırması
- `positive_ratio = pozitif_yorum_sayısı / toplam_yorum × 100`

---

### 2.7 Sahte Takipçi Tespiti

Makine öğrenmesi tabanlı risk skoru:

- Katılım anormalliği, takipçi artış tutarsızlığı gibi özellikler kullanılır
- Risk kategorileri: `DÜŞÜK` / `ORTA` / `YÜKSEK`

---

### 2.8 K-Means Kümeleme (Benzer Fenomenler)

```python
from sklearn.cluster import KMeans
kmeans = KMeans(n_clusters=8, random_state=42)
kmeans.fit(feature_matrix)
```

Bir fenomenin "Benzer" butonuna tıklandığında, aynı kümedeki diğer fenomenler `/influencers/<name>/similar` endpoint'i üzerinden döner.

---

## 3. Makine Öğrenmesi Pipeline

### 3.1 Etiket Üretimi (Kural Tabanlı)

Model eğitimi için etiketler deterministik kurallarla üretilir:

```python
if sfs > 0.35 and nfs > 25 and positive_ratio > 60:
    label = "uygun"
elif sfs < 0.20 or nfs < 15 or positive_ratio < 45:
    label = "uygun_degil"
else:
    label = "orta"
```

Her fenomen × 6 kampanya kombinasyonu için bu kural uygulanır → toplam ~600 örnek.

### 3.2 Özellik Mühendisliği

```python
df_enc = pd.get_dummies(df_model, columns=["category", "account_type", "campaign"])
X = df_enc.drop(columns=["influencer_name", "label"])
```

One-hot encoding sonrası: `engagement_rate`, `FGR`, `posts_per_month`, `NFS`, `SFS`, `positive_ratio`, `negative_ratio`, `avg_sentiment_score` + kategorik değişkenlerin binary kodlamaları.

### 3.3 Model Eğitimi

```python
from xgboost import XGBClassifier
xgb = XGBClassifier(
    n_estimators=100, max_depth=4, learning_rate=0.1,
    use_label_encoder=False, eval_metric="mlogloss", random_state=42
)
xgb.fit(X_train, y_train_encoded)
```

Karşılaştırma için LightGBM ve RandomForest de eğitilir (`_validate_models.py`).

---

## 4. Model Doğrulama Sonuçları

`_validate_models.py` scripti mevcut pkl dosyalarından metrikleri yeniden üretir ve grafik çıktılar oluşturur.

### 4.1 Model Karşılaştırması (Test Seti, %20)

| Model | Accuracy | F1 (Weighted) | Precision | Recall |
|-------|----------|--------------|-----------|--------|
| **XGBoost** | **1.000** | **1.000** | **1.000** | **1.000** |
| LightGBM | 0.958 | 0.957 | 0.958 | 0.958 |
| RandomForest | 0.958 | 0.958 | 0.958 | 0.958 |

**Neden XGBoost %100 doğruluk?**
Etiketler deterministik eşik kurallarından üretildiği için (SFS>0.35 VE NFS>25 VE PR>60 → uygun), XGBoost bu kuralları tamamen öğrenir ve test setindeki örneklerde hatasız tahmin eder. Bu bir veri sızıntısı (data leakage) değil, kural tabanlı etiketlemenin doğal sonucudur.

### 4.2 Overfitting Analizi (Train vs Test)

| Model | Train | Test | Fark | Durum |
|-------|-------|------|------|-------|
| XGBoost | 1.000 | 1.000 | 0.000 | OK |
| LightGBM | 0.974 | 0.958 | 0.016 | OK |
| RandomForest | 1.000 | 0.958 | 0.042 | OK |

Fark eşiği: 0.10 — üç model de aşmıyor.

### 4.3 5-Fold Çapraz Doğrulama (F1 Weighted)

| Model | Ortalama | Std Sapma |
|-------|----------|-----------|
| XGBoost | 0.990 | ±0.009 |
| LightGBM | 0.993 | ±0.003 |
| RandomForest | 0.966 | ±0.015 |

### 4.4 Üretilen Rapor Dosyaları

```
model_reports/
├── confusion_matrices.png      # Üç modelin karmaşıklık matrisleri (yan yana)
├── feature_importance.png      # XGBoost top-15 özellik önem grafiği
├── model_comparison.png        # Accuracy/F1/Precision/Recall karşılaştırma barları
└── model_validation_report.txt # Tüm metriklerin yazılı özet raporu
```

---

## 5. API Endpointleri

Tüm endpoint'ler `app.py` içinde tanımlıdır.

### GET /stats

Sistem özeti — sayfa yüklenince otomatik çağrılır.

```json
{
  "success": true,
  "total_influencers": 100,
  "avg_NFS": 30.57,
  "avg_BAS": 53.44,
  "categories": {"spor": 12, "moda": 10},
  "account_types": {"mikro": 42, "makro": 41, "mega": 17}
}
```

---

### GET /influencers?category=spor

Tüm fenomenleri BAS'a göre sıralı döner. İsteğe bağlı kategori filtresi.

```json
{
  "success": true,
  "count": 50,
  "influencers": [
    {
      "influencer_name": "@influencer42",
      "category": "spor",
      "account_type": "makro",
      "BAS": 50.15,
      "NFS": 65.49,
      "positive_ratio": 100.0,
      "risk_category": "DÜŞÜK"
    }
  ]
}
```

---

### POST /recommend

Ana öneri endpoint'i. Marka metni alır, sıralı fenomenleri döner.

**İstek:**
```json
{
  "brand_text": "Spor giyim ve ekipman alanında faaliyet gösteren bir markayız...",
  "top_n": 5
}
```

**Yanıt (özet):**
```json
{
  "success": true,
  "count": 5,
  "closest_campaign": "spor_kampanyasi",
  "brand_campaign_weights": {
    "spor_kampanyasi": 0.412,
    "moda_kampanyasi": 0.089
  },
  "recommendations": [
    {
      "influencer_name": "@influencer42",
      "final_score": 72.34,
      "campaign_bas": 58.21,
      "cfs": 68.45,
      "sfs": 81.23,
      "NFS": 65.49,
      "ml_label": "uygun",
      "risk_category": "DÜŞÜK"
    }
  ]
}
```

---

### GET /influencers/\<name\>/similar

K-Means kümeleme ile aynı gruptaki fenomenleri döner.

```json
{
  "success": true,
  "influencer_name": "@influencer42",
  "cluster_id": 2,
  "similar": [...]
}
```

---

### GET /campaigns

Her kampanya şablonunun detayları — ortalama benzerlik skorları ve en iyi fenomenler.

---

## 6. Frontend Mimarisi

Saf (framework-siz) HTML + JavaScript + CSS. React veya Vue kullanılmamıştır.

### 6.1 index.html Bölümleri

| Bölüm | ID / Sınıf | Açıklama |
|-------|-----------|----------|
| Header | `.header` | Logo + API durum göstergesi |
| Hero | `.hero` | Başlık, özellik hapları (BAS, CFS, ML, Duygu) |
| İstatistik paneli | `#stats-grid` | 4 stat kart (fenomen, NFS, BAS, kategori) |
| Form paneli | `#recommend-form` | Marka formu + 6 hızlı şablon butonu |
| Yükleme | `#loading-section` | Dönen halka animasyonu (istek süresince) |
| Affinity barları | `#affinity-section` | 6 kampanya ağırlık çubukları |
| Sonuç kartları | `#results-section` | Influencer kartları grid + CSV butonu |
| Benzer fenomenler | `#similar-section` | K-Means benzer listesi (isteğe bağlı) |
| Fenomen listesi | `.browse-panel` | Tüm fenomenler tablosu, kategori filtreli |

### 6.2 app.js — Temel Fonksiyonlar

```javascript
// Üç form alanını birleştirip tek brand_text üretir
function composeBrandText() { ... }

// Kampanya ağırlıklarını görsel çubuk olarak render eder
function renderAffinityBars(weights, closestCamp) { ... }

// Influencer kartlarını grid olarak render eder, CSV için saklar
function renderRecommendations(data) {
  _lastResults = data;   // CSV indirme için kaydedilir
  ...
}

// Skor bileşenlerini (Final, BAS, CFS, SFS, NFS, Pozitif) yatay bar olarak gösterir
function renderScoreBars(r, idx) { ... }

// BOM-prefixed CSV oluşturur ve tarayıcıya indirir
function downloadCSV(data) { ... }
```

### 6.3 Kategori Renk Sistemi

Her kategorinin kendine ait bir rengi vardır. Influencer kartlarının kenarlığı, avatar arka planı ve skor göstergesi bu renkten türetilir:

```javascript
const CAT_COLOR = {
  "spor"       : "#5eead4",   // teal
  "moda"       : "#f472b6",   // pink
  "teknoloji"  : "#38bdf8",   // sky blue
  "yemek"      : "#fb923c",   // orange
  "anne-bebek" : "#c084fc",   // purple
  "oyun"       : "#818cf8",   // indigo
  "saglik"     : "#4ade80",   // green
  "egitim"     : "#fbbf24",   // amber
  "lifestyle"  : "#f9a8d4",   // rose
  "seyahat"    : "#67e8f9",   // cyan
};
```

### 6.4 Hızlı Şablon Sistemi

Formda 6 adet hazır şablon butonu bulunur. Her butona tıklandığında `#field-sector`, `#field-audience` ve `#brand-text` alanları otomatik doldurulur:

```javascript
const TEMPLATES = {
  spor:      { sector: "Spor giyim ve ekipman", audience: "18-35 yaş...", vision: "..." },
  moda:      { ... },
  teknoloji: { ... },
  yemek:     { ... },
  annebebek: { ... },
  oyun:      { ... },
};
```

---

## 7. Kurulum ve Çalıştırma

### 7.1 Gereksinimler

- Python 3.10 veya üzeri
- Windows 10/11 (Linux ve macOS da desteklenir)
- En az 4 GB RAM (BERT modeli için)
- Yaklaşık 3 GB disk alanı (model dosyaları dahil)

### 7.2 İlk Kurulum

```bat
git clone <repo-url>
cd TezBitirme

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 7.3 Analiz Pipeline'ını Çalıştırma (Tek Seferlik)

```bat
.venv\Scripts\python analiz_pipeline.py
```

Bu script sırasıyla şunları yapar:
1. Excel/CSV veri dosyasını yükler ve temizler
2. NFS (Sayısal Performans Skoru) hesaplar
3. SBERT ile fenomen ve 6 kampanya embedding'lerini üretir
4. BERT duygu analizi yapar (yorum bazında)
5. Sahte takipçi risk skoru hesaplar
6. XGBoost modelini eğitir ve kaydeder
7. K-Means kümeleme yapar
8. Model doğrulama metriklerini hesaplar ve `model_reports/` klasörüne kaydeder
9. Tüm sonuçları `*.pkl` dosyalarına kaydeder

> **Süre:** İlk çalıştırmada 30–90 dakika (GPU yoksa CPU modunda)

### 7.4 Sunucuyu Başlatma

**Yöntem 1 — start.bat (önerilen, Windows):**
```bat
start.bat
```

`start.bat` şunları yapar:
1. `.venv` sanal ortamı yoksa oluşturur
2. Bağımlılıkları günceller
3. `waitress-serve` ile Flask'ı 4 thread ile başlatır (Windows üretim WSGI sunucusu)

**Yöntem 2 — Doğrudan Python:**
```bat
.venv\Scripts\python app.py
```

### 7.5 ÖNEMLİ — Tarayıcıyı Ne Zaman Açacaksınız?

Terminalde aşağıdaki satırı görene kadar tarayıcıyı açmayın:

```
* Running on http://0.0.0.0:5000
```
veya
```
Serving on http://0.0.0.0:5000
```

BERT ve XGBoost modellerinin yüklenmesi **30–60 saniye** alır. Bu satır görünmeden açılan tarayıcı "bağlanamıyor" hatası verir.

### 7.6 Tarayıcıda Açma

```
http://127.0.0.1:5000
```

> `localhost` yerine `127.0.0.1` kullanın. Windows'ta `localhost` bazen IPv6 adresine (`::1`) yönlendirilir; Flask varsayılan olarak yalnızca IPv4'te dinler. Bu durumda tarayıcı bağlanamaz ancak `127.0.0.1` doğrudan IPv4'e gider.

---

## 8. Docker ile Dağıtım

### 8.1 İmaj Oluşturma

```bash
docker build -t fenomen-marka-eslestirme:latest .
```

> İmaj boyutu yaklaşık 4 GB'tır. PyTorch (CPU-only) + transformers + sentence-transformers kütüphanelerinin büyüklüğünden kaynaklanır.

### 8.2 Çalıştırma

```bash
docker compose up -d
```

### 8.3 Durumu Kontrol Etme

```bash
docker compose ps
docker compose logs -f
```

### 8.4 Dockerfile Mantığı

```dockerfile
FROM python:3.11-slim

# libgomp: LightGBM ve XGBoost için OpenMP desteği
RUN apt-get install -y libgomp1 curl

# PyTorch'u CPU-only olarak yükle (GPU imajı 3x daha büyük olurdu)
RUN pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu

RUN pip install -r requirements.txt

# BERT modelini imaj içine indir — her container başlangıcında indirme olmasın
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY app.py influencer_features.py *.pkl frontend/ ./
EXPOSE 5000
HEALTHCHECK CMD curl -f http://localhost:5000/stats
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "app:app"]
```

---

## 9. CSV Dışa Aktarma

Öneriler sayfasındaki **"CSV İndir"** butonu şu sütunları içeren bir dosya oluşturur:

| Sütun | Açıklama |
|-------|----------|
| Fenomen | Kullanıcı adı |
| Kategori | İçerik kategorisi |
| Hesap Tipi | mikro / makro / mega |
| Ülke | Fenomenin ülkesi |
| Final Score | Nihai sıralama skoru |
| BAS | Marka uyum skoru |
| CFS | İşbirlikçi uyum skoru |
| SFS | Semantik uyum skoru |
| NFS | Sayısal performans skoru |
| Pozitif % | Pozitif yorum oranı |
| Sahte Risk | Sahte takipçi risk skoru |
| Risk Kategori | DÜŞÜK / ORTA / YÜKSEK |
| ML Etiket | uygun / orta / uygun_degil |
| Cinsiyet | Tahmini cinsiyet |
| Cluster | K-Means küme numarası |

Dosya sonuna marka metni, en yakın kampanya, BAS ve Final formülleri eklenir. Türkçe karakterlerin Excel'de doğru görünmesi için dosya **UTF-8 BOM** ile kaydedilir.

**Dosya adı formatı:** `fenomen_oneri_YYYY-MM-DD-HH-MM.csv`

---

## 10. Karşılaşılan Hatalar ve Çözümler

Bu bölüm geliştirme sürecinde karşılaşılan gerçek hataları ve çözümlerini belgeler.

---

### Hata 1 — `NameError: name 'nn' is not defined`

**Dosya:** `transformers/integrations/accelerate.py`

**Hata mesajı:**
```
NameError: name 'nn' is not defined
```

**Neden oluştu:**
`transformers` kütüphanesinin 4.50 ve üzeri sürümlerinde `torch.nn` modülü bir iç dosyaya doğru import edilmemektedir. Bu versiyon kaynaklı bir upstream bug olup pip ile en son sürüm yüklendiğinde otomatik ortaya çıkar.

**Çözüm:**
`requirements-prod.txt` dosyasında transformers sürümü üst sınırla sabitlendi:

```
# Önce (hatalı):
transformers>=4.35

# Sonra (düzeltilmiş):
transformers>=4.35,<4.50
```

---

### Hata 2 — `RuntimeError: Numpy is not available`

**Hata mesajı:**
```
RuntimeError: Numpy is not available
```

**Neden oluştu:**
`torch==2.2.2` (CPU-only sürüm) NumPy 2.x ile uyumsuz. pip en son sürümü (`numpy 2.4.6`) yüklediğinde PyTorch'un C uzantıları çöküyor; çünkü PyTorch 2.2.x API katmanı NumPy 1.x arayüzüne göre derlenmiş.

**Çözüm:**
NumPy sürümü `requirements-prod.txt`'te üst sınırla sabitlendi:

```
# Önce (hatalı):
numpy>=1.24

# Sonra (düzeltilmiş):
numpy>=1.24,<2.0
```

---

### Hata 3 — Docker Container Restart Döngüsü

**Belirti:**
```
$ docker compose ps
fenomen_marka_api   Restarting (3)
```

Container çalışmaya başlar, birkaç saniye içinde çöker ve yeniden başlar. Bu döngü süresiz devam eder.

**Neden oluştu:**
Docker imajı içinde NumPy 2.x ile PyTorch 2.2.2 yüklüydü (Hata 2 ile aynı uyumsuzluk). Geliştirme ortamında `requirements-prod.txt` düzeltilmişti ancak Docker imajı rebuild edilmemişti; eski katmanlar önbellekten (layer cache) kullanıldı.

**Çözüm:**
Önce `requirements-prod.txt` düzeltildi, ardından imaj önbelleksiz rebuild edildi:

```bash
docker build --no-cache -t fenomen-marka-eslestirme:latest .
docker compose up -d
```

---

### Hata 4 — `docker-compose.yml` Obsolete `version` Uyarısı

**Hata mesajı:**
```
WARN[0000] /path/docker-compose.yml: `version` is obsolete
```

**Neden oluştu:**
Docker Compose v2.x (Compose Specification standardı) artık `version` alanını desteklemiyor. Eski format olan `version: "3.9"` satırı modern Docker Compose sürümlerinde her çalıştırmada uyarı üretiyor.

**Çözüm:**
`docker-compose.yml` dosyasından `version` satırı kaldırıldı:

```yaml
# Önce (uyarı veren):
version: "3.9"
services:
  fenomen-marka-api:
    ...

# Sonra (düzeltilmiş):
services:
  fenomen-marka-api:
    ...
```

---

### Hata 5 — Flask `send_static_file` ile Index Sayfası 404 Hatası

**Hata mesajı:**
```
NotFound: 404 Not Found: ...
```

**Neden oluştu:**
Flask uygulamasında index sayfası başlangıçta şöyle servis ediliyordu:

```python
# Hatalı kod:
return app.send_static_file("../frontend/index.html")
```

`send_static_file` yalnızca `static_folder` içindeki dosyaları arar. `../frontend/index.html` yolu `static_folder` sınırını aştığından Flask dosyayı bulamıyordu.

**Çözüm:**
Flask'ın `template_folder` özelliği tanımlanarak `render_template` ile servis edildi:

```python
# app.py — Flask uygulama tanımı:
app = Flask(__name__,
            static_folder="frontend/static",
            template_folder="frontend")   # index.html buradan okunur

# Route:
@app.route("/")
def index():
    return render_template("index.html")  # artık çalışıyor
```

---

### Hata 6 — Tarayıcı API'ye Bağlanamıyor ("Kontrol ediliyor…" Kalıyor)

**Belirti:**
- Header'daki API durumu "Kontrol ediliyor…" yazısında sürekli kalıyor
- "Tüm Fenomenler" tablosu "Yükleniyor…" yazısından ilerlemiyor
- Stat kartları iskelet (yükleniyor) görünümünde kalıyor

**JavaScript akışı:**
Sayfa yüklendiğinde `init()` fonksiyonu çalışır:
```javascript
(async function init() {
  await checkApi();   // /stats endpoint'ini çeker
  await Promise.all([loadStats(), loadInfluencers()]);
})();
```
`checkApi()` tamamlanmadan `loadStats()` ve `loadInfluencers()` başlamaz. Eğer `fetch("/stats")` askıda kalırsa (ne başarı ne hata dönerse) tüm başlangıç süreci durur.

**Neden oluştu — Üç farklı senaryo:**

**Senaryo A — Eski process port'u tutuyor:**
Önceki oturumdan kalan `python.exe` process'i port 5000'i tutuyordu. `start.bat` ile başlatılan `waitress` aynı port'a bağlanamadı, hata vererek kapandı. Tarayıcı kırık durumda olan eski sunucuya erişmeye çalıştı.

**Senaryo B — `localhost` IPv6'ya yönleniyor:**
Windows'ta `localhost` hem `127.0.0.1` (IPv4) hem `::1` (IPv6) olarak tanımlıdır. Modern Edge ve Chrome tarayıcılar IPv6'yı öncelikli olarak dener. Flask'ın `0.0.0.0:5000` bağlaması yalnızca IPv4 arayüzlerini kapsar; IPv6 adresini kapsamaz. Tarayıcı `::1:5000`'e bağlanmaya çalışır, bağlantı reddedilir.

**Senaryo C — Tarayıcı çok erken açıldı:**
BERT (sentence-transformers) ve XGBoost modellerinin yüklenmesi 30–60 saniye alır. Sunucu bu sürede `LISTENING` durumuna geçemez. Bu süre dolmadan açılan tarayıcı "Bağlantı reddedildi" hatası alır. JavaScript hiç çalışmaz, "Kontrol ediliyor…" metni statik HTML'de kaldığı için görünmeye devam eder.

**Çözüm:**

1. Eski process temizlendi:
```powershell
Stop-Process -Id <PID> -Force
```

2. Sunucu yeniden başlatılıp hazır olana kadar beklendi:
```bash
until curl -s http://127.0.0.1:5000/stats > /dev/null; do sleep 3; done
echo "Sunucu hazir"
```

3. Tarayıcıda `localhost` yerine `127.0.0.1` kullanıldı:
```
http://127.0.0.1:5000
```

**Önleyici kural:** `start.bat` terminalde `Serving on http://0.0.0.0:5000` satırını gösterene kadar tarayıcıyı açmayın.

---

### Hata 7 — PowerShell'de Python Kodu Çalıştırırken SyntaxError

**Hata mesajı:**
```
SyntaxError: f-string: expecting '}'
```

**Neden oluştu:**
Model doğrulama için PowerShell'de `-c` parametresiyle Python kodu çalıştırılmak istendiğinde f-string içindeki çift tırnaklar PowerShell'in kendi dize ayrıştırması ile çakıştı:

```powershell
# Çalışmayan:
python -c "print(f'Sonuc: {variable}')"
# PowerShell burada kendi tırnak kurallarıyla çakışır
```

**Çözüm:**
Doğrudan PowerShell üzerinden Python kodu çalıştırmak yerine, tüm doğrulama kodu ayrı bir `.py` dosyasına taşındı:

```powershell
# Düzeltilmiş:
python _validate_models.py
```

Bu yaklaşım aynı zamanda doğrulama kodunun bağımsız ve tekrar çalıştırılabilir bir script olarak kalıcı hale gelmesini sağladı.

---

## Teknik Notlar

### Veri Seti Hakkında

Bu projede kullanılan fenomen verileri **sentetik olarak üretilmiştir**. Gerçek kişilerin sosyal medya verileri kullanılmamıştır. Veriler, gerçek influencer dağılımlarını temsil edecek şekilde oluşturulmuş olup yalnızca akademik araştırma amaçlıdır.

### Model Güncelleme

Yeni veri eklendiğinde `analiz_pipeline.py` yeniden çalıştırılmalıdır. `app.py` başlangıçta pkl dosyalarını yükler; pipeline yeniden çalışmadan API güncellenmiş veriyi görmez.

### Üretim Ortamı Notları

- `debug=False` ile çalıştırın (uygulama zaten bu şekilde yapılandırılmış)
- Windows için `waitress`, Linux ve Docker için `gunicorn` kullanın
- SBERT modeli başlangıçta bir kez yüklenir, sonraki isteklerde bellekten kullanılır
- `/recommend` endpoint'i marka embedding'ini her istekte hesaplar (yaklaşık 0.1–0.3 sn ek süre)
- Tek worker ile başlatın — model büyük RAM kullanır, birden fazla worker bellek sorununa yol açabilir

---

*TÜBİTAK 2209-A — Yapay Zekâ Destekli Fenomen–Marka Eşleştirme Sistemi*
