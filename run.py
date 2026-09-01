import argparse
import csv
import datetime
import json
import logging
import os
import time
from websocket import WebSocket

import api
from cmd_type import CHZZK_CHAT_CMD


class CsvChatLogger:
    """채팅 및 후원 내역을 CSV 파일에 실시간으로 누적(Append) 저장하는 클래스입니다."""

    def __init__(self, filepath='chat.csv'):
        self.filepath = filepath
        file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0

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

    def write_chat(self, dt_str, timestamp_ms, streamer_id, channel_name, chat_type, user_id, nickname, message):
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

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()


class ChzzkChat:

    def __init__(self, streamer, cookies, logger, csv_logger, check_interval=20):
        self.streamer = streamer
        self.cookies = cookies
        self.logger = logger
        self.csv_logger = csv_logger
        self.check_interval = check_interval

        self.sid = None
        self.sock = None
        self.chatChannelId = None
        self.channelName = None
        self.userIdHash = None
        self.accessToken = None
        self.extraToken = None

        self._init_account_info()

    def _init_account_info(self):
        try:
            self.channelName = api.fetch_channelName(self.streamer)
        except Exception as e:
            self.logger.warning(f"채널명 조회 실패: {e}")
            self.channelName = self.streamer

        try:
            self.userIdHash = api.fetch_userIdHash(self.cookies)
        except Exception as e:
            self.logger.warning(f"유저 상태(userIdHash) 조회 실패: {e}")
            self.userIdHash = ""

    def connect(self, chat_channel_id):
        self.chatChannelId = chat_channel_id
        self.accessToken, self.extraToken = api.fetch_accessToken(self.chatChannelId, self.cookies)

        sock = WebSocket()
        sock.connect('wss://kr-ss1.chat.naver.com/chat')
        self.logger.info(f"[{self.channelName}] 채팅 서버에 연결 중...")

        default_dict = {
            "ver": "2",
            "svcid": "game",
            "cid": self.chatChannelId,
        }

        send_dict = {
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
            self.logger.info(f"[{self.channelName}] 채팅창 연결 완료 (채팅 채널 ID: {self.chatChannelId})")
        else:
            raise ConnectionError("채팅 서버 연결 실패")

    def close_socket(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, message: str):
        if not self.sock or not self.sock.connected:
            self.logger.warning("채팅 서버에 연결되어 있지 않아 메시지를 전송할 수 없습니다.")
            return

        default_dict = {
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

        send_dict = {
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

    def run(self):
        self.logger.info(f"[{self.channelName}] 무중단 채팅 수집기를 시작합니다.")

        while True:
            try:
                # 1. 방송 상태 확인
                try:
                    live_status = api.fetch_live_status(self.streamer, self.cookies)
                except Exception as e:
                    self.logger.warning(f"방송 상태 조회 중 오류 발생 ({e}). {self.check_interval}초 후 재시도합니다.")
                    time.sleep(self.check_interval)
                    continue

                is_live = (live_status.get('status') == 'OPEN')
                chat_channel_id = live_status.get('chatChannelId')

                if not is_live or not chat_channel_id:
                    self.logger.info(
                        f"[{self.channelName}] 현재 방송이 꺼져 있습니다 (상태: {live_status.get('status', 'CLOSE')}). "
                        f"{self.check_interval}초 후 방송 시작 여부를 확인합니다..."
                    )
                    time.sleep(self.check_interval)
                    continue

                # 2. 방송 중인 경우 연결
                title = live_status.get('liveTitle', '')
                self.logger.info(f"[{self.channelName}] 방송 감지됨 - 제목: '{title}', 채팅 채널 ID: {chat_channel_id}")

                try:
                    self.connect(chat_channel_id)
                except Exception as e:
                    self.logger.error(f"채팅 서버 접속 실패 ({e}). 5초 후 재시도합니다.")
                    self.close_socket()
                    time.sleep(5)
                    continue

                # 3. 실시간 수신 루프
                self._listen_loop()

            except KeyboardInterrupt:
                self.logger.info("프로그램 종료 요청을 받았습니다.")
                self.close_socket()
                break
            except Exception as e:
                self.logger.error(f"예기치 못한 오류 발생: {e}. 5초 후 재시도합니다.")
                self.close_socket()
                time.sleep(5)

    def _listen_loop(self):
        while self.sock and self.sock.connected:
            try:
                raw_message = self.sock.recv()
                if not raw_message:
                    break

                raw_message = json.loads(raw_message)
                chat_cmd = raw_message.get('cmd')

                if chat_cmd == CHZZK_CHAT_CMD['ping']:
                    self.sock.send(
                        json.dumps({
                            "ver": "2",
                            "cmd": CHZZK_CHAT_CMD['pong']
                        })
                    )
                    continue

                if chat_cmd == CHZZK_CHAT_CMD['chat']:
                    chat_type = '채팅'
                elif chat_cmd == CHZZK_CHAT_CMD['donation']:
                    chat_type = '후원'
                else:
                    continue

                for chat_data in raw_message.get('bdy', []):
                    user_id = chat_data.get('uid', '')
                    if user_id == 'anonymous':
                        nickname = '익명의 후원자'
                    else:
                        try:
                            profile_data = json.loads(chat_data.get('profile', '{}'))
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

                    # 2. CSV 파일 누적 저장
                    self.csv_logger.write_chat(
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
                self.logger.warning(f"메시지 수신 중 끊김 발생 ({e}). 재연결을 시도합니다.")
                break

        self.close_socket()


def get_logger(log_path='chat.log'):
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


def load_config(config_path='config.json'):
    """설정 파일(config.json)을 로드하며, 파일이 없거나 오류 발생 시 기본값을 반환합니다."""
    default_config = {
        'streamer_id': '9381e7d6816e6d915a44a13c0195b202',
        'output_csv': 'chat.csv',
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
        description="Chzzk Chat & Donation Crawler",
        parents=[pre_parser]
    )
    parser.add_argument(
        '--streamer_id',
        type=str,
        default=config.get('streamer_id', '9381e7d6816e6d915a44a13c0195b202'),
        help=f"스트리머 고유 ID (현재 설정값: {config.get('streamer_id')})"
    )
    parser.add_argument(
        '--output_csv',
        type=str,
        default=config.get('output_csv', 'chat.csv'),
        help=f"저장할 CSV 파일 경로 (현재 설정값: {config.get('output_csv')})"
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

    cookies = {}
    if os.path.exists('cookies.json'):
        try:
            with open('cookies.json', encoding='utf-8-sig') as f:
                cookies = json.load(f)
        except Exception as e:
            print(f"[경고] cookies.json 로드 실패: {e}")

    logger = get_logger(args.output_log)
    csv_logger = CsvChatLogger(args.output_csv)

    try:
        chzzkchat = ChzzkChat(
            streamer=args.streamer_id,
            cookies=cookies,
            logger=logger,
            csv_logger=csv_logger,
            check_interval=args.check_interval
        )
        chzzkchat.run()
    finally:
        csv_logger.close()

