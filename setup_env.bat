@echo off
chcp 65001 >nul
echo ============================================
echo   KRX 주식 AI 에이전트 - 환경 설정
echo ============================================
echo.

:: Python 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo Python 3.12를 설치해주세요:
    echo   https://www.python.org/downloads/
    echo.
    echo 설치 시 "Add Python to PATH" 체크박스를 반드시 선택하세요.
    echo.
    pause
    exit /b 1
)

echo [1/4] Python 확인 완료
python --version
echo.

:: 가상환경 생성
if not exist "venv" (
    echo [2/4] 가상환경 생성 중...
    python -m venv venv
) else (
    echo [2/4] 가상환경 이미 존재합니다.
)
echo.

:: 가상환경 활성화 및 패키지 설치
echo [3/4] 패키지 설치 중...
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo.

:: .env 파일 생성
if not exist ".env" (
    echo [4/4] .env 파일 생성 중...
    copy .env.example .env
    echo.
    echo [중요] .env 파일을 열어 ANTHROPIC_API_KEY를 설정하세요.
    echo   API 키가 없어도 퀀트 분석은 가능합니다.
) else (
    echo [4/4] .env 파일 이미 존재합니다.
)

echo.
echo ============================================
echo   설정 완료!
echo ============================================
echo.
echo 실행 방법:
echo   venv\Scripts\activate.bat
echo   python cli.py
echo.
pause
