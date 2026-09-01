# Chzzk Chat Crawler

<img src="figure/logo.svg" width="400">  

<img src="figure/image.png">  

파이썬을 통해 네이버 치지직 서비스의 채팅을 크롤링 해봅시다.

이 코드는 [kimcore](https://github.com/kimcore/chzzk/tree/main)님의 코드를 기반으로 작성하였습니다.

## 설치

    # 코드 다운로드
    $ git clone https://github.com/Buddha7771/ChzzkChat .
    $ cd ChzzkChat

    # 가상환경 설치
    $ conda create -n chzzk python=3.9
    $ conda activate chzzk

    # 패키지 설치
    $ pip install -r requirements.txt

## 준비하기

1. 웹 브라우저에서 네이버를 켜고 개발자 도구(F12)를 켭니다.
2. 쿠키(Cookies) 탭에 들어가 `NID_AUT`와 `NID_SES` 값을 찾습니다.
3. 해당 값들을 `cookies.json` 파일에 붙여 넣습니다.
4. (선택 사항) `config.json` 파일에서 원하는 기본 설정을 수정합니다:
   ```json
   {
       "streamer_id": "9381e7d6816e6d915a44a13c0195b202",
       "output_csv": "chat.csv",
       "output_log": "chat.log",
       "check_interval": 20
   }
   ```

## 사용하기

```bash
# 1. 기본 실행 (config.json 설정값으로 구동)
python run.py

# 2. 커맨드라인에서 특정 옵션만 덮어써서 실행
python run.py --streamer_id 9381e7d6816e6d915a44a13c0195b202

# 3. 다른 설정 파일 지정 실행
python run.py --config custom_config.json
```

### 주요 기능
- **설정 파일 기반 간편 실행 (`config.json`)**: 스트리머 ID, 저장 경로, 체크 주기를 JSON에 저장하여 `python run.py`만으로 간편 구동.
- **CSV 누적 저장 (`chat.csv`)**: 엑셀 호환(`utf-8-sig`) 인코딩으로 실시간 append 저장되어 대량의 메시지도 스프레드시트에서 쉽게 분석 가능합니다.
- **무중단 장기 실행 & 자동 재연결**: 스트리머가 방송을 종료해도 대기 모드로 전환되며, 다음 날 다시 방송을 시작하면 새 토큰으로 자동 재연결되어 계속 수집합니다.
- **로그 누적 보존 (`chat.log`)**: 기존 텍스트 로그도 덮어쓰지 않고 계속 이어써집니다.

> 작동을 중지하려면 터미널에서 `Ctrl + C`를 눌러주세요.
