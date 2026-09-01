import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def _clean_cookies(cookies: dict) -> dict:
    """쿠키 값 중 ASCII가 아니거나(예: '쿠키값을넣어주세요' 등) 비어있는 항목을 안전하게 제외합니다."""
    if not isinstance(cookies, dict):
        return {}
    cleaned = {}
    for k, v in cookies.items():
        if isinstance(v, str) and v:
            try:
                v.encode('ascii')
                cleaned[k] = v
            except UnicodeEncodeError:
                pass
    return cleaned

def fetch_live_status(streamer: str, cookies: dict = None) -> dict:
    """치지직 채널의 라이브 방송 상태를 안전하게 조회합니다."""
    url = f'https://api.chzzk.naver.com/polling/v2/channels/{streamer}/live-status'
    try:
        clean_c = _clean_cookies(cookies) if cookies else {}
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.json().get('content', {}) or {}
        return {
            'status': content.get('status', 'CLOSE'),
            'chatChannelId': content.get('chatChannelId'),
            'liveTitle': content.get('liveTitle', ''),
            'concurrentUserCount': content.get('concurrentUserCount', 0)
        }
    except Exception as e:
        raise e

def fetch_chatChannelId(streamer: str, cookies: dict = None) -> str:
    live_status = fetch_live_status(streamer, cookies)
    chatChannelId = live_status.get('chatChannelId')
    if not chatChannelId:
        raise ValueError(f"현재 방송 중이 아니거나 chatChannelId를 찾을 수 없습니다. (상태: {live_status.get('status')})")
    return chatChannelId

def fetch_channelName(streamer: str) -> str:
    url = f'https://api.chzzk.naver.com/service/v1/channels/{streamer}'
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response = response.json()
        return response['content']['channelName']
    except Exception as e:
        raise e

def fetch_accessToken(chatChannelId, cookies: dict = None) -> tuple:
    url = f'https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chatChannelId}&chatType=STREAMING'
    try:
        clean_c = _clean_cookies(cookies) if cookies else {}
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response = response.json()
        return response['content']['accessToken'], response['content'].get('extraToken', '')
    except Exception as e:
        raise e

def fetch_userIdHash(cookies: dict = None) -> str:
    url = 'https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus'
    try:
        clean_c = _clean_cookies(cookies) if cookies else {}
        if not clean_c:
            return ""
        response = requests.get(url, cookies=clean_c, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response = response.json()
        content = response.get('content')
        if content and 'userIdHash' in content:
            return content['userIdHash']
        return ""
    except Exception as e:
        return ""


