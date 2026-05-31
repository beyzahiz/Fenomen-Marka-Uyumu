# -*- coding: utf-8 -*-
"""
mongo_client.py — MongoDB baglanti yardimcisi.
MongoDB yoksa graceful olarak None doner; sistem pkl ile calisir.
"""
import os

# Baglanti adresi: once MONGO_URI ortam degiskenine bakilir,
# yoksa gelistirme ortami icin localhost varsayilan olarak kullanilir.
MONGO_URI  = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Baglanilacak veritabani ve koleksiyon isimleri
DB_NAME    = "influencer_db"
COLLECTION = "processed_influencers"

# Modül seviyesinde önbellek degiskenleri (singleton pattern).
# Alt çizgi ile baslamasi bu degiskenlerin sadece bu modul icinde
# kullanilmasi gerektigini belirtir.
_client = None  # MongoClient nesnesi
_db     = None  # Veritabani nesnesi
_col    = None  # Koleksiyon nesnesi (en cok kullanilan, dogrudan sorgu bu nesne uzerinden yapilir)


def get_collection():
    """
    MongoDB koleksiyonunu dondurur. Baglanti yoksa None doner.

    Lazy singleton: ilk cagrildiginda baglanir, sonraki cagrilarda
    mevcut baglantıyı tekrar kullanir (gereksiz baglanti acilmaz).
    """
    global _client, _db, _col

    # Daha once basarili baglandıysak tekrar denemeye gerek yok
    if _col is not None:
        return _col

    try:
        from pymongo import MongoClient

        # MongoDB sunucusuna baglan; 2 saniye icinde yanit gelmezse zaman asimi olusur
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)

        # server_info() ile sunucunun gercekten ayakta olup olmadigi test edilir.
        # Sunucu kapalıysa burada exception firlatilir.
        _client.server_info()

        # Veritabani ve koleksiyon nesnelerini al
        _db  = _client[DB_NAME]
        _col = _db[COLLECTION]

        print(f"OK  MongoDB baglandi: {MONGO_URI} / {DB_NAME}")
        return _col

    except Exception as e:
        # Baglanti kurulamazsa (sunucu kapali, ag hatasi vb.) hata firlatmak yerine
        # None donulur. Bu sayede sistem pkl moduna gecer ve calismayi surdurebilir.
        print(f"UYARI: MongoDB baglantisi kurulamadi ({e}). pkl modu aktif.")
        return None


def is_mongo_available() -> bool:
    """
    MongoDB'nin kullanilabilir olup olmadigini kontrol eder.
    Diger moduller bu fonksiyonu kullanarak hangi modda (MongoDB / pkl)
    calisacagina karar verir.
    """
    return get_collection() is not None
