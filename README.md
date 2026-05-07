# Running Coach Skill | 跑步教練技能

A specialized AI running coach for analyzing data, planning workouts, and syncing directly with Garmin Connect. This skill transforms the assistant into a data-driven coach that understands your physiological state and helps you reach your racing goals.

一個專門為跑者設計的 AI 教練，具備數據分析、訓練規劃以及與 Garmin Connect 直接同步的功能。此技能將助手轉變為數據驅動的專業教練，能理解您的生理狀態並協助您達成賽事目標。

---

## Key Features | 核心功能

### 📊 Data-Driven Analysis | 數據驅動分析
- **Performance Review**: Automatically analyzes the last 14 days of running history (pace, heart rate, cadence, stride length).
- **Form Analysis**: Identifies breakdown in form (cadence/stride) during high-intensity intervals.
- **成效檢視**：自動分析過去 14 天的跑步歷史（配速、心率、步頻、步幅）。
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
- **PB 紀錄**：紀錄您在不同距離的個人最佳紀錄。
- **傷病管理**：追蹤傷病史以調整訓練強度，預防過度訓練。
- **生理趨勢**：監測最大攝氧量 (VO2Max) 與乳酸閥值 (LTHR) 的進展。

### ⚡ Recovery & Readiness | 恢復與就緒度
- **HRV & Body Battery**: Integrates Garmin recovery metrics to decide if you are ready for a hard session or need a rest day.
- **HRV 與身體能量**：整合 Garmin 恢復指標，判斷您適合進行高強度訓練還是需要休息。

### 🏁 Race Goal Planning | 賽事備賽規劃
- **Periodization**: Automatically adjusts training phases (Base, Build, Peak, Taper) based on your target race date.
- **週期化訓練**：根據您的目標賽事日期，自動調整訓練階段（基礎期、建量期、強化期、減量期）。

---

## Directory Structure | 目錄結構

- `scripts/`:
  - `garmin.py`: Core utility for Garmin Connect API interactions. | Garmin Connect API 核心工具。
  - `get_recent_runs.py`: Retrieves recent activity history. | 獲取近期活動紀錄。
  - `update_profile.py`: Manages the athlete's persistent memory. | 管理運動員持久化記憶。
  - `bot_bridge.py`: Integration layer for Telegram/Chat interfaces. | Telegram/對話介面整合層。
  - `upload_calendar.py`: Google Calendar synchronization (Optional). | Google 日曆同步（選用）。
- `data/`:
  - `athlete_profile.json`: Persistent storage for PBs, injuries, and stats. | PB、傷病與統計數據的持久化存儲。
  - `race_goal.json`: Storage for current target race information. | 當前目標賽事資訊存儲。
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

- **Check Profile**: `python scripts/update_profile.py show`
- **Manual Sync**: `python scripts/garmin.py --workout-json '<JSON_DATA>'`
- **View Recent Runs**: `python scripts/get_recent_runs.py`

---
*Created by Gemini-CLI Running Coach Module*
