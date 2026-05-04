"""update_profile.py — CLI tool for the Gemini running-coach agent to update athlete profile.

Usage examples (called by the agent via run_command / shell):

  # Record a new PB
  python scripts/update_profile.py pb --distance 10k --time 47:32 --date 2026-05-01 --race "天母路跑"

  # Record an injury
  python scripts/update_profile.py injury --description "左膝髂脛束症候群" --notes "下坡時疼痛"

  # Resolve an injury (by id)
  python scripts/update_profile.py resolve-injury --id 1 --notes "已恢復，可正常跑"

  # Add a coaching note (agent observation)
  python scripts/update_profile.py note --text "使用者反映這週睡眠不足，HRV 偏低"

  # Record a milestone
  python scripts/update_profile.py milestone --description "首次完成 30km long run"

  # Print current profile summary
  python scripts/update_profile.py show
"""

import argparse
import sys
from pathlib import Path



try:
    from athlete_profile import (  # type: ignore[import]
        update_pb,
        add_injury,
        resolve_injury,
        add_coaching_note,
        add_milestone,
        add_physiology_record,
        format_profile_summary,
        load_profile,
    )
except ImportError as e:
    print(f"❌ 無法載入 athlete_profile 模組（請確認從正確路徑執行）：{e}")
    sys.exit(1)


def cmd_pb(args: argparse.Namespace) -> None:
    """Handle 'pb' subcommand."""
    try:
        entry = update_pb(
            distance=args.distance,
            time=args.time,
            date=getattr(args, "date", None),
            race=getattr(args, "race", None),
        )
        print(f"✅ PB 已更新：{args.distance} — {entry['time']}（{entry['date']}）")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_injury(args: argparse.Namespace) -> None:
    """Handle 'injury' subcommand."""
    entry = add_injury(
        description=args.description,
        notes=getattr(args, "notes", "") or "",
        start_date=getattr(args, "date", None),
    )
    print(f"✅ 傷況已記錄 (ID:{entry['id']})：{entry['description']}（{entry['start_date']}）")


def cmd_resolve_injury(args: argparse.Namespace) -> None:
    """Handle 'resolve-injury' subcommand."""
    result = resolve_injury(
        injury_id=args.id,
        notes=getattr(args, "notes", "") or "",
    )
    if result:
        print(f"✅ 傷況已標記為恢復 (ID:{args.id})：{result['description']}")
    else:
        print(f"❌ 找不到 ID={args.id} 的傷況記錄")
        sys.exit(1)


def cmd_note(args: argparse.Namespace) -> None:
    """Handle 'note' subcommand."""
    add_coaching_note(args.text)
    print(f"✅ 教練備忘已記錄：{args.text[:60]}{'…' if len(args.text) > 60 else ''}")


def cmd_milestone(args: argparse.Namespace) -> None:
    """Handle 'milestone' subcommand."""
    add_milestone(args.description)
    print(f"✅ 里程碑已記錄：{args.description}")


def cmd_physiology(args: argparse.Namespace) -> None:
    """Handle 'physiology' subcommand."""
    entry = add_physiology_record(
        vo2max=args.vo2max,
        lthr=args.lthr,
        lt_pace=getattr(args, "lt_pace", None),
        date=getattr(args, "date", None),
    )
    print(f"✅ 生理數據已記錄 ({entry['date']})：VO2Max={entry['vo2max']} / LTHR={entry['lthr']} / 閾值配速={entry['lt_pace']}")


def cmd_show(_args: argparse.Namespace) -> None:
    """Handle 'show' subcommand."""
    print(format_profile_summary())


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="更新運動員個人檔案（供 Gemini 教練 agent 使用）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # pb
    pb_p = sub.add_parser("pb", help="記錄個人最佳成績")
    pb_p.add_argument("--distance", required=True, help="距離（5k/10k/half/marathon）")
    pb_p.add_argument("--time", required=True, help="完賽時間（e.g. 47:32 / 1:52:10）")
    pb_p.add_argument("--date", default=None, help="日期 YYYY-MM-DD（預設今天）")
    pb_p.add_argument("--race", default=None, help="賽事名稱（選填）")

    # injury
    inj_p = sub.add_parser("injury", help="記錄傷況")
    inj_p.add_argument("--description", required=True, help="傷況描述")
    inj_p.add_argument("--notes", default="", help="補充說明（選填）")
    inj_p.add_argument("--date", default=None, help="開始日期 YYYY-MM-DD（預設今天）")

    # resolve-injury
    res_p = sub.add_parser("resolve-injury", help="標記傷況已恢復")
    res_p.add_argument("--id", type=int, required=True, help="傷況 ID")
    res_p.add_argument("--notes", default="", help="恢復備注（選填）")

    # note
    note_p = sub.add_parser("note", help="新增教練備忘")
    note_p.add_argument("--text", required=True, help="備忘內容")

    # milestone
    ms_p = sub.add_parser("milestone", help="記錄訓練里程碑")
    ms_p.add_argument("--description", required=True, help="里程碑描述")

    # physiology
    phys_p = sub.add_parser("physiology", help="記錄生理數據 (VO2Max/LTHR)")
    phys_p.add_argument("--vo2max", type=float, default=None, help="最大攝氧量 (例如 54.0)")
    phys_p.add_argument("--lthr", type=int, default=None, help="乳酸閾值心率 (例如 170)")
    phys_p.add_argument("--lt-pace", default=None, help="乳酸閾值配速 (例如 4:30)")
    phys_p.add_argument("--date", default=None, help="日期 YYYY-MM-DD（預設今天）")

    # show
    sub.add_parser("show", help="顯示目前個人檔案摘要")

    return parser


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "pb": cmd_pb,
        "injury": cmd_injury,
        "resolve-injury": cmd_resolve_injury,
        "note": cmd_note,
        "milestone": cmd_milestone,
        "physiology": cmd_physiology,
        "show": cmd_show,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
