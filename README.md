# Running Coach Skill | 跑步教練技能

A specialized AI running coach for analyzing data, planning workouts, and syncing directly with Garmin Connect. This skill transforms the assistant into a data-driven coach that understands your physiological state and helps you reach your racing goals.

一個專門為跑者設計的 AI 教練，具備數據分析、訓練規劃以及與 Garmin Connect 直接同步的功能。此技能將助手轉變為數據驅動的專業教練，能理解您的生理狀態並協助您達成賽事目標。

---

## Key Features | 核心功能

### 📊 Data-Driven Analysis | 數據驅動分析
- **Performance Review**: Automatically analyzes the last 14 days of running history (pace, heart rate, cadence, stride length).
- **High-Resolution Activity Charts**: Generates professional, multi-axis telemetry charts (Pace, HR, Cadence, Elevation) for every run using Matplotlib.
- **Form Analysis**: Identifies breakdown in form (cadence/stride) during high-intensity intervals.
- **成效檢視**：自動分析過去 14 天的跑步歷史（配速、心率、步頻、步幅）。
- **高解析度活動圖表**：為每次跑步自動生成專業的多軸遙測圖表（配速、心率、步頻、海拔），使用 Matplotlib 繪製。
- **跑姿分析**：識別高強度間歇訓練中後段的跑姿崩潰（步頻/步幅變化）。

### 📅 Smart Training Plans | 智能訓練計畫
- **Structured Workouts**: Generates precise workouts (Easy, Tempo, Interval, Long Run) with specific heart rate or pace targets.
- **Garmin Sync**: Automatically pushes workouts directly to Garmin Connect; no manual entry required.
- **結構化課表**：生成包含心率或配速目標的精確課表（輕鬆跑、節奏跑、間歇跑、長距離跑）。
- **Garmin 同步**：自動將課表推送到 Garmin Connect，無需手動輸入。

### 🧠 Athlete Memory & Profile | 運動員檔案與記憶
- **PB Tracking**: Keeps a history of your Personal Bests across various distances.
- **Injury Management**: Tracks injury history to adjust training intensity and prevent overtraining.
- **Physiological Trends**: Monitors VO2Max and Lactate Threshold (LTHR) progress.
- **Vector Memory Sync**: Integrates with `contextual-memory` to store long-term traits and habits.
- **PB 紀錄**：紀錄您在不同距離的個人最佳紀錄。
- **傷病管理**：追蹤傷病史以調整訓練強度，預防過度訓練。
- **生理趨勢**：監測最大攝氧量 (VO2Max) 與乳酸閥值 (LTHR) 的進展。
- **向量記憶同步**：與 `contextual-memory` 整合，儲存長期跑者特質與習慣。

### ⚡ Recovery & Readiness | 恢復與就緒度
- **HRV & Body Battery**: Integrates Garmin recovery metrics to decide if you are ready for a hard session or need a rest day.
- **HRV 與身體能量**：整合 Garmin 恢復指標，判斷您適合進行高強度訓練還是需要休息。

### 🏁 Race Goal Planning | 賽事備賽規劃
- **Daniels' Periodization**: Automatically adjusts training phases (Foundation, Early Quality, Transition, Final Quality) and paces based on Daniels' Running Formula and your target race date.
- **Training Levels**: Recommends training levels (White, Red, Blue, Gold) based on your actual 4-week mileage to prevent overtraining.
- **丹尼爾斯週期化**：根據丹尼爾斯跑步方程式與您的目標賽事日期，自動調整訓練階段（基礎期、進展期、巔峰期、減量期）與科學配速。
- **訓練分級**：根據您過去 4 週的真實跑量推薦級別（入門、中階、進階、菁英），確保訓練負荷適中。

---

## Directory Structure | 目錄結構

- `scripts/`:
  - `garmin.py`: Core utility for Garmin Connect API interactions. | Garmin Connect API 核心工具。
  - `get_recent_runs.py`: Retrieves recent activity history. | 獲取近期活動紀錄。
  - `daniels_periodization.py`: Daniels' training phases and level constants. | 丹尼爾斯週期與等級常數。
  - `daniels_formula.py`: VDOT and pace calculation engine. | VDOT 與配速計算引擎。
  - `update_profile.py`: Manages the athlete's persistent memory. | 管理運動員持久化記憶。
  - `record_insight.py`: Saves long-term insights and syncs with contextual-memory. | 儲存長期洞察並與上下文記憶同步。
  - `hrv_guardrail.py`: Proactive recovery alerts and guardrail logic. | 主動恢復預警與保護機制。
  - `visualizer.py`: Generates weekly training and recovery charts. | 生成每週訓練與恢復圖表。
  - `bot_bridge.py`: Integration layer for Telegram/Chat interfaces. | Telegram/對話介面整合層。
  - `upload_calendar.py`: Google Calendar synchronization (Optional). | Google 日曆同步（選用）。
- `data/`:
  - `athlete_profile.json`: Persistent storage for PBs, injuries, stats, and target race goals. | PB、傷病、統計數據與賽事目標的持久化存儲。
- `references/`: Detailed SOPs and implementation plans. | 詳細的 SOP 與實作計畫。

---

## Setup | 設定

1. Ensure your Garmin Connect credentials are set in your environment variables or `.env` file.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Configure Google Calendar API if calendar sync is desired.

1. 確保您的 Garmin Connect 帳密已設定於環境變數或 `.env` 檔案中。
2. 安裝依賴套件：
   ```bash
   pip install -r requirements.txt
   ```
3. （選用）若需使用日曆同步功能，請配置 Google Calendar API。

---

## Usage | 使用方式

The skill is designed to be triggered by the Gemini CLI agent. You can also run individual scripts for manual management:

此技能設計由 Gemini CLI 代理觸發。您也可以手動執行個別腳本進行管理：

- **Onboarding/Setup**: `/setup` (via Telegram) or manually via `bot_bridge`.
- **Check Profile**: `python scripts/update_profile.py show`
- **Manual Sync**: `python scripts/garmin.py --workout-json '<JSON_DATA>'`
- **View Recent Runs**: `python scripts/get_recent_runs.py`

---
*Created by Gemini-CLI Running Coach Module*
