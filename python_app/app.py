"""Flask Web UI for UMA MCTS Assistant

用法: python app.py [--port 5000]
開啟: http://127.0.0.1:5000
"""
import argparse
import threading
import time
import json
import os
import random

from flask import Flask, render_template, jsonify, request

import bridge
from bridge import load_current_turn, recommend, summarise_state
from simulator import (GameState, legalActions, applyAction, _aoharu_member_meta)

app = Flask(__name__)

_last_state = None       # 上次讀到的 raw normalized
_last_summary = None     # 上次計算的 summarise_state 結果
_last_recommend = None   # 上次計算的 MCTS 結果
_lock = threading.Lock()

# 監看 current_turn.json
_WATCHER_STATE = os.path.join(os.path.dirname(__file__), "state", "current_turn.json")
_FILE_MTIME = 0.0

# 沙盒行動 log (逐筆 append, 供比對/除錯用)
_ACTION_LOG = os.path.join(os.path.dirname(__file__), "state", "sim_action_log.jsonl")


def _log_action(rec):
    try:
        rec["clock"] = time.strftime("%m-%d %H:%M:%S") + "." + "%03d" % (time.time() % 1 * 1000)
        with open(_ACTION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _poll():
    global _last_state, _last_summary, _FILE_MTIME
    while True:
        try:
            mtime = os.path.getmtime(_WATCHER_STATE)
            if mtime != _FILE_MTIME:
                _FILE_MTIME = mtime
                with open(_WATCHER_STATE, encoding="utf-8") as f:
                    data = json.load(f)
                with _lock:
                    _last_state = data
                    _last_summary = summarise_state(data)
        except Exception:
            pass
        time.sleep(0.3)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    with _lock:
        if _last_summary is None:
            return jsonify({"ready": False, "msg": "等待遊戲連線…"})
        return jsonify({"ready": True, **_last_summary})


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    with _lock:
        if _last_state is None:
            return jsonify({"ready": False, "msg": "等待遊戲連線…"})
        st = _last_state

    body = request.get_json(silent=True) or {}
    iterations = int(body.get("iterations") or 5000)
    exploration = float(body.get("exploration") or 1.4)
    seed = body.get("seed")
    if seed is not None:
        seed = int(seed)
    strategy = body.get("strategy")

    result = recommend(st, iterations=iterations, exploration=exploration,
                       seed=seed, strategy=strategy)
    result["ready"] = True
    return jsonify(result)


# ================= アオハル盃模擬沙盒 (互動操作) =================
MOOD = {1: "絶不調", 2: "不調", 3: "普通", 4: "好調", 5: "絶好調"}
STAT_KEYS = ("速", "耐", "力", "根", "智")
ACTION_NAMES_SHORT = {0: "速", 1: "耐", 2: "力", 3: "根", 4: "智", 5: "休", 6: "外", 7: "賽"}

_sim = {"s": None, "rng": random.Random(), "seed": None, "mode": None,
        "history": []}
_sim_lock = threading.Lock()


def _sim_reset(mode, seed):
    if mode == "live":
        norm = load_current_turn()
        if not norm or norm.get("scenario_id") != 2:
            return None, "無 aoharu 實戰狀態 (current_turn.json 缺或非アオハル)"
        s = bridge.build_game_state(norm)
        _sim["rng"] = random.Random()
    else:
        rng = random.Random(seed if seed is not None else random.randrange(100000))
        s = GameState(None)
        s.scenario = "aoharu"
        s.applyInitIfNeeded(rng)
        _sim["rng"] = rng
    return s, None


def _sim_snapshot(s):
    return {"stats": [int(x) for x in s.stats], "skillPt": int(s.skillPt),
            "stamina": int(s.stamina),
            "mood": s.mood, "burstCnt": s.aoharuBurstCount,
            "rank": s.aoharuTeamRank, "gauge": list(s.aoharuMemberGauge),
            "burst": list(s.aoharuMemberBurst), "polar": list(s.aoharuMemberPolar)}


def _sim_marks(s):
    guide, soul, sp = {}, {}, {}
    ar = getattr(s, "aoharuMemberArrow", None)
    for col in range(5):
        if ar is not None:
            g = [i for i in range(len(ar))
                 if s.aoharuMemberActive[i] and ar[i] == col]
        else:
            g = [p - 10 for p in s.personDist[col] if p >= 10]
        if g:
            guide[str(col)] = g
        if s.aoharuSoulDict[col]:
            soul[str(col)] = list(s.aoharuSoulDict[col])
        if s.aoharuSPDict[col]:
            sp[str(col)] = list(s.aoharuSPDict[col])
    return {"guide": guide, "soul": soul, "sp": sp}


def _sim_card_type_name(c):
    n = getattr(c, "cardType", None)
    if n is None:
        n = getattr(c, "type", None)
    return {0: "速", 1: "耐", 2: "力", 3: "根", 4: "智", 5: "友", 6: "團"}.get(n, "?")


def _sim_live_marks():
    try:
        norm = load_current_turn()
        if not norm or norm.get("scenario_id") != 2:
            return None
        ah = norm.get("aoharu") or {}
        guide, soul, sp = {}, {}, {}
        for cid, m in (ah.get("marks") or {}).items():
            g = m.get("guide") or []
            su = m.get("soul") or []
            spm = m.get("sp") or []
            if g:
                guide[cid] = g
            if su:
                soul[cid] = su
            if spm:
                sp[cid] = spm
        if not (guide or soul or sp):
            return None
        return {"turn": norm.get("turn"), "guide": guide, "soul": soul, "sp": sp}
    except Exception:
        return None


def _pid_label(s, pid):
    if pid < 0:
        return None
    if pid < 6:
        nm = getattr(s.deck[pid], "name", "") or ""
        return chr(ord("A") + pid) + ("·" + nm[:5] if nm else "")
    if pid == 6:
        return "理事長"
    if pid == 7:
        return "記者"
    if pid == 8:
        return "NPC"
    if pid >= 10:
        return "M%d:%s" % (pid - 10, _aoharu_member_meta(pid - 10)["name"])
    return "?"


def _sim_payload():
    s = _sim["s"]
    if s is None:
        return {"ok": False, "msg": "模擬未啟動"}
    cols = []
    for t in range(5):
        arrows = []
        for p in s.personDist[t]:
            if p >= 10:
                idx = p - 10
                arrows.append({"idx": idx,
                               "arrow": getattr(s, "aoharuMemberArrow", None) is not None
                                        and s.aoharuMemberArrow[idx] == t,
                               "name": _aoharu_member_meta(idx)["name"],
                               "gauge": s.aoharuMemberGauge[idx],
                               "gaugeMax": 5,
                               "stage": ("極爆済" if s.aoharuMemberPolar[idx]
                                         else "魂爆済" if s.aoharuMemberBurst[idx]
                                         else "未爆")})
        eval = [(s.trainValue[t][i] * s.statWeights[i]) for i in range(5)]
        cols.append({
            "t": t, "name": STAT_KEYS[t],
            "level": s.getTrainingLevel(t),
            "fail": s.failRate[t],
            "cost": s.trainVitalChange[t],
            "gain": [float(x) for x in eval],
            "skillPt": s.trainValue[t][5],
            "attending": [x for x in (_pid_label(s, p) for p in s.personDist[t]) if x],
            "arrows": arrows,
            "soul": list(s.aoharuSoulDict[t]),
            "sp": list(s.aoharuSPDict[t]),
        })
    members = []
    for i in range(len(s.aoharuMemberActive)):
        if not s.aoharuMemberActive[i]:
            continue
        meta = _aoharu_member_meta(i)
        members.append({
            "idx": i, "name": meta["name"],
            "type": meta["type"],
            "deYiLv": meta["deYiLv"],
            "isNpc": bool(meta.get("npc")),
            "gauge": s.aoharuMemberGauge[i], "gaugeMax": 5,
            "stage": ("極爆済" if s.aoharuMemberPolar[i]
                      else "魂爆済" if s.aoharuMemberBurst[i] else "未爆"),
            "stat": [int(x) for x in s.aoharuMemberStat[i]],
            "bond": None if meta.get("npc") else s.aoharuMemberBond[i],
        })
    cards = [{
        "idx": i, "name": c.name,
        "type": _sim_card_type_name(c),
        "typeIdx": getattr(c, "cardType", None),
        "bond": s.cardBond[i],
        "shining": bool(s.cardBond[i] >= 80 and 0 <= (getattr(c, "cardType", None) or 99) <= 4),
        "gauge": s.aoharuCardGauge[i],
        "stage": "魂爆済" if s.aoharuCardBurst[i] else "未爆",
    } for i, c in enumerate(s.deck) if c is not None]
    return {
        "ok": True, "mode": _sim["mode"], "seed": _sim["seed"],
        "turn": s.turn, "terminal": s.isTerminal(),
        "scenario": s.scenario,
        "stamina": int(s.stamina), "maxVital": int(s.maxVital),
        "mood": s.mood, "moodName": MOOD.get(s.mood, "?"),
        "skillPt": int(s.skillPt), "teamRank": s.aoharuTeamRank,
        "burstCount": s.aoharuBurstCount,
        "stats": [int(x) for x in s.stats],
        "columns": cols, "members": members, "cards": cards,
        "marks": _sim_marks(s),
        "legal": sorted(legalActions(s)),
        "raceAvailable": s.isRaceAvailable(),
        "live": _sim_live_marks(),
    }


def _sim_diff(before, s2):
    b = before
    a = _sim_snapshot(s2)
    lines = []
    lines.append("育成馬 " + " ".join(
        f"{k}{'+' if v > 0 else ''}{v:d}" for k, v in zip(STAT_KEYS,
                 [x - y for x, y in zip(a["stats"], b["stats"])]) if v))
    dsp = a["skillPt"] - b["skillPt"]
    ds = a["stamina"] - b["stamina"]
    dm = a["mood"] - b["mood"]
    dr = a["rank"] - b["rank"]
    db = a["burstCnt"] - b["burstCnt"]
    if dsp:
        lines.append(f"スキルPt {dsp:+d}")
    if ds:
        lines.append(f"体力 {ds:+d}")
    if dm:
        lines.append(f"調子 {dm:+d}")
    if dr:
        lines.append(f"チームランク {dr:+d}")
    if db:
        lines.append(f"★ 爆発 {db:+d} 回 ★")
    for i in range(len(b["gauge"])):
        dg = a["gauge"][i] - b["gauge"][i]
        dbx = a["burst"][i] - b["burst"][i]
        dpx = a["polar"][i] - b["polar"][i]
        if dg or dbx or dpx:
            line = f"M{i} {_aoharu_member_meta(i)['name']} 渦{b['gauge'][i]}→{a['gauge'][i]}"
            if dbx:
                line += " 【魂爆発!!】"
            if dpx:
                line += " 【極・アオハル魂爆発!!】"
            lines.append(line)
    return lines


@app.route("/sim")
def sim_page():
    return render_template("sim.html")


@app.route("/api/sim/state")
def api_sim_state():
    with _sim_lock:
        if _sim["s"] is None:
            s, err = _sim_reset("fresh", None)
            if err:
                return jsonify({"ok": False, "msg": err})
            _sim["s"], _sim["mode"], _sim["seed"] = s, "fresh", None
        return jsonify(_sim_payload())


@app.route("/api/sim/action", methods=["POST"])
def api_sim_action():
    body = request.get_json(silent=True) or {}
    with _sim_lock:
        if _sim["s"] is None or body.get("reset"):
            mode = body.get("mode") or "fresh"
            seed = body.get("seed")
            s, err = _sim_reset(mode, seed)
            if err:
                return jsonify({"ok": False, "msg": err})
            _sim["s"], _sim["mode"], _sim["seed"] = s, mode, seed
            _sim["history"] = []
            _log_action({"type": "reset", "mode": mode, "seed": seed,
                         "turn": s.turn, "stamina": int(s.stamina),
                         "stats": [int(x) for x in s.stats]})

        s = _sim["s"]
        if s.isTerminal():
            return jsonify({"ok": False, "msg": "育成已結束",
                            "state": _sim_payload()})
        action = body.get("action")
        if action is None:
            return jsonify({"ok": True, "state": _sim_payload()})
        action = int(action)
        if action not in legalActions(s):
            return jsonify({"ok": False,
                            "msg": f"行動 {action} 目前不可用 (可用 {legalActions(s)})",
                            "state": _sim_payload()})
        before = _sim_snapshot(s)
        turn = s.turn
        name = ACTION_NAMES_SHORT.get(action, str(action))
        s2 = applyAction(s, action, _sim["rng"])
        _sim["s"] = s2
        report = getattr(s2, "report", None) or []
        lines = (list(report) if report else []) + _sim_diff(before, s2)
        entry = {"turn": turn, "name": name, "lines": lines,
                 "burstNow": s2.aoharuBurstCount - before["burstCnt"],
                 "stats": [int(x) for x in s2.stats],
                 "stamina": int(s2.stamina), "mood": MOOD.get(s2.mood, "?")}
        _sim["history"].append(entry)
        if len(_sim["history"]) > 40:
            _sim["history"] = _sim["history"][-40:]
        _log_action({"type": "action", "mode": _sim["mode"], "seed": _sim["seed"],
                     "turn": turn, "action": action, "name": name, "lines": entry["lines"],
                     "burstNow": entry["burstNow"], "stats": entry["stats"]})
        return jsonify({"ok": True, "outcome": entry, "state": _sim_payload()})


@app.route("/api/sim/log")
def api_sim_log():
    n = request.args.get("n", 15, type=int)
    rows = []
    try:
        with open(_ACTION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return jsonify({"ok": True, "rows": rows[-max(1, min(n, 500)):]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    print(f"UMA MCTS Assistant: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()