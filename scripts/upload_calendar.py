"""upload_calendar.py — 將課表事件寫入 Google 日曆（選用功能）。

主要用途：
  1. 直接把單一課表事件上傳到 Google 日曆（--mode event）
  2. 從 Google 日曆讀取 [Garmin] 課表並同步到 Garmin Connect（--mode c2g）

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


def delete_garmin_events_on_date(service, calendar_id, date_str: str) -> None:
    """刪除指定日期上，包含 [Garmin] 標記的事件。
    使用字串比對而非 Google API 的時間範圍查詢，以避免全天事件的時區偏移誤判。
    """
    try:
        # 查詢前後三天的範圍，確保能撈到因先前時區 Bug 而偏移的事件
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        time_min = (dt - datetime.timedelta(days=2)).strftime('%Y-%m-%dT00:00:00Z')
        time_max = (dt + datetime.timedelta(days=2)).strftime('%Y-%m-%dT23:59:59Z')
        
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            q='[Garmin]',
            singleEvents=True
        ).execute()
        
        events = result.get('items', [])
        for e in events:
            # 取得該事件在 Google 日曆上的實際日期字串 (YYYY-MM-DD)
            start_info = e.get('start', {})
            event_date = start_info.get('date') or start_info.get('dateTime', '')[:10]
            
            # 只有當日期字串精確吻合，才執行刪除
            if event_date == date_str:
                summary = e.get('summary', 'Unknown')
                print(f"🗑️ 正在刪除原有 Garmin 課表: {summary} ({event_date})")
                service.events().delete(calendarId=calendar_id, eventId=e['id']).execute()
    except Exception as e:
        print(f"⚠️ 清除原有課表時發生錯誤: {e}")


# ---------------------------------------------------------------------------
# Mode 1: Upload a single event to Google Calendar
# ---------------------------------------------------------------------------

def upload_event_to_calendar(date_str: str, summary: str, description: str, replace_existing: bool = True) -> bool:
    """將單一課表事件上傳至 Google 日曆（全天事件）。

    Args:
        date_str: 日期字串，格式 YYYY-MM-DD。
        summary: 事件標題。
        description: 事件描述（建議為 [Garmin] 開頭的 JSON 字串）。
        replace_existing: 是否刪除該日期上原有的 [Garmin] 事件。

    Returns:
        True 表示成功，False 表示失敗。
    """
    service, calendar_id = _build_calendar_service(
        ['https://www.googleapis.com/auth/calendar.events'])
    if not service:
        return False

    if replace_existing:
        delete_garmin_events_on_date(service, calendar_id, date_str)

    # Google 日曆的全天事件 (all-day event) 結束日期是「不包含」(exclusive) 的。
    # 如果要設定在 5/5 當天，結束日期必須設為 5/6。
    try:
        start_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        end_dt = start_dt + datetime.timedelta(days=1)
        end_date_str = end_dt.strftime("%Y-%m-%d")
    except ValueError:
        print(f"❌ 日期格式錯誤: {date_str}")
        return False

    event = {
        'summary': summary,
        'description': description,
        'start': {'date': date_str},
        'end': {'date': end_date_str},
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

    # 讀取從昨天開始（確保涵蓋所有時區偏移後的今日事件）的課表
    # 使用 Asia/Taipei 00:00 作為基準
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%dT00:00:00+08:00')
    print(f"🤖 服務帳戶機器人出動中 (查詢起點: {yesterday})...")
    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=yesterday,
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


def sync_garmin_to_calendar() -> None:
    """從 Garmin Connect 讀取這週課表並同步到 Google 日曆。"""
    from garmin import init_api, get_upcoming_schedule

    print("\n--- 初始化 Garmin API ---")
    api = init_api()
    if not api:
        print("程式終止：無法建立 Garmin 連線")
        return

    print("🔄 正在從 Garmin 讀取這週課表...")
    schedule = get_upcoming_schedule(api)
    if not schedule:
        print("找不到任何課表項目。")
        return

    print(f"✅ 成功讀取 {len(schedule)} 天的行程。")
    
    for day in schedule:
        target_date = day['date']
        workout = day['workout']
        
        if not workout:
            # 如果是休息日，也嘗試清理 Google 日曆上可能殘留的 Garmin 事件
            service, calendar_id = _build_calendar_service(['https://www.googleapis.com/auth/calendar.events'])
            if service:
                delete_garmin_events_on_date(service, calendar_id, target_date)
            continue

        summary = workout.get("title") or workout.get("workoutName") or "跑步訓練"
        
        steps = []
        workout_id = workout.get("workoutId")
        if workout_id:
            try:
                full_workout = api.get_workout_by_id(workout_id)
                
                def parse_step(step):
                    if step.get("type") == "ExecutableStepDTO":
                        step_data = {
                            "type": step.get("stepType", {}).get("stepTypeKey", "interval")
                        }
                        
                        # Handle duration (time vs distance)
                        end_condition = step.get("endCondition", {}).get("conditionTypeKey")
                        end_val = step.get("endConditionValue")
                        if end_condition == "time" and end_val is not None:
                            step_data["duration"] = end_val
                            step_data["duration_type"] = "time"
                        elif end_condition == "distance" and end_val is not None:
                            step_data["duration"] = end_val
                            step_data["duration_type"] = "distance"
                            
                        if step.get("description"):
                            step_data["note"] = step.get("description")
                        
                        t1 = step.get("targetValueOne")
                        t2 = step.get("targetValueTwo")
                        target_type = step.get("targetType", {}).get("workoutTargetTypeKey")
                        
                        if t1 is not None and t2 is not None:
                            if target_type == "heart.rate.zone":
                                step_data["target_heartrate"] = f"{int(t1)}~{int(t2)}"
                            elif target_type == "pace.zone":
                                def speed_to_pace_str(speed_ms):
                                    if speed_ms <= 0: return "0:00"
                                    pace_sec = 1000 / speed_ms
                                    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
                                p1_str = speed_to_pace_str(t2)
                                p2_str = speed_to_pace_str(t1)
                                step_data["target_pace"] = f"{p1_str}~{p2_str}"
                        return step_data
                        
                    elif step.get("type") == "RepeatGroupDTO":
                        return {
                            "type": "repeat",
                            "iterations": step.get("numberOfIterations", 1),
                            "steps": [parse_step(s) for s in step.get("workoutSteps", []) if s]
                        }
                    return None

                for segment in full_workout.get("workoutSegments", []):
                    for step in segment.get("workoutSteps", []):
                        parsed = parse_step(step)
                        if parsed:
                            steps.append(parsed)
            except Exception as e:
                print(f"⚠️ 無法取得完整課表步驟: {e}")
        
        # 依照 original_sop.md 的規範，簡化上傳至 Google 日曆的 JSON 結構
        # 僅保留核心欄位，移除 verbose 的系統 metadata
        simple_workout = {
            "workoutName": summary,
            "description": workout.get('description') or full_workout.get('description') if workout_id else '',
            "steps": steps
        }
        
        # 將簡化後的資料封裝回 [Garmin] JSON 格式，並使用漂亮排版
        description = f"[Garmin]\n{json.dumps(simple_workout, ensure_ascii=False, indent=2)}"
        
        upload_event_to_calendar(target_date, summary, description)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """主程式，支援三種模式：

    event mode（上傳單一事件到 Google 日曆）:
        python upload_calendar.py --mode event --date YYYY-MM-DD --summary "標題" --description "[Garmin]{...}"

    c2g mode（從 Google 日曆同步 [Garmin] 課表到 Garmin Connect）:
        python upload_calendar.py --mode c2g

    g2c mode（從 Garmin Connect 同步課表到 Google 日曆）:
        python upload_calendar.py --mode g2c
    """
    parser = argparse.ArgumentParser(description="Google Calendar ↔ Garmin Connect 整合工具")
    parser.add_argument("--mode", choices=["event", "c2g", "g2c"], default="event",
                        help="event: 上傳單一事件；c2g: Google→Garmin；g2c: Garmin→Google")
    parser.add_argument("--date", help="日期 YYYY-MM-DD（event 模式必填）")
    parser.add_argument("--summary", help="事件標題（event 模式必填）")
    parser.add_argument("--description", help="事件描述，建議以 [Garmin] 開頭（event 模式必填）")
    parser.add_argument("--keep-existing", action="store_true", help="保留指定日期上原有的 [Garmin] 課表（預設為刪除並覆蓋）")
    args = parser.parse_args()

    if args.mode == "c2g":
        sync_calendar_to_garmin()
    elif args.mode == "g2c":
        sync_garmin_to_calendar()
    else:
        if not all([args.date, args.summary, args.description]):
            parser.error("event 模式需要 --date、--summary、--description 三個參數")
        upload_event_to_calendar(args.date, args.summary, args.description, replace_existing=not args.keep_existing)


if __name__ == "__main__":
    main()
