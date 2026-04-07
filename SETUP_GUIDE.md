# KRX 주식 AI 에이전트 — 설치 가이드

## 1단계: Python 설치

### Windows
1. https://www.python.org/downloads/ 에서 **Python 3.12** 다운로드
2. 설치 시 **반드시** "Add Python to PATH" 체크박스 선택
3. "Install Now" 클릭

### 설치 확인
명령 프롬프트(cmd)에서:
```
python --version
```
`Python 3.12.x`가 출력되면 성공

## 2단계: 프로젝트 설정

### 자동 설정 (권장)
`krx-stock-agent` 폴더에서 `setup_env.bat`을 더블클릭하면 자동으로:
- 가상환경 생성
- 필요 패키지 설치
- .env 파일 생성

### 수동 설정
```bash
# 프로젝트 폴더로 이동
cd krx-stock-agent

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

## 3단계: 설정

### 포트폴리오 수정 (필수)
`config/portfolio.yaml` 파일을 열어 본인의 보유 종목 정보를 확인/수정합니다:
- `ticker`: 종목코드 (6자리)
- `quantity`: 보유 수량
- `buy_price`: 평균 매입가 (원)
- `account`: 증권사 계좌 구분
- `type`: stock 또는 etf

### Claude API 키 (선택)
LLM 감성분석을 사용하려면 `.env` 파일에 API 키를 설정합니다:
```
ANTHROPIC_API_KEY=sk-ant-...
```
API 키가 없어도 퀀트 분석은 정상 동작합니다.

## 4단계: 실행

```bash
# 가상환경 활성화 (매번 필요)
venv\Scripts\activate

# 포트폴리오 전체 분석
python cli.py

# 단일 종목 분석
python cli.py --ticker 005930
```

## 문제 해결

### "python을 찾을 수 없습니다"
→ Python 설치 시 "Add to PATH"를 선택하지 않은 경우입니다.
→ Python을 재설치하고 PATH 옵션을 선택하세요.

### "ModuleNotFoundError: No module named 'pykrx'"
→ 가상환경이 활성화되지 않았습니다.
→ `venv\Scripts\activate` 실행 후 다시 시도하세요.

### "종목 XXX의 데이터를 가져올 수 없습니다"
→ 종목코드가 잘못되었거나, 상장폐지된 종목일 수 있습니다.
→ `config/portfolio.yaml`에서 종목코드를 확인하세요.
