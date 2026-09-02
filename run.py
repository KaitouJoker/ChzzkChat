import argparse
import csv
import datetime
import json
import logging
import os
import re
import threading
import time
from typing import Any
from websocket import WebSocket

import api
from cmd_type import CHZZK_CHAT_CMD


def _now_str() -> str:
    """현재 시간을 'YYYY-MM-DD HH:MM:SS' 형식의 문자열로 반환합니다."""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 특수문자를 언더스코어(_)로 치환합니다."""
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()


def _get_chat_ws_url(chat_channel_id: str) -> str:
    """chatChannelId 해시를 기반으로 1~9번 채팅 서버 중 적절한 샤드 URL을 계산합니다."""
    server_idx = (sum(ord(c) for c in chat_channel_id) % 9) + 1
    return f"wss://kr-ss{server_idx}.chat.naver.com/chat"


class CsvChatLogger:
    """채팅 및 후원 내역을 CSV 파일에 실시간으로 누적(Append) 저장하는 클래스입니다."""

    def __init__(self, filepath: str) -> None:
        self.filepath: str = filepath
        file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0

        # 상위 디렉터리 자동 생성
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # 엑셀 호환을 위해 utf-8-sig 인코딩 사용
        self.file = open(self.filepath, mode='a', newline='', encoding='utf-8-sig')
        self.writer = csv.writer(self.file, quoting=csv.QUOTE_MINIMAL)

        if not file_exists:
            self.writer.writerow([
                'datetime',
                'timestamp',
                'streamer_id',
                'channel_name',
                'type',
                'user_id',
                'nickname',
                'message'
            ])
            self.file.flush()

    def write_chat(
        self,
        dt_str: str,
        timestamp_ms: int,
        streamer_id: str,
        channel_name: str,
        chat_type: str,
        user_id: str,
        nickname: str,
        message: str
    ) -> None:
        self.writer.writerow([
            dt_str,
            timestamp_ms,
            streamer_id,
            channel_name,
            chat_type,
            user_id,
            nickname,
            message
        ])
        self.file.flush()

    def close(self) -> None:
        if self.file and not self.file.closed:
            self.file.flush()
            self.file.close()


class ChzzkChat:

    def __init__(
        self,
        streamer: str,
        cookies: dict[str, Any],
        logger: logging.Logger,
        output_dir: str = 'csv',
        check_interval: int = 20
    ) -> None:
        self.streamer: str = streamer
        self.cookies: dict[str, Any] = cookies
        self.logger: logging.Logger = logger
        self.output_dir: str = output_dir
        self.check_interval: int = check_interval

        self.sid: str | None = None
        self.sock: WebSocket | None = None
        self.chatChannelId: str | None = None
        self.channelName: str = streamer
        self.userIdHash: str = ""
        self.accessToken: str | None = None
        self.extraToken: str | None = None

        self.current_csv_logger: CsvChatLogger | None = None
        self.current_csv_path: str | None = None

        # 백그라운드 하트비트 스레드 관리
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop_event: threading.Event | None = None

        # CSV 저장 디렉터리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        self._init_account_info()

    def _init_account_info(self) -> None:
        try:
            self.channelName = api.fetch_channelName(self.streamer)
        except Exception as e:
            self.logger.warning(f"[{_now_str()}][{self.streamer}] 채널명 조회 실패: {e}")
            self.channelName = self.streamer

        try:
            self.userIdHash = api.fetch_userIdHash(self.cookies)
        except Exception as e:
            self.logger.warning(f"[{_now_str()}][{self.channelName}] 유저 상태(userIdHash) 조회 실패: {e}")
            self.userIdHash = ""

    def _create_session_csv(self, open_date_str: str, live_title: str) -> None:
        """새로운 방송 세션마다 고유한 타임스탬프 파일명의 CSV 로거를 생성합니다."""
        if open_date_str:
            # 치지직 openDate 포맷: '2026-09-02 16:30:02' -> '20260902_163002'
            time_tag = open_date_str.replace('-', '').replace(':', '').replace(' ', '_')
        else:
            time_tag = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        safe_channel = _sanitize_filename(self.channelName)
        filename = f"{safe_channel}_{time_tag}.csv"
        filepath = os.path.join(self.output_dir, filename)

        # 기존 로거가 열려있다면 먼저 닫기
        self._close_session_csv()

        self.current_csv_logger = CsvChatLogger(filepath)
        self.current_csv_path = filepath
        self.logger.info(f"[{_now_str()}][{self.channelName}] 방송 채팅 저장 파일 생성: {filepath}")

    def _close_session_csv(self) -> None:
        """현재 방송 세션의 CSV 로거를 안전하게 플러시하고 닫습니다."""
        if self.current_csv_logger:
            try:
                self.current_csv_logger.close()
                self.logger.info(f"[{_now_str()}][{self.channelName}] 방송 세션 종료 - CSV 파일 저장 완료: {self.current_csv_path}")
            except Exception as e:
                self.logger.warning(f"[{_now_str()}][{self.channelName}] CSV 파일 닫기 중 오류: {e}")
            self.current_csv_logger = None
            self.current_csv_path = None

    def _start_heartbeat(self) -> None:
        """웹소켓 연결 유지를 위해 20초마다 Ping(10000)을 전송하는 백그라운드 스레드를 시작합니다."""
        self._stop_heartbeat()
        self._heartbeat_stop_event = threading.Event()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="ChzzkHeartbeatThread",
            daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        """하트비트 스레드를 안전하게 중지합니다."""
        if self._heartbeat_stop_event:
            self._heartbeat_stop_event.set()
            self._heartbeat_stop_event = None
        self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        """20초마다 서버로 하트비트 패킷을 전송합니다."""
        while self._heartbeat_stop_event and not self._heartbeat_stop_event.is_set():
            if self._heartbeat_stop_event.wait(timeout=20):
                break

            if self.sock and self.sock.connected:
                try:
                    self.sock.send(
                        json.dumps({
                            "ver": "2",
                            "cmd": CHZZK_CHAT_CMD['pong']  # cmd: 10000 (하트비트 Ping)
                        })
                    )
                except Exception:
                    break

    def connect(self, chat_channel_id: str) -> None:
        self.chatChannelId = chat_channel_id
        self.accessToken, self.extraToken = api.fetch_accessToken(self.chatChannelId, self.cookies)

        ws_url = _get_chat_ws_url(self.chatChannelId)
        sock = WebSocket()
        sock.connect(ws_url)
        self.logger.info(f"[{_now_str()}][{self.channelName}] 채팅 서버 연결 중 ({ws_url})...")

        default_dict: dict[str, Any] = {
            "ver": "2",
            "svcid": "game",
            "cid": self.chatChannelId,
        }

        send_dict: dict[str, Any] = {
            "cmd": CHZZK_CHAT_CMD['connect'],
            "tid": 1,
            "bdy": {
                "uid": self.userIdHash,
                "devType": 2001,
                "accTkn": self.accessToken,
                "auth": "SEND"
            }
        }

        sock.send(json.dumps(dict(send_dict, **default_dict)))
        sock_response = json.loads(sock.recv())
        self.sid = sock_response['bdy']['sid']

        send_dict = {
            "cmd": CHZZK_CHAT_CMD['request_recent_chat'],
            "tid": 2,
            "sid": self.sid,
            "bdy": {
                "recentMessageCount": 50
            }
        }

        sock.send(json.dumps(dict(send_dict, **default_dict)))
        sock.recv()

        self.sock = sock
        if self.sock.connected:
            self.logger.info(f"[{_now_str()}][{self.channelName}] 채팅창 연결 완료 (채팅 채널 ID: {self.chatChannelId})")
            # 연결 성공 시 하트비트 스레드 시작
            self._start_heartbeat()
        else:
            raise ConnectionError("채팅 서버 연결 실패")

    def close_socket(self) -> None:
        self._stop_heartbeat()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, message: str) -> None:
        if not self.sock or not self.sock.connected:
            self.logger.warning(f"[{_now_str()}][{self.channelName}] 채팅 서버에 연결되어 있지 않아 메시지를 전송할 수 없습니다.")
            return

        default_dict: dict[str, Any] = {
            "ver": 2,
            "svcid": "game",
            "cid": self.chatChannelId,
        }

        extras = {
            "chatType": "STREAMING",
            "emojis": "",
            "osType": "PC",
            "extraToken": self.extraToken,
            "streamingChannelId": self.chatChannelId
        }

        send_dict: dict[str, Any] = {
            "tid": 3,
            "cmd": CHZZK_CHAT_CMD['send_chat'],
            "retry": False,
            "sid": self.sid,
            "bdy": {
                "msg": message,
                "msgTypeCode": 1,
                "extras": json.dumps(extras),
                "msgTime": int(datetime.datetime.now().timestamp())
            }
        }

        self.sock.send(json.dumps(dict(send_dict, **default_dict)))

    def run(self) -> None:
        self.logger.info(f"[{_now_str()}][{self.channelName}] 무중단 채팅 수집기를 시작합니다. (CSV 저장 폴더: '{self.output_dir}')")

        while True:
            try:
                # 1. 방송 상태 확인
                try:
                    live_status = api.fetch_live_status(self.streamer, self.cookies)
                except Exception as e:
                    self.logger.warning(f"[{_now_str()}][{self.channelName}] 방송 상태 조회 중 오류 발생 ({e}). {self.check_interval}초 후 재시도합니다.")
                    time.sleep(self.check_interval)
                    continue

                is_live = (live_status.get('status') == 'OPEN')
                chat_channel_id = live_status.get('chatChannelId')

                if not is_live or not chat_channel_id:
                    # 방송이 꺼진 경우 기존 세션 CSV 닫기
                    self._close_session_csv()
                    self.logger.info(
                        f"[{_now_str()}][{self.channelName}] 현재 방송이 꺼져 있습니다 (상태: {live_status.get('status', 'CLOSE')}). "
                        f"{self.check_interval}초 후 방송 시작 여부를 확인합니다..."
                    )
                    time.sleep(self.check_interval)
                    continue

                # 2. 방송 중인 경우 연결
                title = live_status.get('liveTitle', '')
                open_date = live_status.get('openDate', '')
                self.logger.info(f"[{_now_str()}][{self.channelName}] 방송 감지됨 - 제목: '{title}', 시작시간: '{open_date}', 채팅 채널 ID: {chat_channel_id}")

                # 세션별 CSV 로거 생성 (아직 열려있지 않은 경우)
                if not self.current_csv_logger:
                    self._create_session_csv(open_date, title)

                try:
                    self.connect(chat_channel_id)
                except Exception as e:
                    self.logger.error(f"[{_now_str()}][{self.channelName}] 채팅 서버 접속 실패 ({e}). 5초 후 재시도합니다.")
                    self.close_socket()
                    time.sleep(5)
                    continue

                # 3. 실시간 수신 루프
                self._listen_loop()

                # 수신 루프 종료 시 (방종 또는 연결 끊김) CSV 세션 정리
                self._close_session_csv()

            except KeyboardInterrupt:
                self.logger.info(f"[{_now_str()}] 프로그램 종료 요청을 받았습니다.")
                self.close_socket()
                self._close_session_csv()
                break
            except Exception as e:
                self.logger.error(f"[{_now_str()}] 예기치 못한 오류 발생: {e}. 5초 후 재시도합니다.")
                self.close_socket()
                self._close_session_csv()
                time.sleep(5)

    def _listen_loop(self) -> None:
        while self.sock and self.sock.connected:
            try:
                raw_message = self.sock.recv()
                if not raw_message:
                    break

                raw_message_json: dict[str, Any] = json.loads(raw_message)
                chat_cmd = raw_message_json.get('cmd')

                # 서버 -> 클라이언트 Ping (0) 요청 시 응답
                if chat_cmd == CHZZK_CHAT_CMD['ping']:
                    self.sock.send(
                        json.dumps({
                            "ver": "2",
                            "cmd": CHZZK_CHAT_CMD['pong']
                        })
                    )
                    continue

                # 클라이언트 -> 서버 Ping에 대한 서버 응답(10000)
                if chat_cmd == CHZZK_CHAT_CMD['pong']:
                    continue

                if chat_cmd == CHZZK_CHAT_CMD['chat']:
                    chat_type = '채팅'
                elif chat_cmd == CHZZK_CHAT_CMD['donation']:
                    chat_type = '후원'
                else:
                    continue

                for chat_data in raw_message_json.get('bdy', []):
                    user_id = chat_data.get('uid', '')
                    if user_id == 'anonymous':
                        nickname = '익명의 후원자'
                    else:
                        try:
                            profile_data: dict[str, Any] = json.loads(chat_data.get('profile', '{}'))
                            nickname = profile_data.get('nickname', '알 수 없음')
                        except Exception:
                            nickname = '알 수 없음'

                    msg = chat_data.get('msg', '')
                    if not msg:
                        continue

                    msg_time_ms = chat_data.get('msgTime', int(datetime.datetime.now().timestamp() * 1000))
                    now = datetime.datetime.fromtimestamp(msg_time_ms / 1000)
                    now_str = datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')

                    # 1. 터미널 및 chat.log 출력
                    self.logger.info(f'[{now_str}][{chat_type}] {nickname} : {msg}')

                    # 2. 해당 방송 세션의 CSV 파일에 실시간 저장
                    if self.current_csv_logger:
                        self.current_csv_logger.write_chat(
                            dt_str=now_str,
                            timestamp_ms=msg_time_ms,
                            streamer_id=self.streamer,
                            channel_name=self.channelName,
                            chat_type=chat_type,
                            user_id=user_id,
                            nickname=nickname,
                            message=msg
                        )

            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.logger.warning(f"[{_now_str()}] 메시지 수신 중 끊김 발생 ({e}). 재연결을 시도합니다.")
                break

        self.close_socket()


def get_logger(log_path: str = 'chat.log') -> logging.Logger:
    formatter = logging.Formatter('%(message)s')

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 기존 로그가 삭제되지 않도록 mode="a" (append)로 설정
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def load_config(config_path: str = 'config.json') -> dict[str, Any]:
    """설정 파일(config.json)을 로드하며, 파일이 없거나 오류 발생 시 기본값을 반환합니다."""
    default_config: dict[str, Any] = {
        'streamer_id': '9381e7d6816e6d915a44a13c0195b202',
        'output_dir': 'csv',
        'output_log': 'chat.log',
        'check_interval': 20
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8-sig') as f:
                file_config = json.load(f)
                if isinstance(file_config, dict):
                    default_config.update(file_config)
        except Exception as e:
            print(f"[경고] 설정 파일({config_path}) 읽기 실패: {e}. 기본값을 사용합니다.")
    return default_config


if __name__ == '__main__':
    # 1. 설정 파일 경로 우선 파싱
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument('--config', type=str, default='config.json', help='설정 파일 경로 (기본값: config.json)')
    pre_args, _ = pre_parser.parse_known_args()

    config = load_config(pre_args.config)

    # 2. 메인 파서 생성 (config.json의 값을 기본값으로 반영)
    parser = argparse.ArgumentParser(
        description="Chzzk Chat & Donation Crawler (Python 3.14+ Compatible)",
        parents=[pre_parser]
    )
    parser.add_argument(
        '--streamer_id',
        type=str,
        default=config.get('streamer_id', '9381e7d6816e6d915a44a13c0195b202'),
        help=f"스트리머 고유 ID (현재 설정값: {config.get('streamer_id')})"
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default=config.get('output_dir', config.get('output_csv_dir', 'csv')),
        help=f"방송별 CSV 파일들이 저장될 폴더 경로 (현재 설정값: {config.get('output_dir', 'csv')})"
    )
    parser.add_argument(
        '--output_log',
        type=str,
        default=config.get('output_log', 'chat.log'),
        help=f"저장할 로그 파일 경로 (현재 설정값: {config.get('output_log')})"
    )
    parser.add_argument(
        '--check_interval',
        type=int,
        default=int(config.get('check_interval', 20)),
        help=f"오프라인 시 방송 상태 확인 주기(초, 현재 설정값: {config.get('check_interval')})"
    )
    args = parser.parse_args()

    cookies: dict[str, Any] = {}
    if os.path.exists('cookies.json'):
        try:
            with open('cookies.json', encoding='utf-8-sig') as f:
                cookies = json.load(f)
        except Exception as e:
            print(f"[경고] cookies.json 로드 실패: {e}")

    logger = get_logger(args.output_log)

    chzzkchat = ChzzkChat(
        streamer=args.streamer_id,
        cookies=cookies,
        logger=logger,
        output_dir=args.output_dir,
        check_interval=args.check_interval
    )
    chzzkchat.run()




