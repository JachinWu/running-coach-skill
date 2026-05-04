"""upload_calendar.py — 將課表事件寫入 Google 日曆（選用功能）。

主要用途：
  1. 直接把單一課表事件上傳到 Google 日曆（--mode event）
  2. 從 Google 日曆讀取 [Garmin] 課表並同步到 Garmin Connect（--mode sync）

預設工作流程不需要此腳本；只有使用者明確要求 Google Calendar 整合時才使用。
"""
import os
import sys
import json
import datetime
import argparse
from pathlib import Path

from dotenv import load_dotenv
env_path = Path(__file__).resolve().parents[4] / ".env"
load_dotenv(dotenv_path=env_path)

from google.oauth2 import service_account
from googleapiclient.discovery import build


# ---------------------------------------------------------------------------
# Google Calendar helpers
# ---------------------------------------------------------------------------

def get_google_calendar_credentials() -> tuple[dict | None, str | None]:
    """取得 Google Calendar 服務帳戶憑證與日曆 ID。

    讀取順序：
    1. .env 中的 GOOGLE_CALENDAR_CREDENTIALS (JSON 字串) + RUNNING_CALENDAR_ID
    2. Colab Secrets 'bot-key' + 'calender-id'

    Returns:
        (service_account_info dict, calendar_id str)，失敗時回傳 (None, None)。
    """
    calendar_id = os.getenv('RUNNING_CALENDAR_ID')
    env_creds = os.getenv('GOOGLE_CALENDAR_CREDENTIALS')
    if env_creds and calendar_id:
        try:
            return json.loads(env_creds), calendar_id
        except json.JSONDecodeError:
            print("⚠️ 環境變數 GOOGLE_CALENDAR_CREDENTIALS 格式錯誤，應為 JSON 字串。")

    try:
        from google.colab import userdata  # type: ignore
        bot_key = userdata.get('bot-key')
        colab_calendar_id = userdata.get('calender-id')
        if bot_key and colab_calendar_id:
            try:
                return json.loads(bot_key), colab_calendar_id
            except json.JSONDecodeError:
                print("⚠️ Colab Secret 'bot-key' 格式錯誤，應為 JSON 字串。")
    except ImportError:
        pass

    print("⚠️ 找不到 Google 日曆憑證或 Calendar ID。")
    print("請確認 .env 中已設定 GOOGLE_CALENDAR_CREDENTIALS 與 RUNNING_CALENDAR_ID。")
    return None, None


def _build_calendar_service(scopes: list[str]):
    """建立並回傳 Google Calendar API service 物件。"""
    service_account_info, calendar_id = get_google_calendar_credentials()
    if not service_account_info or not calendar_id:
        return None, None
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)
    return service, calendar_id


# ---------------------------------------------------------------------------
# Mode 1: Upload a single event to Google Calendar
# ---------------------------------------------------------------------------

def upload_event_to_calendar(date_str: str, summary: str, description: str) -> bool:
    """將單一課表事件上傳至 Google 日曆（全天事件）。

    Args:
        date_str: 日期字串，格式 YYYY-MM-DD。
        summary: 事件標題。
        description: 事件描述（建議為 [Garmin] 開頭的 JSON 字串）。

    Returns:
        True 表示成功，False 表示失敗。
    """
    service, calendar_id = _build_calendar_service(
        ['https://www.googleapis.com/auth/calendar.events'])
    if not service:
        return False

    event = {
        'summary': summary,
        'description': description,
        'start': {'date': date_str, 'timeZone': 'Asia/Taipei'},
        'end': {'date': date_str, 'timeZone': 'Asia/Taipei'},
    }

    try:
        print(f"🔄 正在上傳至 Google 日曆 ({date_str}): {summary}")
        result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"✅ 上傳成功！Event ID: {result.get('id')}")
        return True
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")
        return False


# ---------------------------------------------------------------------------
# Mode 2: Sync [Garmin] events from Google Calendar → Garmin Connect
# ---------------------------------------------------------------------------

def fetch_garmin_calendar_events() -> list[dict] | None:
    """從 Google 日曆讀取包含 [Garmin] 標籤的未來課表事件。

    Returns:
        Google Calendar event 字典列表，失敗時回傳 None。
    """
    service, calendar_id = _build_calendar_service(
        ['https://www.googleapis.com/auth/calendar.events.readonly'])
    if not service:
        return None

    now = datetime.datetime.now(datetime.UTC).isoformat()
    print("🤖 服務帳戶機器人出動中...")
    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            q='[Garmin]',
            singleEvents=True,
            orderBy='startTime',
        ).execute()
        events = result.get('items', [])
        if not events:
            print("❌ 找不到 [Garmin] 課表。請確認：1. 日曆已分享給機器人 2. calendarId 正確")
        else:
            print(f"✅ 成功找到 {len(events)} 個課表！")
            for e in events:
                print(f"  📌 {e['summary']}")
        return events
    except Exception as e:
        print(f"❌ 讀取日曆時發生錯誤：{e}")
        return None


def parse_calendar_events(events: list[dict]) -> list[dict]:
    """將 Google 日曆事件解析為 upload_and_replace_workout 可接受的課表字典列表。

    只處理 description 以 '[Garmin]' 開頭且內容為合法 JSON 的事件。

    Args:
        events: Google Calendar event 字典列表。

    Returns:
        解析後的課表字典列表，每項包含 'date' 與 'google_summary' 欄位。
    """
    parsed = []
    for event in events:
        desc = event.get('description', '')
        if not desc.startswith('[Garmin]'):
            continue
        json_str = desc.replace('[Garmin]', '').strip()
        try:
            workout = json.loads(json_str)
            start_info = event.get('start', {})
            if 'date' in start_info:
                target_date = start_info['date']
            elif 'dateTime' in start_info:
                target_date = start_info['dateTime'][:10]
            else:
                continue
            workout['date'] = target_date
            workout['google_summary'] = event.get('summary', 'Unknown')
            parsed.append(workout)
        except json.JSONDecodeError:
            print(f"⚠️ 略過非 JSON 項目: {event.get('summary')}")
    return parsed


def sync_calendar_to_garmin() -> None:
    """從 Google 日曆讀取 [Garmin] 課表並同步至 Garmin Connect。"""
    # 延遲 import，避免非 sync 模式也需要 garmin 依賴
    from garmin import init_api, upload_and_replace_workout

    events = fetch_garmin_calendar_events()
    if not events:
        return

    parsed = parse_calendar_events(events)
    if not parsed:
        print("沒有找到需要同步的有效課表（需符合 JSON 格式）。")
        return

    print("\n--- 初始化 Garmin API ---")
    api = init_api()
    if not api:
        print("程式終止：無法建立 Garmin 連線")
        return

    print(f"\n--- 開始同步 {len(parsed)} 筆課表至 Garmin ---")
    for workout in parsed:
        upload_and_replace_workout(api, workout)
    print("--- 同步完成 ---")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """主程式，支援兩種模式：

    event mode（上傳單一事件到 Google 日曆）:
        python upload_calendar.py --mode event --date YYYY-MM-DD --summary "標題" --description "[Garmin]{...}"

    sync mode（從 Google 日曆同步 [Garmin] 課表到 Garmin Connect）:
        python upload_calendar.py --mode sync
    """
    parser = argparse.ArgumentParser(description="Google Calendar ↔ Garmin Connect 整合工具")
    parser.add_argument("--mode", choices=["event", "sync"], default="event",
                        help="event: 上傳單一事件到 Google 日曆；sync: 從 Google 日曆同步課表到 Garmin Connect")
    parser.add_argument("--date", help="日期 YYYY-MM-DD（event 模式必填）")
    parser.add_argument("--summary", help="事件標題（event 模式必填）")
    parser.add_argument("--description", help="事件描述，建議以 [Garmin] 開頭（event 模式必填）")
    args = parser.parse_args()

    if args.mode == "sync":
        sync_calendar_to_garmin()
    else:
        if not all([args.date, args.summary, args.description]):
            parser.error("event 模式需要 --date、--summary、--description 三個參數")
        upload_event_to_calendar(args.date, args.summary, args.description)


if __name__ == "__main__":
    main()
