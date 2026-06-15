@echo off
echo ============================================
echo   Court Bot - API Packet Capture Setup
echo ============================================
echo.

REM Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%

echo Your computer IP: %LOCAL_IP%
echo.
echo Starting mitmweb on port 8080...
echo Web interface will open at: http://127.0.0.1:8081
echo.
echo ============================================
echo   PHONE SETUP:
echo ============================================
echo 1. Connect phone to same Wi-Fi as computer
echo 2. Set HTTP Proxy: %LOCAL_IP% port 8080
echo    iPhone: Settings → Wi-Fi → (i) → HTTP Proxy → Manual
echo    Android: Settings → WLAN → long-press → Modify network
echo 3. Open http://mitm.it on phone → install certificate
echo    iPhone extra: Settings → General → About →
echo      Certificate Trust Settings → Enable mitmproxy
echo 4. Open WeChat → badminton booking mini program
echo 5. Go through: login → view courts → view slots → book
echo 6. Come back to computer → web UI shows all API calls
echo ============================================
echo.

mitmweb --listen-port 8080 --web-host 0.0.0.0

pause
