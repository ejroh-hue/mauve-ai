@echo off
chcp 65001 >nul
cd /d "G:\공유 드라이브\TAOR_BACKUP\Eunju Roh\★자산 정리\주식 관련\krx-stock-agent"
echo KRX 주식 에이전트 분석 시작...
echo.
C:\Users\taorc\krx-stock-agent-venv\Scripts\python.exe cli.py
echo.
echo 분석 완료. 아무 키나 누르면 창이 닫힙니다.
pause
