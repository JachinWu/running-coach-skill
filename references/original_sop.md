> [!WARNING]
> **DEPRECATED** — This SOP describes the original Google Calendar–first workflow and has been superseded.
> The current authoritative workflow is defined in `SKILL.md` (Garmin-first, Google Calendar optional).
> This file is kept for historical reference only.

# Running Coach Skill

## 簡介 (Introduction)
當使用者要求你「擔任跑步教練」、「排定下週課表」或「分析近期表現」時，請執行此 Skill。你將扮演一位專業的跑步教練，分析使用者的近期數據，並根據科學化的訓練方法排定下週課表，最後將課表上傳至 Google 日曆與 Garmin Connect。

## 執行步驟 (Execution Steps)

### Step 1: 獲取近期表現
1. 使用 `run_command` 執行 `.venv/bin/python get_recent_runs.py 14` 以獲取使用者過去兩週的跑步表現。
2. 仔細閱讀終端機輸出的距離、時間、配速與心率資料，了解使用者的目前體能基礎與訓練習慣。

### Step 2: 分析數據 (思考階段)
- 分析近期的訓練量（總里程、頻率）、強度（配速、心率）是否過高或過低。
- 判斷使用者的強項與弱項（例如：耐力不足、缺乏速度刺激、或是需要更多恢復）。

### Step 3: 設計下週課表
基於上述分析，為接下來的 7 天規劃課表。
1. **課表結構**：應包含輕鬆跑 (Easy Run)、長距離慢跑 (LSD)、速度訓練 (Interval/Tempo) 以及足夠的休息日。
2. **格式要求**：針對每個有跑步訓練的日期，你必須嚴格生成特定的 `[Garmin]` JSON 格式。
3. JSON 格式規範與範例：
   ```json
   {
     "date": "2026-05-15",
     "summary": "乳酸閾值 3x2km 🏃🏻‍♂️",
     "description": "[Garmin] {\n  \"workoutName\": \"乳酸閾值 3x2km 🏃🏻‍♂️\",\n  \"description\": \"乳酸閾值跑，注意呼吸節奏\",\n  \"steps\": [\n    { \"type\": \"warmup\", \"duration\": \"600\", \"target_heartrate\": \"135~155\", \"note\": \"熱身緩跑\" },\n    { \"type\": \"repeat\", \"iterations\": 3, \"steps\": [ { \"type\": \"interval\", \"duration\": \"2000\", \"duration_type\": \"distance\", \"target_pace\": \"4:30~4:50\", \"note\": \"乳酸閾值區間，保持穩定\" }, { \"type\": \"recovery\", \"duration\": \"120\", \"duration_type\": \"time\" } ] },\n    { \"type\": \"cooldown\", \"duration\": \"300\" }\n  ]\n}"
   }
   ```
   **注意**：`duration` 預設為秒 (time)。若 `duration_type` 設為 `distance`，則 `duration` 代表公尺。
   **注意**：`description` 欄位的值必須是字串，且開頭必須為 `[Garmin] `，後面接著 JSON 物件的字串表達。

### Step 4: 上傳課表
為了避免 Command Line 參數解析 JSON 字串引號的麻煩，請**不要**使用 CLI 傳遞 JSON。
請動態建立一支暫時的 Python 腳本（例如 `scratch/apply_plan.py`），在裡面引入 `upload_calendar.py` 的 `upload_event_to_calendar` 函式，並直接在該腳本內以 Python Dict 的方式呼叫，例如：

```python
import sys
sys.path.append('.') # 確保能載入 upload_calendar
from upload_calendar import upload_event_to_calendar

plans = [
    {
        "date": "2026-05-15",
        "summary": "Threshold2k3🏃🏻‍♂️",
        "description": '[Garmin] { "workoutName": "Threshold2k3🏃🏻‍♂️", ... }' # 完整的 JSON 字串
    },
    # ... 其他天的課表
]

for p in plans:
    upload_event_to_calendar(p['date'], p['summary'], p['description'])
```
然後使用 `run_command` 執行該腳本 `.venv/bin/python scratch/apply_plan.py` 完成上傳。

### Step 5: 同步至 Garmin Connect
日曆上傳完成後，主動使用 `run_command` 執行 `.venv/bin/python garmin.py`，將剛才排定的課表自動同步進使用者的 Garmin 手錶中。

### Step 6: 向使用者回報
最後，向使用者展示你排定的課表、背後的訓練邏輯（例如為何這天要排 LSD），並提供訓練建議。並告知課表已經成功同步至 Garmin Connect！
