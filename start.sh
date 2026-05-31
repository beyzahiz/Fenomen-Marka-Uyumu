#!/usr/bin/env bash
# =============================================================================
# start.sh — Linux / macOS Başlatma Betiği
# =============================================================================
# KULLANIM : bash start.sh
# GÖREV    : Sanal ortam oluşturur, bağımlılıkları yükler, Flask API'yi başlatır.
# =============================================================================

set -e
cd "$(dirname "$0")"

export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

echo "====================================================="
echo "  Fenomen-Marka Eslestirme Sistemi"
echo "====================================================="
echo

VENV_DIR=".venv"

# 1) Sanal ortam
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[1/3] Sanal ortam olusturuluyor..."
    python3 -m venv "$VENV_DIR"
fi

# 2) Bağımlılıklar
echo "[2/3] Bagimliliklar yukleniyor..."
"$VENV_DIR/bin/pip" install -r requirements.txt -q
"$VENV_DIR/bin/pip" install gunicorn -q
echo

# macOS Monterey+ AirPlay Receiver varsayilan olarak 5000 portunu kullanir
if [ -z "${PORT:-}" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        PORT=5001
    else
        PORT=5000
    fi
fi

port_in_use() {
    lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

# Ayni porttaki eski gunicorn (onceki oturum) varsa kapat
if port_in_use "$PORT"; then
    for pid in $(lsof -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null); do
        if ps -p "$pid" -o command= 2>/dev/null | grep -qE 'gunicorn|app:app|python.*app\.py|flask'; then
            echo "Eski sunucu durduruluyor (PID $pid, port $PORT)..."
            kill "$pid" 2>/dev/null || true
        fi
    done
    sleep 1
fi

# Port hala doluysa (AirPlay vb.) bos port bul
_base_port=$PORT
while port_in_use "$PORT"; do
  if [ "$PORT" -gt "$((_base_port + 20))" ]; then
    echo "Hata: ${_base_port}-$PORT arasi portlar dolu. Dolu portu kapatin:"
    echo "  lsof -i :${_base_port}"
    exit 1
  fi
  echo "Port $PORT dolu, $((PORT + 1)) deneniyor..."
  PORT=$((PORT + 1))
done

# 3) API'yi başlat
echo "[3/3] API baslatiliyor..."
echo
echo "  Tarayicinizda acin : http://127.0.0.1:${PORT}"
echo "  Durdurmak icin     : Ctrl+C"
echo

# macOS: gunicorn worker + PyTorch/MPS cokuyor — dogrudan Flask (tek process)
if [ "$(uname -s)" = "Darwin" ]; then
    export PORT
    "$VENV_DIR/bin/python" app.py
else
    "$VENV_DIR/bin/gunicorn" \
        --bind "0.0.0.0:${PORT}" \
        --workers 2 \
        --timeout 120 \
        app:app
fi
