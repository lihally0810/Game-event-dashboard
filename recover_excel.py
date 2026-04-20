import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import os
import time
from datetime import datetime

LOUNGES = {
    "WutheringWaves": {
        "name": "명조",
        "boards": [{"id": "3", "cat": "커뮤니티"}, {"id": "28", "cat": "인 게임"}]
    },
    "ZZZ": {
        "name": "젠레스",
        "boards": [{"id": "13", "cat": "커뮤니티"}, {"id": "11", "cat": "인 게임"}]
    },
    "Trickcal": {
        "name": "트릭컬",
        "boards": [{"id": "13", "cat": "전체"}]
    }
}

def get_end_date(text):
    """본문에서 종료일로 추정되는 날짜 탐색"""
    # MM.DD 또는 MM/DD 형식 탐색 (후반부 날짜 위주)
    date_patterns = [
        r'~\s*(\d{1,2})[./](\d{1,2})',
        r'종료\s*:\s*(\d{1,2})[./](\d{1,2})',
        r'까지\s*(\d{1,2})[./](\d{1,2})'
    ]
    for pattern in date_patterns:
        match = re.findall(pattern, text)
        if match:
            # 가장 마지막에 등장하는 날짜를 종료일로 가정
            m, d = match[-1]
            return f"{int(m):02d}.{int(d):02d} 23:59"
    return "05.01 23:59" # 기본값

def recover_data():
    all_events = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    print("[Recovery] 실시간 이벤트 데이터 재수집 시작...")
    
    for lounge_id, info in LOUNGES.items():
        game_name = info["name"]
        for board in info["boards"]:
            url = f"https://game-api.naver.com/game/v1/lounge/{lounge_id}/feed?boardId={board['id']}&page=1&pageSize=15"
            try:
                res = requests.get(url, timeout=10)
                if res.status_code != 200: continue
                feeds = res.json().get("contents", {}).get("feeds", [])
                
                for f in feeds:
                    title = f['feed'].get('title', '')
                    # 이벤트성 게시글만 필터링
                    if not any(k in title for k in ['이벤트', '모집', '쿠폰', '기념', '안내', '출시', '공지']):
                        continue
                    
                    f_id = f['feed'].get('feedId')
                    link = f"https://game.naver.com/lounge/{lounge_id}/board/detail/{f_id}"
                    
                    # 본문 스캔 (종료일 추정용)
                    content_res = requests.get(link, headers=headers, timeout=10)
                    end_date_str = "05.01 23:59"
                    if content_res.status_code == 200:
                        end_date_str = get_end_date(content_res.text)
                    
                    all_events.append({
                        "게임": game_name,
                        "카테고리": "쿠폰" if "쿠폰" in title else board["cat"],
                        "제목": title,
                        "기간": f"{datetime.now().strftime('%m.%d')} ~ {end_date_str}",
                        "공지링크": link,
                        "이벤트링크": "",
                        "마감임박": False
                    })
                    print(f"  > 수집 완료: [{game_name}] {title[:25]}...")
                    time.sleep(0.1)
            except: pass

    if all_events:
        df = pd.DataFrame(all_events)
        df.to_excel("events.xlsx", index=False)
        print(f"\n[Success] 총 {len(all_events)}개의 이벤트를 복구하여 events.xlsx에 저장했습니다.")
    else:
        print("\n[Fail] 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    recover_data()
