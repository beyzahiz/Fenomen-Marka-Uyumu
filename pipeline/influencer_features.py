# =============================================================================
# pipeline/influencer_features.py — Gelişmiş Fenomen Özellik Analizi
# =============================================================================
# GÖREV   : Üç özel analiz fonksiyonu sağlar:
#   1. Benzer Fenomenler Tespiti  — K-Means cluster mesafesiyle en yakın N fenomen
#   2. Cinsiyet / Demografik Dağılım — profil bilgisinden çıkarım
#   3. Sahte Takipçi Tespiti     — cluster anomali skoru (fake_followers_risk)
#
# KULLANIM: app.py ve analiz_pipeline.py tarafından import edilerek kullanılır.
#   find_similar_influencers(df, "@ardaguler", top_n=5)
#   detect_fake_followers(df)   → "fake_followers_risk" sütunu ekler
#
# BAĞIMLILIK: sklearn (KMeans, StandardScaler)
# =============================================================================

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ============================================================================
# 1. BENZEŞİR FENOMENLERİN OTOMATİK TESPİTİ
# ============================================================================

def find_similar_influencers(influencer_summary, influencer_name, top_n=5):
    """
    İki kişi benzer mi diye kontrol et
    
    Parameters:
    -----------
    influencer_summary : DataFrame
        Fenomen özet tablosu (influencer_summary)
    influencer_name : str
        Örn: '@influencer1'
    top_n : int
        Kaç benzer fenomen gösterelim
        
    Returns:
    --------
    DataFrame : Benzer fenomenler listesi
    """
    try:
        idx = influencer_summary[
            influencer_summary['influencer_name'] == influencer_name
        ].index[0]
        cluster = influencer_summary.loc[idx, 'similarity_cluster']
        
        similar = influencer_summary[
            influencer_summary['similarity_cluster'] == cluster
        ].copy()
        
        similar = similar[similar['influencer_name'] != influencer_name]
        similar = similar.sort_values('engagement_rate', ascending=False).head(top_n)
        
        return similar[['influencer_name', 'category', 'engagement_rate', 'NFS']]
    
    except IndexError:
        return pd.DataFrame()


def add_similarity_clustering(influencer_summary):
    """
    K-Means clustering ile benzer fenomenler için 'similarity_cluster' sütunu ekle
    
    Parameters:
    -----------
    influencer_summary : DataFrame
        Fenomen özet tablosu
        
    Returns:
    --------
    DataFrame : 'similarity_cluster' sütunu eklenmiş yeni dataframe
    """
    df = influencer_summary.copy()
    
    # Features seç
    similarity_features = df[[
        'engagement_rate', 'FGR', 'posts_per_month', 'latest_followers'
    ]].fillna(0)
    
    # Standardize et
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(similarity_features)
    
    # K-Means
    kmeans = KMeans(n_clusters=6, random_state=42, n_init=10)
    df['similarity_cluster'] = kmeans.fit_predict(features_scaled)
    
    return df


# ============================================================================
# 2. CİNSİYET VE DEMOGRAFİK DAĞILIM ANALİZİ
# ============================================================================

def add_demographic_analysis(influencer_summary):
    """
    Kategori + Hashtag bazlı cinsiyet tahmini ekle
    
    Parameters:
    -----------
    influencer_summary : DataFrame
        Fenomen özet tablosu
        
    Returns:
    --------
    DataFrame : 'estimated_gender' ve 'gender_confidence' sütunları eklenmiş
    """
    
    # Kategori-bazlı demografik varsayımları
    category_demographics = {
        'moda'           : {'kadın': 0.75, 'erkek': 0.20, 'belirsiz': 0.05},
        'anne-bebek'     : {'kadın': 0.90, 'erkek': 0.05, 'belirsiz': 0.05},
        'saglik'         : {'kadın': 0.65, 'erkek': 0.30, 'belirsiz': 0.05},
        'yemek'          : {'kadın': 0.60, 'erkek': 0.35, 'belirsiz': 0.05},
        'egitim'         : {'kadın': 0.55, 'erkek': 0.40, 'belirsiz': 0.05},
        'spor'           : {'kadın': 0.45, 'erkek': 0.50, 'belirsiz': 0.05},
        'oyun'           : {'kadın': 0.30, 'erkek': 0.65, 'belirsiz': 0.05},
        'teknoloji'      : {'kadın': 0.35, 'erkek': 0.60, 'belirsiz': 0.05},
        'lifestyle'      : {'kadın': 0.60, 'erkek': 0.35, 'belirsiz': 0.05},
        'seyahat'        : {'kadın': 0.55, 'erkek': 0.40, 'belirsiz': 0.05},
        # Yeni kategoriler (10-kampanya sistemi)
        'beauty_fashion' : {'kadın': 0.72, 'erkek': 0.23, 'belirsiz': 0.05},
        'fitness_health' : {'kadın': 0.60, 'erkek': 0.35, 'belirsiz': 0.05},
        'technology'     : {'kadın': 0.35, 'erkek': 0.60, 'belirsiz': 0.05},
        'gaming'         : {'kadın': 0.30, 'erkek': 0.65, 'belirsiz': 0.05},
        'travel'         : {'kadın': 0.55, 'erkek': 0.40, 'belirsiz': 0.05},
        'finance_business': {'kadın': 0.40, 'erkek': 0.55, 'belirsiz': 0.05},
        'entertainment'  : {'kadın': 0.55, 'erkek': 0.40, 'belirsiz': 0.05},
        'sports'         : {'kadın': 0.40, 'erkek': 0.55, 'belirsiz': 0.05},
        'food_gastronomy': {'kadın': 0.60, 'erkek': 0.35, 'belirsiz': 0.05},
        'eglence'        : {'kadın': 0.55, 'erkek': 0.40, 'belirsiz': 0.05},
    }
    
    # Gender keywords
    gender_keywords = {
        'kadın': ['kız', 'kadın', 'girl', 'woman', 'bayan', 'my daughter', 'daughter', 'mom', 'anne'],
        'erkek': ['erkek', 'boy', 'man', 'abi', 'babası', 'oğlu', 'my son', 'son', 'daddy', 'baba'],
    }
    
    def estimate_demographic(row):
        category = row['category'].lower() if pd.notna(row['category']) else 'lifestyle'
        tags = str(row['clean_tags_all']).lower()
        
        # Hashtag'de cinsiyet referansı?
        for gender, keywords in gender_keywords.items():
            if any(kw in tags for kw in keywords):
                return gender, 0.8
        
        # Kategori bazlı
        if category in category_demographics:
            probs = category_demographics[category]
            estimated = max(probs, key=probs.get)
            confidence = probs[estimated]
            return estimated, confidence
        
        return 'belirsiz', 0.3
    
    df = influencer_summary.copy()
    df[['estimated_gender', 'gender_confidence']] = df.apply(
        lambda row: pd.Series(estimate_demographic(row)),
        axis=1
    )
    
    return df


# ============================================================================
# 3. SAHTE TAKIPÇI TESPİTİ
# ============================================================================

def add_fake_followers_detection(influencer_summary):
    """
    3 metotla sahte takipçi riski skoru hesapla:
    - Engagement Anomali
    - Growth Tutarlılığı
    - Reach vs Followers
    
    Parameters:
    -----------
    influencer_summary : DataFrame
        Fenomen özet tablosu
        
    Returns:
    --------
    DataFrame : Fake follower score sütunları eklenmiş
    """
    
    def detect_fake_engagement(engagement_rate):
        if 1 <= engagement_rate <= 5:
            return 0
        if engagement_rate < 0.5:
            return 85
        if engagement_rate > 10:
            return 60
        if engagement_rate < 1 or engagement_rate > 5:
            return 30
        return 0
    
    def detect_fake_growth(FGR, post_count):
        if post_count > 30 and FGR < 5:
            return 0
        if post_count < 15 and FGR > 30:
            return 70
        if 5 <= FGR <= 15:
            return 0
        if FGR > 30:
            return 50
        if FGR < 1 and post_count > 50:
            return 20
        return 0
    
    def detect_fake_reach(avg_reach, followers, posts):
        if followers == 0 or avg_reach == 0:
            return 0
        
        reach_ratio = avg_reach / followers if followers > 0 else 0
        
        if 0.10 <= reach_ratio <= 0.50:
            return 0
        if reach_ratio < 0.05:
            return 75
        if reach_ratio > 0.50:
            return 40
        return 20
    
    df = influencer_summary.copy()
    
    # Üç metodu hesapla
    df['fake_engagement_score'] = df['engagement_rate'].apply(detect_fake_engagement)
    df['fake_growth_score'] = df.apply(
        lambda r: detect_fake_growth(r['FGR'], r['post_count']), axis=1
    )
    df['fake_reach_score'] = df.apply(
        lambda r: detect_fake_reach(r['avg_post_reach'], r['latest_followers'], r['post_count']),
        axis=1
    )
    
    # Birleştir
    df['fake_followers_risk'] = (
        df['fake_engagement_score'] * 0.5 +
        df['fake_growth_score'] * 0.3 +
        df['fake_reach_score'] * 0.2
    ).round(1)
    
    # Kategoriyle
    def categorize_risk(score):
        if score >= 70:
            return '⚠️ ÇOK YÜKSEK'
        elif score >= 50:
            return '🟡 ORTA'
        elif score >= 30:
            return '🟢 DÜŞÜK'
        else:
            return '✅ TEMİZ'
    
    df['risk_category'] = df['fake_followers_risk'].apply(categorize_risk)
    
    return df


# ============================================================================
# 4. TÜMÜNÜ BİRLEŞTİREN FONKSİYON (TEST İÇİN)
# ============================================================================

def apply_all_features(influencer_summary):
    """
    Üç özelliği de sırasıyla uygula
    
    Parameters:
    -----------
    influencer_summary : DataFrame
        Fenomen özet tablosu
        
    Returns:
    --------
    DataFrame : Tüm özellikler eklenmiş yeni dataframe
    """
    
    print(" 1/3 - Benzer fenomenler tespiti...")
    df = add_similarity_clustering(influencer_summary)
    
    print(" 2/3 - Demografik analiz...")
    df = add_demographic_analysis(df)
    
    print(" 3/3 - Sahte takipçi tespiti...")
    df = add_fake_followers_detection(df)
    
    print(" Tüm özellikler eklendi!\n")
    
    return df


# ============================================================================
# 5. SONUÇ ÇIKARTMA FONKSİYONLARI (RAPORLAMA)
# ============================================================================

def report_similarities(influencer_summary):
    """Benzerlik clusterbindüm raporu"""
    print(" BENZEŞİR FENOMENLERİN OTOMATİK TESPİTİ\n")
    print("✅ Cluster Dağılımı:")
    print(influencer_summary['similarity_cluster'].value_counts().sort_index())
    print()


def report_demographics(influencer_summary):
    """Demografik analiz raporu"""
    print("\n👥 CİNSİYET VE DEMOGRAFİK DAĞILIM\n")
    print("Genel Dağılım:")
    print(influencer_summary['estimated_gender'].value_counts())
    print(f"\nOrtalama Güven Skoru: {influencer_summary['gender_confidence'].mean():.2%}")
    
    print("\nKategori Başına Dağılım:")
    demo_by_category = pd.crosstab(
        influencer_summary['category'],
        influencer_summary['estimated_gender']
    )
    print(demo_by_category)
    print()


def report_fake_followers(influencer_summary):
    """Sahte takipçi tespiti raporu"""
    print("\n🔴 SAHTE TAKIPÇI TESPİTİ\n")
    
    print("En Riskli 5 Fenomen (⚠️ ÇOK YÜKSEK RİSK):")
    risky = influencer_summary.sort_values('fake_followers_risk', ascending=False).head(5)
    print(risky[['influencer_name', 'category', 'fake_followers_risk', 'risk_category']].to_string())
    
    print("\n\nRisk Dağılımı:")
    print(influencer_summary['risk_category'].value_counts())
    
    print("\n\nİstatistik:")
    print(f"Ortalama Risk: {influencer_summary['fake_followers_risk'].mean():.1f}")
    print(f"Maksimum Risk: {influencer_summary['fake_followers_risk'].max():.1f}")
    print()


def generate_full_report(influencer_summary):
    """Tüm raporları oluştur"""
    report_similarities(influencer_summary)
    report_demographics(influencer_summary)
    report_fake_followers(influencer_summary)


# ============================================================================
# KULLANIM ÖRNEĞİ (Bu dosya direkt çalıştırılırsa)
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("INFLUENCER FEATURES TEST MODÜLÜ")
    print("=" * 70)
    print("\nBu modülü kullanmak için:\n")
    print("""
1. Notebook'ta tüm hücrelerinizi çalıştırın
2. Sonra bu kodu notebook'ta çalıştırın:

    from influencer_features import *
    
    # Tümünü uygula
    influencer_summary = apply_all_features(influencer_summary)
    
    # Rapor oluştur
    generate_full_report(influencer_summary)
    
    # Veya tek tek:
    similar = find_similar_influencers(influencer_summary, '@influencer1', top_n=5)
    print(similar)
    
3. Veya test olarak bu dosyayı doğrudan çalıştırın
    """)
