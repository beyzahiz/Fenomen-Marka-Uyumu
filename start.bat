@echo off
chcp 65001 > nul
echo =====================================================
echo  Fenomen-Marka Eslestirme Sistemi
echo =====================================================
echo.

cd /d "%~dp0"

REM Sanal ortam yoksa oluştur
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo HATA: Python bulunamadi. Python 3.10+ yuklu oldugundan emin olun.
        pause
        exit /b 1
    )
)

REM Bağımlılıkları yükle
echo [2/3] Bagimliliklar yukleniyor (ilk kurulumda uzun surebilir)...
.venv\Scripts\pip install -r requirements.txt -q --no-warn-script-location
.venv\Scripts\pip install waitress -q --no-warn-script-location
echo.

REM API'yi başlat — waitress (Windows üretim sunucusu)
echo [3/3] API baslatiliyor...
echo.
echo  Tarayicinizda acin: http://localhost:5000
echo  Durdurmak icin    : Ctrl+C
echo.
.venv\Scripts\waitress-serve --host=0.0.0.0 --port=5000 --threads=4 app:app

pause
