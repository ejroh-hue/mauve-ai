@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "G:\공유 드라이브\TAOR_BACKUP\Eunju Roh\★자산 정리\주식 관련\krx-stock-agent"
echo 대시보드 시작 중...
echo 잠시 후 브라우저에서 http://localhost:8502 를 열어주세요.
echo (이 창을 닫으면 대시보드가 종료됩니다)
echo.
C:\Users\taorc\krx-stock-agent-venv2\Scripts\python.exe -m streamlit run app/app.py --server.port 8502 --server.headless true

