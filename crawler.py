import requests
from bs4 import BeautifulSoup
import json
import os
import time
import traceback
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# 환경 변수 및 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LOUNGES = {
    "WutheringWaves": {
        "name": "명조: 워더링 웨이브",
        "boards": [
            {"id": "3", "category": "커뮤니티/오프라인"},
            {"id": "28", "category": "인 게임"}
        ]
    },
    "ZZZ": {
        "name": "젠레스 존 제로",
        "boards": [
            {"id": "13", "category": "커뮤니티/오프라인"},
            {"id": "11", "category": "인 게임"}
        ]
    },
    "Trickcal": {
        "name": "트릭컬: 리바이브",
        "boards": [
            {"id": "13", "category": "전체 이벤트"}
        ]
    }
}

def get_full_text(url):
    """게시글 상세 페이지 방문하여 본문 전체 텍스트 수집"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, 'html.parser')
        content_area = soup.select_one(".se-viewer") or soup.select_one("div[class^='detail_contents']")
        if content_area:
            return content_area.get_text("\n", strip=True)
        return ""
    except Exception:
        return ""

def collect_game_data(lounge_id, info):
    """각 게임별로 최신 15개 게시글에 대해 딥 스크래핑"""
    all_game_feeds = []
    for board in info["boards"]:
        board_id = board["id"]
        url = f"https://game-api.naver.com/game/v1/lounge/{lounge_id}/feed?boardId={board_id}&page=1&pageSize=15"
        try:
            res = requests.get(url, timeout=12)
            if res.status_code != 200: continue
            data = res.json()
            feeds = data.get("contents", {}).get("feeds", [])
            for f in feeds:
                f_id = f.get('feed', {}).get('feedId')
                if not f_id: continue
                
                link = f"https://game.naver.com/lounge/{lounge_id}/board/detail/{f_id}"
                print(f"[SCAN] {info['name']} 정밀 스캔 중: {f['feed'].get('title', '제목없음')[:20]}...")
                full_text = get_full_text(link)
                
                all_game_feeds.append({
                    "game": info["name"],
                    "title": f['feed'].get('title', '제목없음'),
                    "link": link,
                    "full_text": full_text
                })
                time.sleep(0.3)
        except Exception:
            traceback.print_exc()
    return all_game_feeds

def analyze_game_events(game_name, raw_data, ai_model):
    """AI를 이용한 이벤트 데이터 정밀 분석"""
    if not ai_model or not raw_data:
        return []

    prompt = f"""
너는 게임 데이터 분석 전문가야. 제공된 '{game_name}'의 전체 본문 데이터를 기반으로 현재 진행 중인 한정 이벤트 정보를 JSON 배열로 반환해.

### 데이터 (본문 전체):
{json.dumps(raw_data, ensure_ascii=False)}

### 🔍 초정밀 추출 및 분류 규칙:
1. **오늘 날짜**: {datetime.now().strftime('%Y-%m-%d')}
2. **카테고리 분류**: '커뮤니티', '오프라인', '인 게임' 중 하나로 분류.
   - 캐릭터/무기 모집, 버전 소식, 인게임 미니게임 등은 '인 게임'으로 분류.
3. **날짜 강제 추출**: 
   - 형식: "X월 X일 00:00 ~ X월 X일 00:00"
4. **포함/제외**: 기간 한정 이벤트, 캐릭터 모집은 포함하고 단순 출석/접속 보상은 제외. 이미 종료된 이벤트는 무조건 삭제.
5. **상태**: 오늘 기준 종료까지 3일 이내 마감이면 `is_urgent: true`.

### ✍️ 출력 형식 (반드시 JSON 배열만 출력):
[
  {{
    "game": "{game_name}",
    "category": "...",
    "title": "...",
    "period": "...",
    "lounge_link": "...",
    "web_link": "...",
    "is_urgent": true/false
  }}
]
"""
    try:
        response = ai_model.generate_content(prompt)
        res_text = response.text.strip()
        if "```" in res_text:
            res_text = res_text.split("```")[1]
            if res_text.lower().startswith("json"):
                res_text = res_text[4:]
        res_text = res_text.strip()
        events = json.loads(res_text)
        print(f"[AI] {game_name} 분석 완료: {len(events)}개 추출")
        return events
    except Exception:
        print(f"[ERROR] {game_name} AI 분석 실패")
        return []

def save_to_excel(events, filename="temp_events.xlsx"):
    """수집된 이벤트를 엑셀 파일로 저장"""
    if not events:
        print(f"[ERROR] 저장할 데이터가 없습니다.")
        return
    
    df = pd.DataFrame(events)
    # 컬럼 순서 조정
    columns = ["game", "category", "title", "period", "lounge_link", "web_link", "is_urgent"]
    df = df[columns]
    
    df.to_excel(filename, index=False)
    print(f"[SUCCESS] 데이터가 {filename}에 저장되었습니다.")

if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        print("[ERROR] GOOGLE_API_KEY 없음")
        exit(1)

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = None
        for m_name in ['gemini-2.0-flash', 'gemini-pro-latest', 'gemini-flash-latest']:
            try:
                temp_model = genai.GenerativeModel(m_name)
                temp_model.generate_content("test", generation_config={"max_output_tokens": 1})
                model = temp_model
                break
            except: continue

        if not model:
            print("[ERROR] AI 모델 연결 실패")
            exit(1)

        final_all_events = []
        for lounge_id, info in LOUNGES.items():
            print(f"[INFO] {info['name']} 데이터 수집 중...")
            raw_data = collect_game_data(lounge_id, info)
            if raw_data:
                game_events = analyze_game_events(info['name'], raw_data, model)
                final_all_events.extend(game_events)
            time.sleep(1)

        save_to_excel(final_all_events)
        print("[DONE] 모든 크롤링 작업 완료!")
        
    except Exception:
        traceback.print_exc()
        exit(1)
