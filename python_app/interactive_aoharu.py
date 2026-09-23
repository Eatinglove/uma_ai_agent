"""interactive_aoharu.py: 手動操作アオハル盃模擬環境

用法:
  python interactive_aoharu.py            全新一局 (隨機種子)
  python interactive_aoharu.py --seed 7   全新一局 (指定種子)
  python interactive_aoharu.py --live     接著實戰 watcher state (current_turn.json) 繼續玩
  python interactive_aoharu.py --auto "3,0,2,5,0"   自動跑一串行動 (冒煙測試用)

每回合顯示與實戰相同視角的狀態:
  - 白箭頭 / 魂爆標記(soul) / 極爆標記(sp) 對應 watcher marks 格式
  - 訓練欄: 卡片·NPC·理事長·記者 出席 + 白箭頭成員 (渦條) + 爆発標記
  - 部活成員: 渦條進度 / 爆發履歴 (未爆/魂爆済/極爆済)
指令:
  0 速度  1 耐力  2 力量  3 根性  4 智力  5 休息  6 外出  7 比賽(可用時)
  s  重印目前棋盤         w  印 watcher 格式標記陣列
  d N  部活成員 N 明細     q  結束
"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulator import (GameState, legalActions, applyAction, _aoharu_member_meta)
import bridge

STAT_KEYS = ("速", "耐", "力", "根", "智")
MOOD = {1: "絶不調", 2: "不調", 3: "普通", 4: "好調", 5: "絶好調"}


def _name(s, pid):
    if pid < 0:
        return None
    if pid < 6:
        return chr(ord("A") + pid)
    if pid == 6:
        return "理事長"
    if pid == 7:
        return "記者"
    if pid == 8:
        return "NPC"
    if pid >= 10:
        return _aoharu_member_meta(pid - 10)["name"]
    return f"?{pid}"


def _gauge_bar(v, cap=5):
    return "▮" * v + "▯" * (cap - v) if v <= cap else "▮" * cap + "×"


def _stage(idx, s):
    b, p = s.aoharuMemberBurst[idx], s.aoharuMemberPolar[idx]
    if p:
        return "極爆済"
    if b:
        return "魂爆済"
    return "未爆"


def snapshot(s):
    return {
        "stats": list(s.stats),
        "skillPt": s.skillPt,
        "stamina": s.stamina,
        "maxVital": int(s.maxVital),
        "mood": s.mood,
        "burstCnt": s.aoharuBurstCount,
        "rank": s.aoharuTeamRank,
        "gauge": list(s.aoharuMemberGauge),
        "burst": list(s.aoharuMemberBurst),
        "polar": list(s.aoharuMemberPolar),
    }


def marks_view(s):
    guide = {}
    soul = {}
    sp = {}
    for col in range(5):
        g = [p - 10 for p in s.personDist[col] if p >= 10]
        if g:
            guide[str(col)] = g
        if s.aoharuSoulDict[col]:
            soul[str(col)] = list(s.aoharuSoulDict[col])
        if s.aoharuSPDict[col]:
            sp[str(col)] = list(s.aoharuSPDict[col])
    return {"guide": guide, "soul": soul, "sp": sp}


def render(s):
    L = []
    L.append("═" * 62)
    L.append(f"ターン {s.turn}  体力 {int(s.stamina)}/{s.maxVital}  調子 {s.mood} "
             f"({MOOD.get(s.mood, '?')})  スキルPt {int(s.skillPt)}  "
             f"チームランク {s.aoharuTeamRank}")
    L.append("育成馬 " + "  ".join(f"{k}{int(v):d}" for k, v in zip(STAT_KEYS, s.stats)))
    L.append(f"累計爆発 {s.aoharuBurstCount}  會員爆発履歴: " + "  ".join(
        f"M{i}:{_stage(i, s)}" for i in range(len(s.aoharuMemberActive)) if s.aoharuMemberActive[i]))
    L.append("-" * 62)
    for col in range(5):
        present = [_name(s, p) for p in s.personDist[col] if p >= 0]
        present = " ".join(present) if present else "―"
        lvl = s.getTrainingLevel(col)
        tv = s.trainValue[col]
        val = " ".join(f"{k}+{max(int(v),0):d}" for k, v in zip(STAT_KEYS, tv[:5]) if v > 0) or "―"
        arrow = []
        for p in s.personDist[col]:
            if p >= 10:
                idx = p - 10
                arrow.append(f"{_aoharu_member_meta(idx)['name']}(渦{_gauge_bar(s.aoharuMemberGauge[idx])})")
        mark = ""
        if s.aoharuSoulDict[col]:
            mark += "  ●魂爆[" + ",".join(f"M{i}" for i in s.aoharuSoulDict[col]) + "]"
        if s.aoharuSPDict[col]:
            mark += "  ★極爆[" + ",".join(f"M{i}" for i in s.aoharuSPDict[col]) + "]"
        extra = "  [!]力+SP" if tv[5] > 0 else ""
        L.append(f"[{col}] {STAT_KEYS[col]}訓練 Lv{lvl}  失敗{s.failRate[col]}%"
                 f"  體力消費{s.trainVitalChange[col]}")
        L.append(f"    出席: {present}")
        L.append(f"    效果: {val}{extra}{mark}")
        if arrow:
            L.append("    白箭頭: " + "  ".join(arrow))
    L.append("═" * 62)
    return "\n".join(L)


def render_member(s, idx):
    if not (0 <= idx < len(s.aoharuMemberActive)) or not s.aoharuMemberActive[idx]:
        return f"M{idx}: 無此會員"
    meta = _aoharu_member_meta(idx)
    g = s.aoharuMemberGauge[idx]
    st = s.aoharuMemberStat[idx]
    return (f"M{idx} {meta['name']}  屬性={STAT_KEYS[meta['type']]} deYiLv={meta['deYiLv']}\n"
            f"  渦 {g}/5 {_gauge_bar(g)}  {_stage(idx, s)}  累計特訓成長: "
            + " ".join(f"{k}{int(v):d}" for k, v in zip(STAT_KEYS, st)))


def render_outcome(before, after, action_name):
    lines = []
    head = f"▶ {action_name}"
    stats0, stats1 = before["stats"], after["stats"]
    dv = [a - b for a, b in zip([int(x) for x in stats1],
                                [int(x) for x in stats0])]
    if any(dv):
        head += "  " + " ".join(f"{k}{'+' if v>0 else ''}{v:d}" for k, v in zip(STAT_KEYS, dv))
    sp = int(after["skillPt"]) - int(before["skillPt"])
    if sp:
        head += f"  SP{'+' if sp>0 else ''}{sp:d}"
    st = int(after["stamina"]) - int(before["stamina"])
    if st:
        head += f"  体力{'+' if st>0 else ''}{st:d}" + f"(→{int(after['stamina'])}/{after['maxVital']})"
    mo = after["mood"] - before["mood"]
    if mo:
        head += f"  調子{'+' if mo>0 else ''}{mo}"
    rk = after["rank"] - before["rank"]
    if rk:
        head += f"  チームランク{'+' if rk>0 else ''}{rk}"
    bc = after["burstCnt"] - before["burstCnt"]
    if bc:
        head += f"  ★爆発+{bc}★"
    lines.append(head)
    for i in range(len(before["gauge"])):
        dg = after["gauge"][i] - before["gauge"][i]
        db = after["burst"][i] - before["burst"][i]
        dp = after["polar"][i] - before["polar"][i]
        if not before["gauge"] or not before["burst"]:
            continue
        if dg or db or dp:
            d = f"M{i} {_aoharu_member_meta(i)['name']} 渦{before['gauge'][i]}→{after['gauge'][i]}"
            if db:
                d += " 【魂爆発!!】"
            if dp:
                d += " 【極・アオハル魂爆発!!】"
            if dg < 0:
                d += "  (渦降?!)"
            lines.append(f"    {d}")
    return "\n".join(lines)


def make_initial(live, seed):
    if live:
        norm = bridge.load_current_turn()
        if not norm:
            print("無 current_turn.json (需 third-party watcher 正常連線)")
            sys.exit(1)
        s = bridge.build_game_state(norm)
        print(f"[live] 繼承實戰進度 turn={s.turn} scenario={s.scenario} "
              f"チームランク={s.aoharuTeamRank} 爆発={s.aoharuBurstCount}")
        return s
    s = GameState(None)
    s.scenario = "aoharu"
    rng = random.Random(seed)
    s.applyInitIfNeeded(rng)
    print(f"[fresh] 全新一局 seed={seed} deck={len(s.deck)}")
    return s


def main():
    args = sys.argv[1:]
    live = "--live" in args
    seed = None
    if "--seed" in args:
        seed = int(args[args.index("--seed") + 1])
    else:
        seed = random.randrange(100000)
    auto = None
    if "--auto" in args:
        auto = [int(x) for x in args[args.index("--auto") + 1].split(",")]

    s = make_initial(live, seed)
    rng = random.Random(seed)
    queue = list(auto) if auto is not None else None

    print(render(s))
    while not s.isTerminal():
        print("標記 whitelist 等效: " + str(marks_view(s)))
        acts = set(legalActions(s))
        prompt = "  ".join(f"[{a}]{bridge.ACTION_NAMES[a]}" for a in sorted(acts))
        print("行動選択: " + prompt)
        try:
            if queue is not None:
                if not queue:
                    break
                raw = str(queue.pop(0))
                print(f"  (auto) > {raw}")
            else:
                raw = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if raw in ("q", "quit", "exit"):
            break
        if raw == "s":
            print(render(s))
            continue
        if raw == "w":
            print("marks: " + str(marks_view(s)))
            continue
        if raw.startswith("d"):
            try:
                mi = int(raw[1:].strip().split()[0])
                print(render_member(s, mi))
            except (IndexError, ValueError):
                print("用法: d <成員index>")
            continue
        try:
            a = int(raw)
        except ValueError:
            print("請輸入 0-7 / s / w / d N / q")
            continue
        if a not in acts:
            print(f"行動 {a} 目前不可用 (可用: {sorted(acts)})")
            continue
        before = snapshot(s)
        s = applyAction(s, a, rng)
        print(render_outcome(before, snapshot(s), bridge.ACTION_NAMES[a]))
        print(render(s))

    print("── 育成終盤 ──")
    print("育成馬 " + "  ".join(f"{k}{int(v):d}" for k, v in zip(STAT_KEYS, s.stats)))
    print(f"スキルPt {int(s.skillPt)}  累計爆発 {s.aoharuBurstCount}  "
          f"チームランク {s.aoharuTeamRank}")
    print("會員: " + "  ".join(
        f"M{i}{_aoharu_member_meta(i)['name']}({_stage(i, s)})"
        for i in range(len(s.aoharuMemberActive)) if s.aoharuMemberActive[i]))


if __name__ == "__main__":
    main()