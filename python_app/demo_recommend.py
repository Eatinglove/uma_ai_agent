"""demo_recommend.py: 對目前 third-party watcher 狀態執行 recommend 並印建議。

(預設 parity 模式；加 --mcts 走 UCB 樹)
--target <距離|數值>: 目標育成數值 [速,耐,力,根,智]。
   short/mile/mid/long/max 為預設距離型, 或直接給 5 數字 "1400,800,1200,1000,1200"
   (語意=目標數值; 離目標越遠的屬性訓練價值越高, 達標後遞減至 0)

互動模式: 互動終端啟動時會詢問目標數值 (直接 Enter 沿用上次/預設 1400)。
設定會存到 state/target.json, 下次啟動自動帶入。
"""
import json
import os
import sys

import bridge

# 目標距離 → [速,耐,力,根,智] 目標數值
# 常駐預設: 五圍全 1400 (全點滿)
_DEFAULT_TARGET = [1400, 1400, 1400, 1400, 1400]
_TARGET_PRESETS = {
    "max": _DEFAULT_TARGET,
    "short": [1250, 800, 1100, 950, 1150],
    "mile":  [1200, 900, 1100, 900, 1150],
    "mid":   [1150, 1000, 1050, 850, 1100],
    "long":  [1050, 1200, 1000, 800, 1050],
}

_STAT_KEYS = ("速", "耐", "力", "根", "智")
_TARGET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "state", "target.json")


def _load_saved_target():
    try:
        with open(_TARGET_FILE, encoding="utf-8") as f:
            t = json.load(f)
        vals = [float(x) for x in t][:5]
        if len(vals) != 5:
            return None
        return vals
    except Exception:
        return None


def _save_target(t):
    try:
        os.makedirs(os.path.dirname(_TARGET_FILE), exist_ok=True)
        with open(_TARGET_FILE, "w", encoding="utf-8") as f:
            json.dump([float(x) for x in t], f)
    except Exception:
        pass


def _parse_target(raw):
    if not raw:
        return None
    raw = raw.strip()
    if raw in _TARGET_PRESETS:
        return _TARGET_PRESETS[raw]
    parts = raw.split(",")
    if len(parts) != 5:
        raise SystemExit("--target 需為 short/mile/mid/long/max 或 5 目標數值: 速,耐,力,根,智")
    try:
        return [float(p) for p in parts]
    except ValueError:
        raise SystemExit("--target 數值解析失敗")


def _prompt_target(default):
    """互動終端詢問目標數值。回傳 list 或 None(=沿用 default)。"""
    if not sys.stdin.isatty():
        return None
    pre = ", ".join(f"{k}:{v:g}" for k, v in zip(_STAT_KEYS, default))
    print("輸入目標育成數值 (速,耐,力,根,智)")
    print(f"  [預設 {pre}]  直接 Enter 沿用; 可輸入 short/mile/mid/long/max")
    try:
        raw = input("  目標數值 > ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return None
    if raw.lower() in _TARGET_PRESETS:
        return _TARGET_PRESETS[raw.lower()]
    parts = raw.split(",")
    if len(parts) != 5:
        print("  格式錯誤, 沿用預設")
        return None
    try:
        vals = [min(1400.0, max(0.0, float(p))) for p in parts]
    except ValueError:
        print("  數值錯誤, 沿用預設")
        return None
    return vals


def main():
    n = bridge.load_current_turn()
    if not n:
        print("無 current_turn.json")
        return
    # 優先: --target CLI; 其次互動輸入; 再其次已存設定; 最後預設
    target = None
    args = sys.argv[1:]
    if "--target" in args:
        i = args.index("--target")
        if i + 1 < len(args):
            target = _parse_target(args[i + 1])
    else:
        for a in args:
            if a.startswith("--target="):
                target = _parse_target(a.split("=", 1)[1])
    default = _load_saved_target() or _DEFAULT_TARGET
    if target is None:
        target = _prompt_target(default) or default
    _save_target(target)

    method = "mcts" if "--mcts" in sys.argv else "parity"
    print(f"回合 {n.get('turn')}  scenario={n.get('scenario_id')}  "
          f"心情={n.get('motivation')}  體力={n.get('vital')}/{n.get('max_vital')}  技能點={n.get('skill_point')}")
    w = ", ".join(f"{k}:{v:g}" for k, v in zip(_STAT_KEYS, target))
    print(f"目標數值: {w}")
    r = bridge.recommend(n, iterations=5000, method=method, stat_targets=target)
    best = r.get("best")
    note = r.get("note") or ""
    if best is None:
        print(f"無建議: {note}")
        return
    best_name = r.get("best_name") or bridge.ACTION_NAMES.get(best, "?")
    print(f"建議: {best_name} (action={best}, 決定依據: {note})\n")
    print(f"{'idx':>3} {'行動':<5} {'rollouts':>8} {'avg':>6} {'board':>6} {'失敗率':>6} {'等級':>3}")
    for s in r["stats"]:
        d = s.get("param_deltas") or {}
        dv = ", ".join(f"+{v}" for v in d.values() if v and v > 0) or "-"
        print(f"{s['action']:>3} {s['name']:<5} {s['visits']:>8} {s['avg']:>6} {round(s['board']):>6} "
              f"{str(s['failure_rate']):>6} {str(s['level']):>3}   {dv}")


if __name__ == "__main__":
    main()