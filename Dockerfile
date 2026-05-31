# ============================================================
# Fenomen-Marka Eslestirme Sistemi — Docker Image
# ============================================================
# Kullanim:
#   docker compose up --build
#   Ardından: http://localhost:5000
# ============================================================

FROM python:3.11-slim

# ── Sistem bağımlılıkları ────────────────────────────────────
# libgomp1 : LightGBM için OpenMP
# curl     : sağlık kontrolü için
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python bağımlılıkları (önce yükle — layer cache için) ───
COPY requirements-prod.txt ./requirements.txt

# PyTorch CPU-only sürümü yükle (GPU yok → daha küçük image)
RUN pip install --no-cache-dir \
        torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu

# Geri kalan bağımlılıklar
RUN pip install --no-cache-dir -r requirements.txt

# ── SBERT modelini build aşamasında indir (çalışma zamanında internet gerekmez) ──
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2'); \
print('SBERT model indirildi')"

# ── Uygulama dosyaları ───────────────────────────────────────
COPY app.py          ./
COPY influencer_features.py ./
COPY influencer_summary_checkpoint.pkl ./
COPY best_model_xgb.pkl    ./
COPY label_encoder.pkl     ./
COPY feature_columns.pkl   ./
COPY db/                   ./db/
COPY frontend/             ./frontend/

# ── Ortam değişkenleri ───────────────────────────────────────
ENV PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

EXPOSE 5000

# ── Sağlık kontrolü ──────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/stats || exit 1

# ── Üretim sunucusu: gunicorn ─────────────────────────────────
# 1 worker: model bellek içinde, birden fazla worker kopya yükler
# timeout 120s: SBERT kodlama biraz uzun sürebilir
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
