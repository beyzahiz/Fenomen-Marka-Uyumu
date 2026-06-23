# Yapay Zekâ Destekli Fenomen–Marka Eşleştirme Uygulaması

**TÜBİTAK 2209-A Üniversite Öğrencileri Araştırma Projeleri Destekleme Programı**

**İstanbul Sağlık ve Teknoloji Üniversitesi — Mühendislik ve Doğa Bilimleri Fakültesi — Yazılım Mühendisliği Bölümü Lisans Bitirme Projesi**

> Bir markanın serbest metin olarak girdiği kampanya açıklamasını alıp; **anlamsal benzerlik, sayısal performans, kampanya/kitle uyumu, anahtar kelime eşleşmesi, duygu analizi ve sahte takipçi riskini** tek bir hibrit skorlama mimarisinde birleştirerek 135 kişilik doğrulanmış Instagram fenomeni veri tabanından markaya en uygun içerik üreticilerini sıralayan, açıklanabilir (XAI) bir karar destek sistemi.

**Proje Ekibi:** Beyza Hız ·  Zeynep Ece Kutlu · Zeynep Yıldırım<br>
**Proje Danışmanı:** Dr. Öğr. Üyesi Mehmet Kurt

---

## İçindekiler

1. [Proje Özeti](#1-proje-özeti)
2. [Problem Tanımı ve Motivasyon](#2-problem-tanımı-ve-motivasyon)
3. [Sistem Mimarisi](#3-sistem-mimarisi)
4. [Veri Seti](#4-veri-seti)
5. [Skorlama Bileşenleri ve Formüller](#5-skorlama-bileşenleri-ve-formüller)
6. [Sahte Takipçi Risk Skoru](#6-sahte-takipçi-risk-skoru)
7. [Makine Öğrenmesi Pipeline'ı](#7-makine-öğrenmesi-pipelineı)
8. [Model Performans Sonuçları](#8-model-performans-sonuçları)
9. [Benzer Fenomen Sistemi (CF + K-Means)](#9-benzer-fenomen-sistemi-cf--k-means)
10. [Backend ve API Katmanı](#10-backend-ve-api-katmanı)
11. [Frontend Mimarisi](#11-frontend-mimarisi)
12. [Proje Dosya Yapısı](#12-proje-dosya-yapısı)
13. [Docker ile Dağıtım](#14-docker-ile-dağıtım)
14. [Test Süreci](#15-test-süreci)
15. [Veri Dışa Aktarma](#16-veri-dışa-aktarma)
16. [Kullanılan Teknolojiler](#17-kullanılan-teknolojiler)
17. [Sınırlılıklar](#18-sınırlılıklar)
18. [Akademik ve Etik Bilgilendirme](#20-akademik-ve-etik-bilgilendirme)

---

## 1. Proje Özeti

Dijital pazarlama sektöründe marka–fenomen eşleştirmesi günümüzde büyük ölçüde takipçi sayısı, beğeni sayısı gibi yüzeysel metriklere ve öznel deneyime dayanmaktadır. Bu proje, aşağıdaki temel araştırma sorusuna yanıt aramak amacıyla geliştirilmiştir:

> **"Bir fenomenin içerik dili, etkileşim kalitesi ve hedef kitle özellikleri, bir markanın kampanya başarısını öngörmede ne derece etkili olabilir?"**

Bu doğrultuda, Meta Geliştirici Platformu üzerinden resmi başvuru ile elde edilen **135 doğrulanmış Instagram fenomenine** ait kamuya açık veriler (profil, gönderi metni, etkileşim, hashtag) toplanmış; bu veriler **doğal dil işleme (NLP)** ve **makine öğrenmesi** teknikleriyle işlenerek uçtan uca çalışan bir karar destek sistemi geliştirilmiştir. Sistem, kullanıcının girdiği marka/kampanya metnini en uygun kampanya kategorisine eşler, fenomenleri çok bileşenli bir hibrit skorla sıralar ve her öneri için **"neden önerildi?"** açıklamasını React tabanlı arayüz üzerinden şeffaf biçimde sunar.

---

## 2. Problem Tanımı ve Motivasyon

- Küresel influencer pazarlama pazarı 2024 sonunda **24 milyar dolar**a, 2025 sonunda tahminen **32,5 milyar dolar**a ulaşmıştır; Türkiye'de bu hacim 2024'te **6,75 milyar TL**'dir.
- Markalar reklam bütçelerinin **%40'ından fazlasını** sosyal medya fenomenleriyle yapılan kampanyalara ayırmaktadır.
- Literatür incelemesi, mevcut fenomen seçim araçlarının büyük ölçüde **anahtar kelime arama + takipçi sayısı + genel etkileşim oranı** gibi yüzeysel ve içerik tabanlı filtrelemeyle sınırlı kaldığını; geçmiş kampanya/işbirlikçi verileri, anlamsal uyum ve sahte etkileşim riskini büyük ölçüde göz ardı ettiğini göstermektedir.
- Yanlış fenomen seçimi; itibar kaybı, düşük dönüşüm oranı ve düşük Yatırım Getirisi (ROI) gibi somut zararlara yol açmaktadır.

Bu çalışma, **Kaynak Güvenilirliği Modeli** (Ohanian, 1990) ve **Anlam Transferi Modeli** (McCracken, 1989) gibi pazarlama iletişimi kuramlarını teknik bir karar destek sistemine dönüştürerek; içerik tabanlı filtreleme ile işbirlikçi filtrelemeyi (collaborative filtering) birleştiren hibrit bir yaklaşım önermektedir.

---

## 3. Sistem Mimarisi

```
                ┌─────────────────────────────┐
                │   React + Vite Frontend      │
                │ (Kampanya formu, skor        │
                │  kartları, grafikler, AI     │
                │  gerekçelendirme paneli)     │
                └───────────────┬─────────────┘
                                │ Axios (JSON / REST)
                                ▼
                ┌─────────────────────────────┐
                │     Flask REST API (app.py)  │
                │  /recommend  /stats          │
                │  /campaigns  /influencers    │
                │  /influencers/<name>/similar │
                └───────────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────────┐    ┌──────────────────┐
│  NLP Katmanı   │     │  Skorlama Motoru   │    │  ML Karar Modeli  │
│ SBERT (SFS)    │     │ NFS · CFS · KFS    │    │ XGBoost (ml_label)│
│ TF-IDF (KFS)   │     │ BAS · Final Score  │    │ uygun/orta/       │
│ Turkish BERT   │     │ Risk Penalty       │    │ uygun_degil       │
│ (Duygu Analizi)│     │                     │    │                   │
└───────────────┘     └───────────────────┘    └──────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                ┌─────────────────────────────┐
                │  MongoDB  (birincil depo)     │
                │  + .pkl Checkpoint (fallback) │
                │  best_model_xgb.pkl           │
                │  cf_similarity_matrix.pkl     │
                │  influencer_summary_*.pkl     │
                └─────────────────────────────┘
```

**Akış mantığı:** `analiz_pipeline.py` veri setini bir kez işler, SBERT/TF-IDF/duygu özniteliklerini çıkarır, XGBoost modelini eğitir, K-Means kümelemesini ve 135×135 işbirlikçi benzerlik matrisini hesaplar ve tüm çıktıları `.pkl` dosyalarına ile MongoDB'ye yazar. `app.py` başlangıçta bu çıktıları belleğe yükler; her `/recommend` isteğinde yalnızca marka metninin embedding'i ve skor birleştirmesi anlık olarak hesaplanır (~0.1–0.3 sn). MongoDB bağlantısı kesilirse sistem otomatik olarak `.pkl` checkpoint'lerinden çalışmaya devam eder.

---

## 4. Veri Seti

| Özellik | Değer |
|---|---|
| Veri kaynağı | Meta Geliştirici Platformu (resmi API başvurusu ile) |
| Platform | Instagram |
| Fenomen sayısı | **135** doğrulanmış hesap |
| Kampanya kategorisi sayısı | **6** (spor, moda, teknoloji, yemek, anne-bebek, oyun) |
| Model satırı (fenomen × kampanya) | **810** |
| Eğitim / Test ayrımı | 648 / 162 (%80 / %20) |
| Fenomen başına örneklenen gönderi | En fazla 30 gönderi metni |
| Toplanan alanlar | Profil bilgisi, biyografi, hashtag, gönderi metni, beğeni/yorum sayısı, takipçi sayısı/geçmişi |

**Etik ve hukuki çerçeve:** Veri toplama sürecinde yalnızca kamuya açık içerik ve metrikler kullanılmıştır. Doğrudan mesaj (DM), özel hikâye veya gizli hesap paylaşımı gibi kişisel veri niteliği taşıyan hiçbir alan toplanmamıştır. Veriler veri tabanına işlenmeden önce **KVKK** ve uluslararası veri koruma ilkelerine uygun şekilde anonimleştirilmiş; kullanıcı adları ve kişisel tanımlayıcılar maskelenmiştir. Geliştirme sürecinin Meta başvuru onayı öncesindeki ilk aşamalarında, model mimarisinin test edilmesi amacıyla sentetik profiller de kullanılmıştır.

---

## 5. Skorlama Bileşenleri ve Formüller

Sistem; **kelime düzeyinde**, **anlam düzeyinde**, **sayısal düzeyde**, **kampanya düzeyinde** ve **duygu düzeyinde** olmak üzere beş farklı katmanı birleştiren çok bileşenli bir skorlama mimarisi kullanır. Hiçbir bileşen tek başına karar verici değildir.

### 5.1 NFS — Sayısal Uyum Skoru (Numerical Fit Score)

Fenomenin sayısal performansını; etkileşim gücü, takipçi büyümesi ve yayın sıklığı üzerinden 0–100 aralığında ölçer.

```
ER  (Etkileşim Oranı)     = (Toplam Beğeni + Toplam Yorum) / Toplam Takipçi × 100
FGR (Takipçi Artış Oranı) = (Dönem Sonu Takipçi − Dönem Başı Takipçi) / Dönem Başı Takipçi × 100
Paylaşım Sıklığı          = Toplam Gönderi Sayısı / Zaman Dönemi

NFS = Σ wᵢ × özellik_i (normalize edilmiş) → 0–100 aralığına ölçeklenir
```

### 5.2 SFS — Semantik Uyum Skoru (Semantic Fit Score)

Marka metni ile fenomenin biyografi/gönderi/hashtag metni arasındaki **SBERT** tabanlı anlamsal benzerlik.

```
SFS = cosine_similarity( SBERT(marka_metni), SBERT(fenomen_metni) ) × 100
```

- **Model:** `paraphrase-multilingual-MiniLM-L12-v2` (Sentence-BERT, çok dilli, 512 boyutlu yoğun vektör uzayı)
- Fenomen embedding'leri pipeline aşamasında önceden hesaplanır; marka embedding'i her istekte anlık hesaplanır.
- "Moda", "kombin", "stil", "giyim" gibi farklı ama anlamca yakın ifadeleri klasik anahtar kelime eşleştirmesinin ötesinde yakalar.

### 5.3 KFS — Anahtar Kelime Uyum Skoru (Keyword Frequency Score)

SBERT'in açıklanabilirliğini desteklemek amacıyla eklenen **TF-IDF tabanlı** istatistiksel destek katmanı.

```
tf(t,d)   = f(t) / n
idf(t)    = log( |D| / |{d : t ∈ d}| )
tfidf(t,d)= tf(t,d) × idf(t)

KFS = cosine_similarity( TFIDF(kampanya_metni), TFIDF(fenomen_metni) ) × 100
```

KFS, ana karar mekanizması değildir; SBERT'in ürettiği anlamsal skoru kelime düzeyinde doğrulayan, açıklanabilir bir yardımcı sinyaldir.

### 5.4 CFS — Kampanya Uyum Skoru (Campaign Fit Score)

Fenomenin, markanın hedeflediği kampanya türüne (spor, moda, teknoloji, yemek, anne-bebek, oyun) ne kadar uygun olduğunu işbirlikçi bir mantıkla ölçer.

```
raw[k]    = cosine_sim( marka_embedding, kampanya_embedding[k] )
weight[k] = softmax( raw[k] × T )                     # T = sıcaklık parametresi
CFS       = Σ weight[k] × sim_kampanya[k] × 100
```

CFS'nin mantığı: marka metni hangi kampanya tipine ne kadar yakınsa (softmax ağırlıklar), o kampanya türünde güçlü performans gösteren fenomenlere daha fazla ağırlık verilir — "benzer markaların tercih ettiği fenomenleri öner" prensibinin matematiksel karşılığıdır.

### 5.5 Duygu Analizi (Sentiment)

```python
from transformers import pipeline
sentiment = pipeline("sentiment-analysis", model="savasy/bert-base-turkish-sentiment-cased")
```

- Türkçenin sondan eklemeli yapısına uygun **Turkish BERT** modeli kullanılır.
- Fenomen başına en fazla 30 gönderi metni örneklenir; her gönderi pozitif/negatif olarak sınıflandırılır.
- Türetilen öznitelikler: `positive_ratio`, `negative_ratio`, `avg_sentiment_score`, `avg_signed_sentiment` (final skor hesaplamasında normalize edilerek kullanılır).

### 5.6 BAS — Marka Uyum Skoru (Brand Alignment Score)

Belirli bir kampanya seçimi olmaksızın, fenomenin **genel** marka uyumunu ölçen kampanyadan bağımsız temel skor.

```
BAS = SFS × 0.35 + NFS × 0.30 + Sentiment_norm × 0.25 + (100 − FakeRisk) × 0.10
```

### 5.7 Final Score — Çok Katmanlı Hibrit Nihai Skor

Sistemin en özgün yönü, tek bir modelin veya tek bir skorun tahminine bağımlı kalmamasıdır. Altı bağımsız bileşeni birleştiren ağırlıklı bir mimari kullanılır:

```
Final Score = SFS × 0.35
            + NFS × 0.25
            + CFS × 0.15
            + KFS × 0.15
            + Sentiment_norm × 0.10
            − RiskPenalty
```

| Bileşen | Ağırlık | Ölçtüğü Sinyal |
|---|---|---|
| SFS | %35 | Sentence-BERT tabanlı derin anlamsal yakınlık |
| NFS | %25 | Etkileşim oranı, büyüme ve paylaşım kalitesi |
| CFS | %15 | Kampanya / kitle uyum oranı |
| KFS | %15 | Kelime frekansı tabanlı istatistiksel destek |
| Sentiment | %10 | Turkish BERT pozitif kitle duygu tonu |
| RiskPenalty | dinamik | Sahte takipçi tespiti durumunda uygulanan ceza puanı |

Ayrıca sıralama motorunda **kampanya–kategori alaka kontrolü** uygulanır: anlamsal skoru yüksek olsa da kampanya kategorisiyle örtüşmeyen fenomenlerin üst sıralara çıkması sınırlandırılır (örn. moda kampanyasında sadece ortak kelime nedeniyle öne çıkan bir spor hesabı cezalandırılır). Yeterli sayıda öneri üretilemediğinde bu filtre esnetilir.

---

## 6. Sahte Takipçi Risk Skoru

Risk skoru üç ağırlıklı sinyalin birleşiminden oluşur ve 0–100 aralığında üretilir:

| Sinyal | Ağırlık | Mantık |
|---|---|---|
| Etkileşim Anomalisi | %50 | ER < %0.5 → 85 risk puanı (pasif/satın alınmış takipçi şüphesi); ER > %10 → 60 risk puanı (bot beğenisi şüphesi); %1–%5 aralığı normal kabul edilir |
| Büyüme Tutarsızlığı | %30 | Takipçi Büyüme Oranı (FGR) bazlı ani/doğrusal olmayan sıçramaların tespiti |
| Erişim/Takipçi Oranı | %20 | Reach ile takipçi sayısı arasındaki orantısızlığın kontrolü |

**Risk kategorileri:** `≥70` → **YÜKSEK** · `≥50` → **ORTA** · `≤30` → **DÜŞÜK**

Bu skor, BAS ve Final Score hesaplamalarına `(100 − FakeRisk)` terimi olarak dahil edilerek sahte takipçi riski yüksek hesapların öneri sıralamasında otomatik olarak geri plana atılması sağlanır.

---

## 7. Makine Öğrenmesi Pipeline'ı

### 7.1 Etiket Üretimi

Model eğitimi için uygunluk etiketleri kural tabanlı olarak üretilmiştir (her fenomen × 6 kampanya kombinasyonu için, toplam 810 örnek):

```python
if sfs > eşik_yüksek and nfs > eşik_orta and positive_ratio > eşik_pozitif:
    label = "uygun"
elif sfs < eşik_düşük or nfs < eşik_alt or positive_ratio < eşik_alt:
    label = "uygun_degil"
else:
    label = "orta"
```

### 7.2 Özellik Mühendisliği

- Sayısal değişkenler (ER, FGR, paylaşım sıklığı) **StandardScaler (Z-score)** ile normalize edilmiştir — yalnızca mesafeye duyarlı Logistic Regression için; ağaç tabanlı modeller (XGBoost, LightGBM, Random Forest) normalizasyona ihtiyaç duymaz.
- Kategorik değişkenler one-hot encoding ile dönüştürülmüştür.
- Pearson ve Spearman korelasyon analizleriyle modele anlamlı katkı sağlamayan değişkenler elenmiştir.
- Sınıf dengesizliğini azaltmak amacıyla **SMOTE** uygulanmıştır.
- Veri sızıntısını (leakage) önlemek için encoding ve örnekleme adımları `Pipeline` nesnesi içinde, çapraz doğrulama döngüsünden önce değil **döngünün içinde** uygulanmıştır.

### 7.3 Karşılaştırılan Modeller

| Model | Rol |
|---|---|
| **XGBoost** | Ana karar destek modeli — ikinci derece türev bilgisiyle optimize edilen gradyan artırma algoritması |
| LightGBM | Karşılaştırma modeli — yüksek hız, düşük bellek kullanımı |
| Random Forest | Referans sınıflandırıcı — topluluk öğrenmesiyle overfitting kontrolü |
| Logistic Regression | Klasik istatistiksel temel çizgi (baseline) modeli |
| Voting Classifier (LR+RF+LightGBM) | Deneysel karşılaştırma amaçlı topluluk modeli |
| Linear/RF/XGBoost Regressor | Deneysel: fenomenin beklenen etkileşim oranını tahmin eden ek regresyon modelleri |

### 7.4 XGBoost'un Seçilme Gerekçesi

XGBoost; tablosal verilerde yüksek performans, hızlı çıkarım ve `ml_label` (`uygun` / `orta` / `uygun_degil`) üzerinden **açıklanabilir** bir sınıflandırma sunması nedeniyle ana model olarak seçilmiştir. Ancak XGBoost **hiçbir zaman tek başına karar verici olarak konumlandırılmamıştır**: veri setindeki fenomen sayısının sınırlı olması ve etiketlerin kural tabanlı üretilmiş olması, modelin yalnızca bu kuralları ezberleme riskini taşımasına yol açmaktadır. Bu nedenle XGBoost çıktısı, sistemde nihai sıralamayı belirleyen **tek bir karar sinyali** olarak değil, SFS/NFS/CFS/KFS/Sentiment/Risk skorlarıyla birlikte değerlendirilen **bir bileşen** olarak kullanılır.

---

## 8. Model Performans Sonuçları

### 8.1 5-Fold Çapraz Doğrulama (F1 Weighted)

| Model | Fold-1 | Fold-2 | Fold-3 | Fold-4 | Fold-5 | Ortalama F1 | Std. Sapma |
|---|---|---|---|---|---|---|---|
| **XGBoost** | 1.000 | 1.000 | 1.000 | 0.993 | 1.000 | **0.999** | 0.003 |
| LightGBM | 1.000 | 1.000 | 1.000 | 0.993 | 0.994 | 0.997 | 0.003 |
| Random Forest | 1.000 | 1.000 | 1.000 | 0.985 | 0.989 | 0.995 | 0.007 |
| Logistic Regression | 0.985 | 0.977 | 0.961 | 0.971 | 0.960 | 0.971 | 0.010 |

### 8.2 Overfitting Analizi

XGBoost modelinin eğitim/test doğrulukları arasındaki fark yalnızca **−0.002** seviyesinde kalmıştır; bu da modelin aşırı öğrenme açısından kontrollü bir sınırda olduğunu göstermektedir. Bununla birlikte, **yüksek doğruluk değerleri yalnızca model başarısı olarak yorumlanmamıştır**: etiketlerin kural tabanlı üretilmiş olması, ağaç tabanlı modellerin bu yapıyı kolayca öğrenebilmesine ve dolayısıyla yapay olarak yüksek skorlar üretmesine yol açabilmektedir. Bu nedenle model çıktıları; overfitting analizi, çapraz doğrulama, sınıf bazlı performans ve **manuel/nitel değerlendirme** (gerçek hesapların kampanya geçmişiyle karşılaştırılması) ile birlikte yorumlanmıştır.

### 8.3 Manuel / Nitel Değerlendirme

Öneri listelerindeki fenomen hesapları; kampanya metniyle anlamsal bağ kurup kurmadığı, içerik kategorisinin kampanya ile uyumu ve geçmişte ilgili alanda reklam/işbirliği içeriği üretip üretmediği açısından nitel olarak incelenmiş ve sistem bu bulgular doğrultusunda iyileştirilmiştir.

---

## 9. Benzer Fenomen Sistemi (CF + K-Means)

Bir fenomen için "benzer fenomenler" listesi, **hibrit bir yaklaşımla** üretilir:

1. **Birincil yöntem — Item-based Collaborative Filtering:** Fenomenler arası davranışsal profil benzerliği (etkileşim, büyüme, paylaşım sıklığı), önceden hesaplanmış **135×135 boyutlu fenomen-fenomen benzerlik matrisi** (`cf_similarity_matrix.pkl`) üzerinden değerlendirilir.
2. **Yedek yöntem (fallback) — K-Means Kümeleme:** CF matrisi yetersiz sonuç ürettiğinde, sayısal performans ve etkileşim değişkenleri üzerinden oluşturulmuş **K-Means kümeleri** devreye girer.

K-Means sonucunda fenomenler 4 ana kümeye ayrılmıştır:

| Küme | Tanım | Hesap Sayısı |
|---|---|---|
| Küme 0 | Düşük etkileşimli genel profiller | 42 |
| Küme 1 | Orta düzeyde istikrarlı profiller | 35 |
| Küme 2 | Yüksek etkileşimli niş üreticiler | 39 |
| Küme 3 | Çok yüksek büyüme oranına sahip öncüler | 19 |

`GET /influencers/<name>/similar` uç noktası bu hibrit benzerlik mekanizmasını kullanarak seçilen fenomene en yakın alternatifleri döner.

---

## 10. Backend ve API Katmanı

- **Framework:** Flask (REST API, JSON tabanlı istek/yanıt döngüsü)
- **Veri katmanı:** MongoDB (birincil) + `.pkl` checkpoint dosyaları (fallback) — MongoDB bağlantısı olmadığında sistem otomatik olarak checkpoint'lerden çalışmaya devam eder
- **Bellek optimizasyonu:** SBERT ve XGBoost modelleri uygulama başlangıcında **bir kez** belleğe yüklenir; her istek için yeniden eğitim veya yeniden yükleme yapılmaz

### Uç Noktalar

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/recommend` | POST | Marka/kampanya metnini alır; SFS, NFS, CFS, KFS, duygu ve risk skorlarını birleştirerek sıralı fenomen önerisi döner |
| `/stats` | GET | Toplam fenomen sayısı, ortalama skorlar, kategori dağılımı gibi genel istatistikleri döner |
| `/campaigns` | GET | Sistemde tanımlı 6 kampanya şablonu ve ağırlıklarını döner |
| `/influencers` | GET | Tüm fenomenleri (isteğe bağlı kategori filtresiyle) skor sırasına göre listeler |
| `/influencers/<name>/similar` | GET | CF + K-Means hibrit yaklaşımıyla benzer fenomenleri döner |

**Örnek `/recommend` isteği:**

```json
{
  "brand_text": "Spor giyim ve ekipman alanında faaliyet gösteren, 18-35 yaş aralığını hedefleyen bir markayız...",
  "top_n": 5
}
```

**Örnek yanıt (özet):**

```json
{
  "success": true,
  "closest_campaign": "spor_kampanyasi",
  "recommendations": [
    {
      "influencer_name": "@fenomen_42",
      "final_score": 78.4,
      "sfs": 81.2, "nfs": 65.5, "cfs": 68.4, "kfs": 54.1,
      "sentiment_score": 72.0,
      "ml_label": "uygun",
      "risk_category": "DÜŞÜK"
    }
  ]
}
```

---

## 11. Frontend Mimarisi

- **Teknoloji:** React + Vite + Tailwind CSS, Axios ile Flask API'sine bağlanır
- **React seçilme gerekçesi:** bileşen tabanlı yapının hızlı geliştirme imkânı sunması, Vite ile yüksek performanslı derleme ve dinamik arayüzler için yaygın kabul görmesi

### Temel Arayüz Bileşenleri

| Bölüm | Açıklama |
|---|---|
| Sistem Metrikleri Paneli | Kullanıcı girdi yapmadan önce gösterilen genel istatistikler (fenomen sayısı, ortalama NFS vb.) |
| Kampanya Formu | Marka/kampanya metninin girildiği, hedef kitle ve ürün bilgisinin tanımlandığı alan |
| Kampanya Uyum Panelleri | Girilen metnin 6 kampanya türüne olan softmax ağırlıklarını gösteren bar/grafik bileşenleri |
| Skor Kartları | Her fenomen için Final Score, BAS, SFS, NFS, CFS, KFS ve duygu oranını yatay bar grafikleriyle gösteren kartlar |
| AI Gerekçelendirme Paneli | XGBoost'un ürettiği `ml_label` çıktısını "Neden Önerildi?" başlığıyla kullanıcıya açıklayan bileşen |
| Benzer Fenomenler Paneli | CF + K-Means hibrit yaklaşımıyla üretilen alternatif öneriler |

---

## 12. Proje Dosya Yapısı

```
FenomenMarkaUyumu/
│
├── app.py                          # Flask REST API — tüm endpoint'ler
├── .dockerignore
├── .gitignore
│
├── data/                           # Ham veri (CSV)
│   ├── influencer_posts.csv
│   ├── influencer_profiles.csv
│   └── sentiment_cache.csv
│
├── db/                             # MongoDB bağlantı katmanı
│   ├── __init__.py
│   ├── mongo_client.py
│   └── mongo_sync.py
│
├── docs/                           # Dokümantasyon, QA raporları, görseller
│   ├── model_reports/
│   ├── qa_validation_report.md
│   ├── full_test_ui_pass.png
│   ├── ranking_ui_verification.png
│   └── Tablolar.md / Tablolar.html
│
├── notebooks/                      # Akademik/keşifsel analiz ortamı
│   ├── bitirme_projesi_jpynb.ipynb # Ana analiz ve modelleme notebook'u
│   ├── elbow_method.png
│   ├── grafik1_kategori_dagilimi.png ... grafik10_top5_oneriler.png
│   ├── influencer_analysis_results_v2.xlsx
│   ├── influencer_summary_checkpoint.pkl
│   ├── best_model_xgb.pkl / label_encoder.pkl / feature_columns.pkl
│   └── model_karsilastirma*.png
│
├── pipeline/                        # Üretim skorlama / pipeline modülleri
│   ├── analiz_pipeline.py          # Tek seferlik uçtan uca analiz pipeline'ı
│   ├── build_cf_matrix.py          # 135×135 işbirlikçi benzerlik matrisi üretimi
│   ├── category_seeds.py / category_utils.py
│   ├── comment_processor.py        # Yorum/duygu ön işleme
│   ├── fix_categories.py
│   ├── influencer_features.py      # Özellik mühendisliği yardımcıları
│   ├── nfs_scoring.py              # NFS hesaplama modülü
│   ├── nfs_ridge_model.pkl / nfs_feature_scaler.pkl / nfs_label_scaler.pkl
│   ├── cf_similarity_matrix.pkl
│   ├── influencer_summary_checkpoint.pkl
│   ├── _validate_models.py         # Bağımsız model doğrulama scripti
│   └── scripts/                    # Rapor/grafik üretim ve bakım scriptleri
│       ├── generate_charts.py
│       ├── generate_report3.py / generate_report3b.py
│       ├── refresh_nfs_checkpoint.py
│       ├── run_notebook_cells.py
│       └── run_qa_suite.py
│
└── frontend-react/                  # React + Vite kullanıcı arayüzü
    ├── src/
    ├── index.html
    ├── package.json / package-lock.json
    ├── vite.config.js
    ├── Dockerfile / nginx.conf
    └── dist/                        # Üretim build çıktısı
```

---


## 13. Docker ile Dağıtım

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

- `frontend-react/Dockerfile` + `nginx.conf` ile statik build Nginx üzerinden servis edilir.
- Backend imajı PyTorch (CPU-only), `transformers` ve `sentence-transformers` bağımlılıklarını içerir; SBERT ve Turkish BERT modelleri imaj build aşamasında önceden indirilerek container başlatma süresi kısaltılır.
- Tek worker ile çalıştırılması önerilir — büyük model belleği nedeniyle birden fazla worker bellek sorununa yol açabilir.

---

## 14. Test Süreci

| Test Kategorisi | Test Edilen Boyut | Beklenen Sonuç | Sonuç |
|---|---|---|---|
| Birim Testleri | Veri ön işleme, hard override, tier katsayısı, skor normalizasyonu | Fonksiyonların doğru çalışması | ✅ Başarılı |
| Entegrasyon Testleri | Flask API, MongoDB, model yükleme, JSON sözleşmesi | Servislerin birlikte hatasız çalışması | ✅ Başarılı |
| Algoritmik Doğrulama | Farklı kampanya sorguları (moda/teknoloji vb.) | Kategori sızıntısı (semantic leakage) olmaması | ✅ Başarılı |
| Sınır Durum Testleri | Boş, geçersiz, aşırı uzun kampanya metinleri | Kontrollü hata / güvenli yanıt | ✅ Başarılı (400 yanıtları doğrulandı) |
| Yük ve Latency Testleri | Ardışık ve eşzamanlı API istekleri | Zaman aşımı olmadan yanıt | ✅ 10/10 ve 50/50 eşzamanlı istek başarılı |

---

## 15. Veri Dışa Aktarma

Arayüzdeki **CSV/Excel İndir** özelliği aşağıdaki bilgileri içeren bir çıktı üretir:

- Fenomen adı, kategori, hesap tipi, ülke
- Final Score, BAS, SFS, NFS, CFS, KFS
- Pozitif/negatif duygu oranı
- Sahte takipçi risk skoru ve risk kategorisi
- ML uygunluk etiketi (`uygun` / `orta` / `uygun_degil`)
- K-Means küme numarası, tahmini demografik bilgi

Notebook tarafında ek olarak **5 sayfalı bir Excel raporu** (`influencer_analysis_results_v2.xlsx`) üretilmektedir: Tüm Fenomenler, Top-20 Fenomen, Risk Analizi, Kategori Özeti, Kampanya Bazlı Top-5 Öneriler. Türkçe karakter uyumu için CSV çıktıları **UTF-8 BOM** ile kaydedilir.

---

## 16. Kullanılan Teknolojiler

| Bileşen | Teknoloji | Görev |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS | Etkileşimli kullanıcı paneli |
| Backend | Flask + REST API + Axios | İş mantığı yönetimi ve API |
| Anlamsal Analiz | Sentence-BERT — `paraphrase-multilingual-MiniLM-L12-v2` | SFS hesaplama |
| Anahtar Kelime Analizi | TF-IDF + Cosine Similarity | KFS hesaplama |
| Duygu Analizi | Turkish BERT — `savasy/bert-base-turkish-sentiment-cased` | Pozitif/negatif duygu sınıflandırması |
| Sınıflandırma | XGBoost (LightGBM, Random Forest, Logistic Regression karşılaştırmalı) | `ml_label` uygunluk etiketi |
| Kümeleme | K-Means | Benzer fenomen yedek mekanizması |
| Benzerlik | Item-based Collaborative Filtering (135×135 matris) | Birincil benzer fenomen mekanizması |
| Veri Saklama | MongoDB + Pickle Checkpoint | Kalıcı veri ve model deposu |
| Konteynerleştirme | Docker + Docker Compose | Bağımsız paketleme ve dağıtım |
| Test | Pytest | Skor, endpoint ve CF matrisi doğrulama |

---

## 17. Sınırlılıklar

- Veri seti **135 fenomen** ile sınırlıdır; bu büyüklük makine öğrenmesi modellerinin genelleme kapasitesi için yetersiz kalabilir.
- Uygunluk etiketleri (`uygun`/`orta`/`uygun_degil`) **tamamen kural tabanlı** üretilmiştir; gerçek kampanya başarı verisi (satış, marka bilinirliği artışı, dönüşüm oranı) bulunmamaktadır.
- Veriler yalnızca **Instagram** platformundan toplanmıştır; YouTube, TikTok, X gibi farklı platformların içerik dinamikleri bu bulgularla doğrudan genellenemez.
- XGBoost'un test setinde ulaştığı çok yüksek doğruluk değerleri, kural tabanlı etiketleme yapısının modeller tarafından kolayca öğrenilmesinden kaynaklanmaktadır; bu nedenle sonuçlar dikkatle yorumlanmalıdır.

---

## 18. Akademik ve Etik Bilgilendirme

Bu çalışma **TÜBİTAK 2209-A Üniversite Öğrencileri Araştırma Projeleri Destekleme Programı** kapsamında kabul edilmiş ve desteklenmeye hak kazanmıştır. Veri toplama ve saklama süreçlerinde KVKK ve uluslararası veri koruma ilkelerine tam uyum sağlanmış; tüm kişisel tanımlayıcılar anonimleştirilmiştir. Proje, akademik bir bitirme projesi/araştırma prototipi niteliğindedir ve ticari bir ürün olarak sunulmamaktadır.

---

*Yapay Zekâ Destekli Fenomen–Marka Eşleştirme Uygulaması — İstanbul Sağlık ve Teknoloji Üniversitesi, Yazılım Mühendisliği Bölümü - TÜBİTAK 2209-A Onaylı*
