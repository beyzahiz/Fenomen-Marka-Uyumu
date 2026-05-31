# =============================================================================
# start.py — Evrensel Başlatma Betiği (Windows / Linux / macOS)
# =============================================================================
# KULLANIM : python start.py
# GÖREV    : Sanal ortam oluşturur, bağımlılıkları yükler, Flask API başlatır.
#            start.bat (Windows) ve start.sh (Linux/macOS) alternatifi.
# =============================================================================

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"

IS_WIN = sys.platform == "win32"
PY  = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
PIP = VENV / ("Scripts/pip.exe"    if IS_WIN else "bin/pip")

BANNER = """
=====================================================
  Fenomen-Marka Eslestirme Sistemi
=====================================================
"""

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def main():
    print(BANNER)
    os.chdir(ROOT)
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

    # 1) Sanal ortam
    if not PY.exists():
        print("[1/3] Sanal ortam olusturuluyor...")
        run([sys.executable, "-m", "venv", str(VENV)])

    # 2) Bağımlılıklar
    print("[2/3] Bagimliliklar yukleniyor...")
    run([str(PIP), "install", "-r", "requirements.txt", "-q"])

    # macOS AirPlay Receiver 5000 portunu kullanabilir
    port = os.environ.get("PORT")
    if not port:
        port = "5001" if sys.platform == "darwin" else "5000"

    # 3) Üretim sunucusu seç
    print("[3/3] API baslatiliyor...\n")
    print(f"  Tarayicinizda acin : http://127.0.0.1:{port}")
    print("  Durdurmak icin     : Ctrl+C\n")

    env = os.environ.copy()
    env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    env["PORT"] = port

    if IS_WIN:
        run([str(PIP), "install", "waitress", "-q"])
        run([str(PY), "-m", "waitress",
             "--host=0.0.0.0", f"--port={port}", "--threads=4", "app:app"], env=env)
    elif sys.platform == "darwin":
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        run([str(PY), "app.py"], env=env)
    else:
        run([str(PIP), "install", "gunicorn", "-q"])
        run([str(VENV / "bin/gunicorn"),
             "--bind", f"0.0.0.0:{port}",
             "--workers", "2",
             "--timeout", "120",
             "app:app"], env=env)

if __name__ == "__main__":
    main()
