# Running Coach Skill 實作計畫

這個計畫旨在為 Antigravity Agent 建立一個名為「跑步教練 (Running Coach)」的專屬 Skill，讓 Agent 能夠自動化完成「分析數據 -> 規劃課表 -> 上傳 Google 日曆」的完整流程。

## 背景與目標
使用者希望 Agent 能化身為專屬跑步教練。當觸發此 Skill 時，Agent 需要：
1. 獲取並分析使用者近期的跑步數據。
2. 根據數據表現與恢復狀況，給予專業建議，並排定下週的跑步課表。
3. 將課表轉化為特定的 `[Garmin] JSON` 格式。
4. 透過 Google Calendar API，自動將課表上傳至使用者的 Google 日曆。

## User Review Required

> [!IMPORTANT]
> 1. **Google Calendar 權限**：接下來的腳本會需要對你的 Google 日曆有「寫入」權限。請確保你已經到 Google 日曆的設定中，將日曆共用給 `[EMAIL_ADDRESS]` 並設定權限為 **「變更活動 (Make changes to events)」**。
> 2. **Skill 觸發方式**：這個 Skill 將會以 Markdown 文件的形式存在你的專案中。未來你只要跟我說「幫我排下週課表」，我就會讀取這個 Skill 檔案並自動執行所有流程。

## 提出的變更 (Proposed Changes)

---

### Google Calendar 上傳腳本 (Python)
為了讓 Agent 能夠將排好的課表上傳到日曆，我們需要一隻專門的 Python 腳本。

#### [NEW] `upload_calendar.py`
建立一支全新的 Python 腳本，封裝 Google Calendar API 的寫入功能。
- 讀取 `./content/credentials.json` 與 `./content/calendar_id.txt`。
- 提供一個命令列介面或函式，接收 `Date`、`Summary` 與 `Description (JSON)`。
- 使用 `SCOPES = ['https://www.googleapis.com/auth/calendar.events']` 來獲取寫入權限。
- 呼叫 `service.events().insert()` 將活動寫入 Google 日曆。

---

### Garmin 數據獲取腳本 (Python)
雖然我們有了匯出 GPX 的腳本，但對於 Agent 分析來說，直接抓取活動的「統計摘要」（如平均配速、心率、距離）會更有效率。

#### [NEW] `get_recent_runs.py`
建立一支簡單的腳本，用於抓取近兩週的跑步摘要並輸出為 Agent 容易閱讀的文字格式（包含每次跑步的日期、名稱、距離、平均心率、平均配速等）。

---

### Agent Skill 文件 (Markdown)
這是教導我（Agent）如何執行這個複雜任務的「大腦指令」。

#### [NEW] `skills/running_coach.md`
建立專屬的 Skill 檔案，定義標準作業流程 (SOP)：
1. **收集數據**：執行 `python get_recent_runs.py` 取得近期表現。
2. **分析與生成**：根據數據，使用專業跑步教練的知識庫來撰寫下週的課表。課表必須嚴格遵循使用者定義的 Garmin JSON 格式。
3. **上傳日曆**：將生成的課表，依序透過 `upload_calendar.py` 寫入到指定的日期。
4. **回報使用者**：向使用者展示排定的課表與教練建議。

## 驗證計畫 (Verification Plan)
### 手動驗證
1. 確保 `upload_calendar.py` 可以成功在你的 Google 日曆上建立一個測試事件。
2. 呼叫「執行 Running Coach Skill」，觀察 Agent 是否能順利讀取過去紀錄、輸出合法的 JSON，並將未來的課表成功推送到 Google Calendar，最後再由你執行 `python garmin.py` 驗證是否能順利同步到 Garmin Connect。
