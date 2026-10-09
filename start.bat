@echo off
chcp 65001 > nul
echo กำลังเริ่มต้นระบบ ThaiNDC AI Learning Assistant...
cd /d "%~dp0"
if "%GEMINI_API_KEY%"=="" set GEMINI_API_KEY=%OPENAI_API_KEY%

if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
    echo กำลังเปิด Public Tunnel สำหรับให้ผู้อื่นเชื่อมต่อ...
    start /b "" "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url https://localhost:8443 --no-tls-verify > nul 2>&1
)

.\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8443 --ssl-certfile localhost.pem --ssl-keyfile localhost-key.pem
pause
