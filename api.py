from typing import Any
import requests

HEADERS: dict[str, str] = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def _clean_cookies(cookies: dict[str, Any] | None) -> dict[str, str]:
    """쿠키 값 중 ASCII가 아니거나(예: '쿠키값을넣어주세요' 등) 비어있는 항목을 안전하게 제외합니다."""
    if not isinstance(cookies, dict):
        return {}
    cleaned: dict[str, str] = {}
    for k, v in cookies.items():
        if isinstance(v, str) and v:
            try:
                v.encode('ascii')
                cleaned[k] = v
            except UnicodeEncodeError:
                pass
    return cleaned


def fetch_live_status(streamer: str, cookies: dict[str, Any] | None = None) -> dict[str, Any]:
    """치지직 채널의 라이브 방송 상태를 안전하게 조회합니다."""
    url = f'https://api.chzzk.naver.com/polling/v2/channels/{streamer}/live-status'
    try:
        clean_c = _clean_cookies(cookies)
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.json().get('content', {}) or {}
        return {
            'status': content.get('status', 'CLOSE'),
            'chatChannelId': content.get('chatChannelId'),
            'liveTitle': content.get('liveTitle', ''),
            'openDate': content.get('openDate', ''),
            'concurrentUserCount': content.get('concurrentUserCount', 0)
        }
    except Exception as e:
        raise e



def fetch_chatChannelId(streamer: str, cookies: dict[str, Any] | None = None) -> str:
    """치지직 채널의 채팅 채널 ID를 조회합니다."""
    live_status = fetch_live_status(streamer, cookies)
    chatChannelId = live_status.get('chatChannelId')
    if not chatChannelId:
        raise ValueError(f"현재 방송 중이 아니거나 chatChannelId를 찾을 수 없습니다. (상태: {live_status.get('status')})")
    return chatChannelId


def fetch_channelName(streamer: str) -> str:
    """치지직 스트리머의 채널명을 조회합니다."""
    url = f'https://api.chzzk.naver.com/service/v1/channels/{streamer}'
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        return response_data['content']['channelName']
    except Exception as e:
        raise e


def fetch_accessToken(chatChannelId: str, cookies: dict[str, Any] | None = None) -> tuple[str, str]:
    """채팅 웹소켓 접속용 accessToken 및 extraToken을 발급받습니다."""
    url = f'https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chatChannelId}&chatType=STREAMING'
    try:
        clean_c = _clean_cookies(cookies)
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        return response_data['content']['accessToken'], response_data['content'].get('extraToken', '')
    except Exception as e:
        raise e


def fetch_userIdHash(cookies: dict[str, Any] | None = None) -> str:
    """네이버 로그인 유저의 userIdHash를 조회합니다."""
    url = 'https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus'
    try:
        clean_c = _clean_cookies(cookies)
        if not clean_c:
            return ""
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        content = response_data.get('content')
        if content and 'userIdHash' in content:
            return content['userIdHash']
        return ""
    except Exception:
        return ""



