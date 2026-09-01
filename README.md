# Chzzk Chat Crawler

<img src="figure/logo.svg" width="400">  

파이썬을 통해 네이버 치지직(CHZZK) 방송의 실시간 채팅 및 후원 내역을 크롤링하고 누적 저장하는 도구입니다.  
스트리머가 방송을 종료하고 다음 날 다시 방송을 켜도 끊김 없이 자동으로 재연결되어 24시간 안정적으로 수집할 수 있습니다.

---

## ✨ 주요 기능

- **📁 방송 세션별 CSV 파일 분할 저장 (`csv/{채널명}_{시작일시}.csv`)**:
  - 방송이 새로 시작될 때마다 방송 시작 시간(예: `csv/LCK_20260902_163002.csv`)을 기준으로 별도의 CSV 파일이 자동 생성됩니다.
  - 하루에 방송이 여러 번 종료/재시작되어도 **다시보기 VOD 비디오와 채팅 내역의 싱크를 정확하게 매칭**할 수 있습니다.
  - `utf-8-sig` 인코딩이 적용되어 Excel이나 스프레드시트에서 한글 깨짐 없이 바로 열람 가능합니다.
  - 실시간 디스크 플러시(`flush`)로 대량의 메시지도 누락 없이 안전하게 기록됩니다.
- **🔄 무중단 장기 실행 & 자동 재연결**:
  - 스트리머가 방송을 종료하면 자동으로 대기 모드로 전환되며, 방송이 다시 시작되면 새 토큰을 발급받아 끊김 없이 수집을 재개합니다.
  - 네트워크 단절이나 일시적 오류 발생 시 자동 복구 로직이 작동합니다.
- **⚙️ 간편한 설정 파일 지원 (`config.json`)**:
  - 스트리머 ID, 저장 폴더, 확인 주기 등을 `config.json`에 저장하여 매번 인자를 입력할 필요 없이 `python run.py`만으로 실행할 수 있습니다.
- **📝 텍스트 로그 동시 기록 (`chat.log`)**:
  - 터미널 출력과 함께 일반 텍스트 로그 파일에도 덮어쓰지 않고 계속 이어써집니다(`append`).

---

## 🚀 설치 방법 (Python 3.14+ 및 Conda 권장)

이 프로젝트는 최신 **Python 3.14+** 환경에 완벽하게 호환되도록 최적화되어 있습니다.

```bash
# 1. 코드 다운로드 (Clone)
git clone https://github.com/KaitouJoker/ChzzkChat.git
cd ChzzkChat

# 2. Python 3.14 Conda 가상환경 생성 및 활성화
conda create -n chzzk python=3.14 -y
conda activate chzzk

# 3. 필수 패키지 설치
pip install -r requirements.txt
```

*(참고: Python 3.9 ~ 3.14+ 모든 파이썬 버전을 지원하며, venv 환경을 사용하셔도 무방합니다.)*

---

## 🔑 준비하기 (네이버 쿠키 설정)

1. 웹 브라우저(Chrome 등)에서 네이버에 로그인한 후 개발자 도구(`F12`)를 엽니다.
2. **Application (애플리케이션)** 탭 -> **Cookies (쿠키)** -> `https://naver.com` 항목으로 이동합니다.
3. `NID_AUT`와 `NID_SES` 값을 복사합니다.
4. 프로젝트 루트의 `cookies.json` 파일에 해당 값들을 붙여 넣습니다:
   ```json
   {
       "NID_AUT": "복사한_NID_AUT_값",
       "NID_SES": "복사한_NID_SES_값"
   }
   ```

---

## 🛠️ 설정 (`config.json`)

`config.json` 파일에서 기본 실행 옵션을 자유롭게 수정할 수 있습니다:

```json
{
    "streamer_id": "9381e7d6816e6d915a44a13c0195b202",
    "output_dir": "csv",
    "output_log": "chat.log",
    "check_interval": 20
}
```

| 설정 키 | 기본값 | 설명 |
|---|---|---|
| `streamer_id` | `9381e7d6816e6d915a44a13c0195b202` | 수집할 치지직 스트리머 채널 고유 ID |
| `output_dir` | `csv` | 방송별 CSV 파일들이 저장될 디렉터리 경로 |
| `output_log` | `chat.log` | 콘솔 로그가 누적 저장될 파일 경로 |
| `check_interval` | `20` | 방송 오프라인 시 다음 시작 여부를 확인할 주기(초) |

---

## 💻 사용 방법

### 방법 1. 원클릭 실행 (Windows 배치 파일)
- 탐색기에서 **[`run.bat`](file:///d:/programming%20language/pythun/Github/ChzzkChat/run.bat)** 파일을 더블 클릭하면 자동으로 `chzzk` Conda 환경을 활성화하고 크롤러를 실행합니다.

### 방법 2. 콘솔/터미널에서 실행
```bash
# 기본 실행 (config.json 설정값 기반으로 시작)
python run.py

# 특정 스트리머 ID를 커맨드라인에서 바로 지정하여 실행
python run.py --streamer_id 9381e7d6816e6d915a44a13c0195b202

# 다른 설정 파일을 지정하여 실행
python run.py --config my_config.json

# 저장 폴더 및 확인 주기 임시 변경
python run.py --output_dir my_csv_folder --check_interval 30
```

> 💡 작동을 중지하려면 터미널 창에서 `Ctrl + C`를 누르시면 안전하게 연결을 닫고 종료됩니다.

---

## 📊 CSV 데이터 구조

생성되는 `csv/{채널명}_{시작일시}.csv` 파일은 다음과 같은 구조로 실시간 기록됩니다:

| 컬럼명 | 설명 | 예시 |
|---|---|---|
| `datetime` | 한국 시간 기준 일시 | `2026-09-02 12:34:56` |
| `timestamp` | 밀리초 단위 타임스탬프 | `1788284096000` |
| `streamer_id` | 스트리머 채널 ID | `9381e7d6816e6d915a44a13c0195b202` |
| `channel_name` | 채널 이름 | `LCK` |
| `type` | 메시지 유형 | `채팅` 또는 `후원` |
| `user_id` | 사용자 식별자 해시 | `anonymous` 또는 `유저해시값` |
| `nickname` | 작성자 닉네임 | `치지직유저` (익명 후원 시 '익명의 후원자') |
| `message` | 채팅 또는 후원 메시지 본문 | `안녕하세요!` |

---

## 🙏 Credits

이 프로젝트는 [kimcore](https://github.com/kimcore/chzzk/tree/main) 님의 코드 및 [Buddha7771](https://github.com/Buddha7771/ChzzkChat) 님의 원본 저장소를 기반으로 개선되었습니다.


