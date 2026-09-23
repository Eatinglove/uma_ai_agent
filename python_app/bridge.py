"""bridge.py: 從 watcher 產出的 current_turn.json 建立 GameState，並跑 MCTS 提供給 UI 顯示。
- 讀取: 回合/心情/體力/技能點 等資訊
- 體力: 遊戲 vital/max_vital (可能非 0..100) → 轉成 0..100
- cardBond: 來自 bonds["1".."6"] = deck position
- cardNow: 從 commands[].training_partner_array 推得每個位置目前在練什麼
"""
import json
import os
import random
import subprocess
import tempfile
import time
import gc

PARITY_CANDS = 5          # parity 模式: 以 board 篩出的候選數
PARITY_N_DIV = 3          # parity 模式: n_per = iterations // PARITY_N_DIV (上下限 800..3000)
RAINBOW_TIE_EPS = 50.0    # 彩圈優先: 平均差距 ≤ 此值時, 以板面決定 (板面含彩圈/彈性/羈絆)

from simulator import (GameState, NUM_CARDS, NUM_TRAININGS, NUM_STATS, CFG,
                       TRAIN_SPEED, TRAIN_STAMINA, TRAIN_POWER, TRAIN_GUTS,
                       TRAIN_WIT, REST, OUTING, RACE,
                       ACTION_NAMES, MOOD_NAMES, DECK,
                       _aoharu_team_stat, _action_values)
from mcts import MCTS
from carddata import build_deck_from, uma_name, cardtype_name
from scenarios import SCENARIO_BY_ID, SCENARIOS

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "state", "current_turn.json")

# C++ 引擎執行檔 (URA 專用加速；アオハル維持 Python 兜底)
def _engine_exe():
    cfg = {}
    raw = os.environ.get("UMA_AI_ENGINE_CFG")
    if raw:
        cfg = json.loads(raw)
    exe = cfg.get("exe") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "build", "uma_ai.exe")
    if not os.path.exists(exe):
        raise RuntimeError(f"C++ 引擎不存在: {exe} (先執行 cmake --build build)")
    return exe

# 對應 command_type -> 訓練 action
COMMAND_TYPE_TO_ACTION = {1: None, 3: REST, 4: OUTING, 7: RACE}

# command_id 對訓練 index (URA 一般訓練；param_deltas 優先判斷)
_COMMAND_TRAIN_BY_ID = {
    101: TRAIN_SPEED,
    102: TRAIN_POWER,
    103: TRAIN_GUTS,
    105: TRAIN_STAMINA,
    106: TRAIN_WIT,
}

# param target_type (1..5 = 速耐カ根智, 10 = 體力, 30 = 技能點)
_TARGET_STAT_INDEX = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4}


def map_command_to_action(cmd):
    """對應 command 到訓練 action (訓練用 param_deltas 判斷屬性)。"""
    ct = cmd.get("command_type")
    if ct == 1:
        cid = cmd.get("command_id")
        if cid in _COMMAND_TRAIN_BY_ID:
            return _COMMAND_TRAIN_BY_ID[cid]
        # 否則: 用 param_deltas 判斷目標屬性
        deltas = cmd.get("param_deltas") or {}
        best = None
        bestV = -1
        for key, stat in _TARGET_STAT_INDEX.items():
            v = deltas.get(key, 0)
            if v > bestV:
                bestV = v
                best = stat
        return best if best is not None else TRAIN_SPEED
    return COMMAND_TYPE_TO_ACTION.get(ct)


def load_current_turn():
    """讀取 watcher 產出的 current_turn.json；不存在則回 None。"""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build_game_state(normalized, stat_weights=None, stat_targets=None):
    """normalized (state.normalize 輸出) → GameState.

    stat_weights: 目標育成固定屬性權重 [速,耐,力,根,智] (預設 1.0)。
    stat_targets: 目標育成數值 [速,耐,力,根,智] (None=用五圍上限)。
                  離目標越遠的屬性訓練價值越高；達標後價值遞減至 0。
    """
    deck = build_deck_from(normalized.get("support_cards"))
    s = GameState(deck)
    if stat_weights is not None:
        w = [float(x) for x in stat_weights]
        if any(not (0 <= x <= 3) for x in w):
            raise ValueError(f"stat_weights 需介於 0..3: {w}")
        s.statWeights = (w + [1.0] * NUM_STATS)[:NUM_STATS]
    if stat_targets is not None:
        t = [float(x) for x in stat_targets]
        if any(not (0 <= x <= 1400) for x in t):
            raise ValueError(f"stat_targets 需介於 0..1400: {t}")
        s.statTargets = (t + [0.0] * NUM_STATS)[:NUM_STATS]
    s.umaId = int(normalized.get("card_id") or 0) or None
    s.scenario = SCENARIO_BY_ID.get(int(normalized.get("scenario_id") or 0), "ura")
    s.applyInitIfNeeded()

    s.turn = int(normalized.get("turn") or s.turn)
    s.mood = max(1, min(5, int(normalized.get("motivation") or 3)))

    vital = normalized.get("vital")
    max_vital = normalized.get("max_vital")
    if vital is not None and max_vital:
        s.stamina = max(0, min(CFG.maxStamina,
                               round(vital * CFG.maxStamina / max_vital)))

    status = normalized.get("status") or {}
    order = [status.get("speed"), status.get("stamina"),
             status.get("power"), status.get("guts"), status.get("wiz")]
    for k, v in enumerate(order):
        if v is not None:
            s.stats[k] = int(v)

    # 上限: 用 max_status 覆蓋 (engine init 給的 + 遊戲實測)
    max_status = normalized.get("max_status") or {}
    for i, key in enumerate(["speed", "stamina", "power", "guts", "wiz"]):
        if key in max_status:
            s.fiveStatusLimit[i] = max(1, int(max_status[key]))

    # 訓練等級: 用 training_level (command_id 101..106) 的等級設 trainCount
    tl = normalized.get("training_level") or {}
    for cid, tra in _COMMAND_TRAIN_BY_ID.items():
        lv = int(tl.get(str(cid)) or 0)
        if 1 <= lv <= 5:
            s.trainCount[tra] = (lv - 1) * 4

    # 師資配置: 用封包訓練面板的真實 people 覆蓋隨機抽卡，
    # 讓 MCTS 對「這訓練有幾個卡、會拉誰的羈絆」的估值符合實戰畫面
    for cmd in normalized.get("commands") or []:
        act = map_command_to_action(cmd)
        if act is None or act >= NUM_TRAININGS:
            continue
        partners = cmd.get("training_partner_array") or []
        row = [p - 1 for p in partners if 1 <= p <= NUM_CARDS]
        row += [-1] * (NUM_TRAININGS - len(row))
        s.personDist[act] = row[:NUM_TRAININGS]

    # アオハル: 用 wire 的 guide(每欄白箭頭成員) 覆寫當前回合欄位，
    # 並同步 team 成員渦/爆発狀態/チーム順位/魂爆・極爆標記，
    # 讓 MCTS 依實戰畫面估值
    ah = normalized.get("aoharu") or {}
    if s.scenario == "aoharu" and ah:
        # 對映 wire target_id → sim 內部 idx: 以 scenarios 名單 (members+recruit) 的 tid 欄位
        # 對映 (實戰開場 10 人、turn25 起 +4 → 14 人，且含未招募候補)。
        # 補充成員每局隨機, 對 scenarios 沒列到的 tid (如候補角) 再以 team 補缺。
        name_of = {}
        tid_to_idx = {}
        for i, m in enumerate(SCENARIOS["aoharu"].get("members") or []):
            if m.get("tid") is not None:
                tid_to_idx[int(m["tid"])] = i
        for i, m in enumerate(SCENARIOS["aoharu"].get("recruit") or []):
            if m.get("tid") is not None:
                tid_to_idx[int(m["tid"])] = i + len(SCENARIOS["aoharu"].get("members") or [])
        for m in list(SCENARIOS["aoharu"].get("members") or []) + list(SCENARIOS["aoharu"].get("recruit") or []):
            if m.get("tid") is not None:
                name_of[int(m["tid"])] = m.get("name")
        _used = set(tid_to_idx.values())
        _next = len(SCENARIOS["aoharu"].get("members") or []) + len(SCENARIOS["aoharu"].get("recruit") or [])
        # live 補充不限 scenarios 名單: 新 tid (補充/候補) 自動分配後段 idx，
        # slot 不足時動態擴充 sim 成員陣列 (有限位元組, 只影響 live state)。
        for _e in (ah.get("team") or {}).get("team_chara_info_array") or []:
            _pid = _e.get("training_partner_id")
            if _pid is None or _pid in tid_to_idx:
                continue
            while _next in _used:
                _next += 1
            if _next >= len(s.aoharuMemberActive):
                _add = _next + 1 - len(s.aoharuMemberActive)
                s.aoharuMemberActive += [0] * _add
                s.aoharuMemberBond += [0] * _add
                s.aoharuMemberGauge += [0] * _add
                s.aoharuMemberBurst += [0] * _add
                s.aoharuMemberPolar += [0] * _add
                s.aoharuMemberStat += [[0] * NUM_STATS for _ in range(_add)]
                s.aoharuMemberArrow += [-1] * _add
            tid_to_idx[int(_pid)] = _next
            name_of.setdefault(int(_pid), "NPC·招募")
            _used.add(_next)
        idx_of = tid_to_idx.get
        members = ah.get("members") or []

        # 1) personDist: 用完整站欄 (training_partner_array，含無箭頭站欄成員)，
        #    不只 guide。卡/NPC 站欄位由 sim 的 cardRandom 保持。
        for cmd in normalized.get("commands") or []:
            act = map_command_to_action(cmd)
            if act is None or act >= NUM_TRAININGS:
                continue
            row = [10 + idx_of(p) for p in (cmd.get("training_partner_array") or [])
                   if idx_of(p) is not None]
            row += [-1] * (NUM_TRAININGS - len(row))
            s.personDist[act] = row[:NUM_TRAININGS]

        # 2) guide 白箭頭 → aoharuMemberArrow (該成員亮箭欄 = tra)
        s.aoharuMemberArrow = [-1] * len(s.aoharuMemberActive)
        # 3) 魂爆/極爆標記 → aoharuSoulDict/SPDict (標記欄有「點選即爆」)
        s.aoharuSoulDict = [[] for _ in range(5)]
        s.aoharuSPDict = [[] for _ in range(5)]
        for cid, m in (ah.get("marks") or {}).items():
            act = _COMMAND_TRAIN_BY_ID.get(int(cid))
            if act is None:
                continue
            for g in (m.get("guide") or []):
                gi = idx_of(g)
                if gi is not None and 0 <= gi < len(s.aoharuMemberArrow):
                    s.aoharuMemberArrow[gi] = act
            s.aoharuSoulDict[act] = [idx_of(g) for g in (m.get("soul") or []) if idx_of(g) is not None]
            s.aoharuSPDict[act] = [idx_of(g) for g in (m.get("sp") or []) if idx_of(g) is not None]

        # 4) 同步活躍成員 + 渦/爆発狀態 (member_state>0 即為活躍)
        for e in members:
            idx = idx_of(e.get("target_id"))
            if idx is None or not 0 <= idx < len(s.aoharuMemberActive):
                continue
            if int(e.get("member_state") or 0) > 0:
                s.aoharuMemberActive[idx] = 1
                state = int(e.get("soul_event_state") or 0)
                s.aoharuMemberGauge[idx] = max(0, int(e.get("soul_threshold_id") or 1) - 1)
                # soul_event_state 0=未爆 1=魂爆発済 2=極魂爆済
                s.aoharuMemberBurst[idx] = 1 if state >= 1 else 0
                s.aoharuMemberPolar[idx] = 1 if state >= 2 else 0
        # 累計爆発次數 = 各已魂爆(1) + 各已極爆(1) (每位成員至多 2 次)
        s.aoharuBurstCount = sum(s.aoharuMemberBurst) + sum(s.aoharuMemberPolar)

        # 同步各成員真實五圍 (team_chara_info_array: speed/stamina/power/guts/wiz
        # → sim stat 順序 速/耐/力/根/智)。live 模式成員可能含 scenarios 名單外的
        # 中入/補充角色, stat 直接以 wire 為準。
        _ord = [("speed", 0), ("stamina", 1), ("power", 2), ("guts", 3), ("wiz", 4)]
        for _e in (ah.get("team") or {}).get("team_chara_info_array") or []:
            _pid = _e.get("training_partner_id")
            _idx = idx_of(_pid)
            if _idx is None or not 0 <= _idx < len(s.aoharuMemberStat):
                continue
            for _k, _si in _ord:
                if _k in _e:
                    s.aoharuMemberStat[_idx][_si] = int(_e[_k])

        # 有魂爆/極爆標記 = 量條已滿可爆発。
        # wire 的 soul_threshold_id 在滿時可能給到 5(-1 後=4)，讓 gauge 維持滿
        # (覆蓋在 members 迴圈之後，否則會被 threshold-1 蓋回；否則 _aoharu_soulburst_try
        #  的 gauge>=5 檢查會擋掉真正該爆的成員)。
        _mark_gauge = int(SCENARIOS["aoharu"]["tokkun"]["gaugeMax"])
        for act in range(5):
            for idx in s.aoharuSoulDict[act] + s.aoharuSPDict[act]:
                if 0 <= idx < len(s.aoharuMemberGauge):
                    s.aoharuMemberGauge[idx] = _mark_gauge
        _tr = (ah.get("team") or {}).get("team_rank")
        if _tr:
            s.aoharuTeamRank = int(_tr)

    # 最後: 用 vit/stats 覆蓋後重新計算訓練顯示值
    # (避免 applyInitIfNeeded 的 stamina=100 影響 clamp)
    s._calcTrainingValue()

    s.skillPt = int(normalized.get("skill_point") or s.skillPt)

    # 羈絆：從 bonds 對應 deck position
    bonds = normalized.get("bonds") or {}
    for pos in range(1, NUM_CARDS + 1):
        key = str(pos)
        if key in bonds:
            s.cardBond[pos - 1] = max(0, min(100, int(bonds[key])))
            if s.cardBond[pos - 1] >= 80 and s.cardBond80Turn[pos - 1] < 0:
                s.cardBond80Turn[pos - 1] = 1  # 已達 80 的回合標記為 1
    # 補上羈絆資訊: 從 training_partner_array 推得
    s.cardNow = [-1] * NUM_CARDS
    for cmd in normalized.get("commands") or []:
        act = map_command_to_action(cmd)
        if act is None or act >= NUM_TRAININGS:
            continue
        for pos in cmd.get("training_partner_array", []):
            if 1 <= pos <= NUM_CARDS:
                s.cardNow[pos - 1] = act

    # 用封包真實面板覆蓋 sim 生成值: 當回合訓練顯示數值即為真實
    # (含遊戲的友情/彩圈加成；sim 生成值會低估密集卡與高羈絆訓練)
    _REAL_STAT_KEYS = {i: str(i) for i in range(1, 6)}
    for cmd in normalized.get("commands") or []:
        act = map_command_to_action(cmd)
        if act is None or act >= NUM_TRAININGS:
            continue
        d = cmd.get("param_deltas") or {}
        real = [float(d.get(_REAL_STAT_KEYS[i], 0)) for i in range(1, 6)]
        real.append(float(d.get("30", s.trainValue[act][5])))
        if any(real[:5]) or real[5]:
            s.trainValue[act] = real
        if "10" in d:
            s.trainVitalChange[act] = int(d["10"])
        fr = cmd.get("failure_rate")
        if isinstance(fr, (int, float)) and 0 <= fr <= 100:
            s.failRate[act] = int(fr)

    return s


def panel_from_commands(normalized):
    """當回合面板資訊 (給 UI 顯示真實遊戲資料)。"""
    rows = []
    for cmd in normalized.get("commands") or []:
        act = map_command_to_action(cmd)
        rows.append({
            "action": act,
            "action_name": ACTION_NAMES.get(act, "?"),
            "command_id": cmd.get("command_id"),
            "command_type": cmd.get("command_type"),
            "is_enable": cmd.get("is_enable"),
            "failure_rate": cmd.get("failure_rate", 0),
            "level": cmd.get("level", 0),
            "param_deltas": cmd.get("param_deltas", {}),
            "partners": cmd.get("training_partner_array", []),
            "tips": cmd.get("tips_event_partner_array", []),
        })
    return rows


def summarise_state(normalized):
    """給 UI 的摘要 dict。"""
    return {
        "turn": normalized.get("turn"),
        "card_id": normalized.get("card_id"),
        "uma_name": uma_name(normalized.get("card_id")),
        "vital": normalized.get("vital"),
        "max_vital": normalized.get("max_vital"),
        "motivation": MOOD_NAMES.get(normalized.get("motivation"), "?"),
        "motivation_raw": normalized.get("motivation"),
        "skill_point": normalized.get("skill_point"),
        "status": normalized.get("status"),
        "max_status": normalized.get("max_status"),
        "bonds": normalized.get("bonds"),
        "support_cards": normalized.get("support_cards"),
        "panel": panel_from_commands(normalized),
        "deck": [
            {"position": i + 1,
             "name": c.name,
             "cardId": c.cardId,
             "rarity": c.rarity,
             "type": cardtype_name(c)}
            for i, c in enumerate(build_deck_from(normalized.get("support_cards")))
        ],
        "scenario_id": normalized.get("scenario_id"),
        "scenario": SCENARIOS.get(
            SCENARIO_BY_ID.get(int(normalized.get("scenario_id") or 0), "ura"),
            {}).get("name"),
        "source_path": normalized.get("_source_path"),
        "captured_at": normalized.get("_captured_at"),
        "race_starting": normalized.get("race_starting"),
        "career_ended": normalized.get("career_ended"),
    }


def _mcts_python(state, seeds, per_run, exploration):
    """アオハル/Python 兜底：直接在 Python 跑 K 棵樹。"""
    aggVal = {}
    aggSims = {}
    aggVisits = {}
    votes = {}
    mc = MCTS(explorationConst=exploration, iterations=per_run)
    for sd in seeds:
        mc.rng.seed(sd)
        runBest, st = mc.searchWithStats(state)
        votes[runBest] = votes.get(runBest, 0) + 1
        for it in st:
            a = it["action"]
            aggVal[a] = aggVal.get(a, 0.0) + it["avg"] * it["visits"]
            aggSims[a] = aggSims.get(a, 0) + it["visits"]
            aggVisits[a] = aggVisits.get(a, 0) + it["visits"]
    mctsVal = {a: aggVal[a] / aggSims[a] for a in aggVal if aggSims[a] > 0}
    return mctsVal, aggVisits, votes


def _mcts_cpp(state, seeds, K, per_run, exploration):
    """URA/aoharu: 呼叫 build/uma_ai.exe 外部 CLI (回合邏輯同引擎)。"""
    exe = _engine_exe()
    inp = serialize_state(state)
    with tempfile.TemporaryDirectory(prefix="uma_ai_") as td:
        in_path = os.path.join(td, "engine_input.json")
        out_path = os.path.join(td, "out.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(inp, f, ensure_ascii=False, separators=(",", ":"))
        cmd = [exe, "recommend",
               "--input", in_path, "--output", out_path,
               "--seeds", str(K), "--per-run", str(per_run),
               "--seed", str(seeds[0])]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, cwd=os.path.dirname(exe))
        if proc.returncode != 0:
            raise RuntimeError(f"引擎失敗 rc={proc.returncode}: {proc.stderr}")
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
    mctsVal = {}
    aggVisits = {}
    votes = {}
    for it in data.get("stats") or []:
        a = int(it["action"])
        mctsVal[a] = float(it["avg"])
        aggVisits[a] = int(it["visits"])
        votes[a] = int(it.get("votes", 0))
    return mctsVal, aggVisits, votes


def _parity_cpp(state, action, n, seed):
    """固定首行動 rollout N 次的長局平均分 (穩定估計), 呼叫外部 C++ CLI。"""
    exe = _engine_exe()
    inp = serialize_state(state)
    with tempfile.TemporaryDirectory(prefix="uma_ai_") as td:
        in_path = os.path.join(td, "engine_input.json")
        out_path = os.path.join(td, "out.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(inp, f, ensure_ascii=False, separators=(",", ":"))
        cmd = [exe, "parity", "--action", str(action), "--n", str(n),
               "--seed", str(seed), "--input", in_path, "--output", out_path]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=180, cwd=os.path.dirname(exe))
        if proc.returncode != 0:
            raise RuntimeError(f"引擎失敗 rc={proc.returncode}: {proc.stderr}")
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
    return float(data.get("avg", 0.0)) if isinstance(data, dict) else float(data)


def serialize_state(state):
    """GameState → C++ engine input (compact numeric JSON, 對齊 main.cpp loader)。"""
    out = {
        "scenario": getattr(state, "scenario", "ura"),
        "turn": state.turn,
        "stamina": state.stamina,
        "mood": state.mood,
        "stats": [float(x) for x in state.stats],
        "trainCount": [int(x) for x in state.trainCount],
        "cardBond": [int(x) for x in state.cardBond],
        "cardBond80Turn": [int(x) for x in state.cardBond80Turn],
        "fans": state.fans,
        "skillPt": state.skillPt,
        "shiningCount": state.shiningCount,
        "umaStars": state.umaStars,
        "fiveStatusBonus": [int(x) for x in state.fiveStatusBonus],
        "fiveStatusLimit": [int(x) for x in state.fiveStatusLimit],
        "skillScore": state.skillScore,
        "maxVital": state.maxVital,
        "failureRateBias": state.failureRateBias,
        "isPositiveThinking": 1 if state.isPositiveThinking else 0,
        "isRefreshMind": 1 if state.isRefreshMind else 0,
        "friendshipNoncardYayoi": int(state.friendshipNoncardYayoi),
        "friendshipNoncardReporter": int(state.friendshipNoncardReporter),
        "saiHou": float(state.saihou),
        "zhongMaBlueCount": [int(x) for x in state.zhongMaBlueCount],
        "zhongMaExtraBonus": [int(x) for x in state.zhongMaExtraBonus],
        "raceTurns": [int(x) for x in state.raceTurns],
        "hintNow": [1 if x else 0 for x in state.hintNow],
        "personDist": [[int(p) for p in row] for row in state.personDist],
        "isTrainShining": [1 if x else 0 for x in state.isTrainShining],
        "trainValue": [[float(x) for x in row] for row in state.trainValue],
        "trainVitalChange": [int(x) for x in state.trainVitalChange],
        "failRate": [int(x) for x in state.failRate],
        "trainClicked": [int(x) for x in state.trainClicked],
        "statWeights": [float(x) for x in state.statWeights],
        "statTargets": [float(x) for x in (state.statTargets or [0] * NUM_STATS)],
        "strategy": {"weight": [float(x) for x in state.strategy["weight"]],
                     "skill": float(state.strategy["skill"])},
        "deck": [_serialize_card(c) for c in state.deck],
    }
    # アオハル盃欄位 (URA 也輸出空陣列，C++ 端以 scenario 旗標分流)
    out["aoharuTeamRank"] = int(getattr(state, "aoharuTeamRank", 30))
    out["aoharuBurstCount"] = int(getattr(state, "aoharuBurstCount", 0))
    out["aoharuMemberActive"] = [int(x) for x in getattr(state, "aoharuMemberActive", [])]
    out["aoharuMemberBond"] = [int(x) for x in getattr(state, "aoharuMemberBond", [])]
    out["aoharuMemberGauge"] = [int(x) for x in getattr(state, "aoharuMemberGauge", [])]
    out["aoharuMemberBurst"] = [int(x) for x in getattr(state, "aoharuMemberBurst", [])]
    out["aoharuMemberPolar"] = [int(x) for x in getattr(state, "aoharuMemberPolar", [])]
    out["aoharuMemberArrow"] = [int(x) for x in getattr(state, "aoharuMemberArrow", [-1] * 19)]
    out["aoharuMemberStat"] = [
        [int(x) for x in row] for row in getattr(state, "aoharuMemberStat", [])
    ]
    out["aoharuCardGauge"] = [int(x) for x in getattr(state, "aoharuCardGauge", [0] * 6)]
    out["aoharuCardBurst"] = [int(x) for x in getattr(state, "aoharuCardBurst", [0] * 6)]
    out["aoharuSoulDict"] = [
        [int(x) for x in v] for v in getattr(state, "aoharuSoulDict", [[] for _ in range(5)])
    ]
    out["aoharuSPDict"] = [
        [int(x) for x in v] for v in getattr(state, "aoharuSPDict", [[] for _ in range(5)])
    ]
    return out


def _serialize_card(c):
    return {
        "type": int(c.type),
        "cardType": int(c.cardType),
        "cardBonus": [int(x) for x in c.cardBonus],
        "skillPtBonus": int(c.skillPtBonus),
        "initStats": [int(x) for x in c.initStats],
        "initSkillPt": int(c.initSkillPt),
        "initialBond": int(c.initialBond),
        "friendPct": float(c.friendPct),
        "moodPct": float(c.moodPct),
        "trainPct": float(c.trainPct),
        "specialtyRate": float(c.specialtyRate),
        "saiHou": float(c.saiHou),
        "hintProb": float(c.hintProb),
        "failRateDrop": float(c.failRateDrop),
        "vitalCostDrop": float(c.vitalCostDrop),
        "wizVitalBonus": int(c.wizVitalBonus),
        "hintLevel": int(c.hintLevel),
        "uniqueEffectType": int(c.uniqueEffectType),
        "uniqueEffectParam": [float(x) for x in c.uniqueEffectParam],
    }


def recommend(normalized, iterations=5000, exploration=1.4, seed=None, strategy=None,
              method="mcts", stat_weights=None, stat_targets=None):
    """回傳 {best, stats, top, engine_snapshot}。

    strategy: {weight: [速,耐,力,根,智] (0..5), skill: 技能權重 (0..5)}
    method: "mcts"   走 UCB 搜尋樹 (平均分可能受訪問分配雜訊影響)
            "parity" 對 board 前 5 候選各跑固定首行動 rollout 平均 (更穩定)
    stat_weights: 目標育成固定屬性權重 [速,耐,力,根,智] (預設 1.0)。
    stat_targets: 目標育成數值 [速,耐,力,根,智] (None=用五圍上限)。
    """
    state = build_game_state(normalized, stat_weights=stat_weights,
                             stat_targets=stat_targets)
    if strategy:
        w = [float(x) for x in (strategy.get("weight") or [])[:NUM_STATS] if x is not None]
        if len(w) < NUM_STATS:
            w += [1.0] * (NUM_STATS - len(w))
        state.strategy = {"weight": [max(0.0, min(5.0, x)) for x in w],
                          "skill": max(0.0, min(5.0, float(strategy.get("skill") or 1.0)))}
    misc = summarise_state(normalized)

    if state.isTerminal():
        return {"state": misc, "best": None, "stats": [], "note": "育成已結束"}

    if state.isMandatoryRaceTurn():
        return {"state": misc, "best": RACE, "stats": [], "note": "強制出賽週"}

    # 多次 seed 的 MCTS (穩定化)：每 seed 各跑 iterations//K，避免單一 RNG 流的運氣
    K = 11
    if seed is None:
        master = random.Random()
        seeds = [master.randrange(2**31 - 1) for _ in range(K)]
    else:
        seeds = [seed + i for i in range(K)]

    immediate = _action_values(state)          # 根節點立即值 (真實面板+羈絆)
    imBest = max(immediate, key=immediate.get)
    others = [v for a, v in immediate.items() if a != imBest]
    secondIm = max(others) if others else 0
    # 當回合面板明顯優勢 (分數高且 >1.5 倍次佳)：輕量 MCTS 確認即可，省時間
    clearBoard = (immediate[imBest] >= 150 and immediate[imBest] >= 1.5 * secondIm)

    if clearBoard:
        per_run = max(min(iterations // K, 400), 40)   # 面板優勢: 提高單樹額度讓優勢行動visits明顯集中 (~2千 sims)
        gate = 0.75                                # 面板優勢時，除非長局強烈反對 (差>25%) 才改判
    else:
        per_run = min(max(iterations // K, 40), 800)   # 一般盤: 每棵樹 ≤800 節點 (11 棵 ~8.8千 sims) 讓訪次依價值排序
        gate = 0.90
    if state.scenario == "aoharu":
        # アオハル每輪 rollout 較長 (特訓/爆発/チームレース至 78T)，降到半額
        # 保持即時性 (web 15000 → ~13s，原 ~26s)；決策仍以 votes/avg 聚合為準。
        per_run = max(min(per_run, 400), 30)

    if state.scenario in ("ura", "aoharu"):
        if method == "parity":
            candidates = sorted(immediate, key=immediate.get, reverse=True)[:PARITY_CANDS]
            n_per = max(min(iterations // 3, 3000), 800)
            parityVal = {}
            for a in candidates:
                parityVal[a] = _parity_cpp(state, a, n_per, seeds[0])
            mctsVal = parityVal
            aggVisits = {a: n_per for a in candidates}
            votes = {a: 0 for a in candidates}
        else:
            mctsVal, aggVisits, votes = _mcts_cpp(state, seeds, K, per_run, exploration)
    else:
        mctsVal, aggVisits, votes = _mcts_python(state, seeds, per_run, exploration)
    gc.collect()

    cands = [a for a in mctsVal]
    if method == "parity":
        # 長局平均優先; 但差距 ≤ RAINBOW_TIE_EPS 時, 依「彩圈優先」原則用板面決定
        # (板面已內含彩圈/縛絆/高體力機會成本)
        avgBest = max(cands, key=lambda a: mctsVal[a])
        boardBest = max(cands, key=lambda a: immediate.get(a, -1e9))
        if (avgBest != boardBest
                and mctsVal[avgBest] - mctsVal[boardBest] <= RAINBOW_TIE_EPS
                and immediate.get(boardBest, -1e9) > immediate.get(avgBest, -1e9)):
            mctsBest, bestBy = boardBest, "parity"
        else:
            mctsBest, bestBy = avgBest, "parity"
        if mctsBest is None:
            best, bestBy = imBest, "board"
        else:
            best = mctsBest
    else:
        mctsBest = max(cands, key=lambda a: mctsVal[a]) if cands else None
        if (clearBoard and mctsBest is not None and imBest in mctsVal
                and mctsVal[imBest] >= gate * mctsVal[mctsBest]):
            best = imBest
            bestBy = "board"
        elif (not clearBoard and mctsBest is not None and imBest in mctsVal
              and mctsBest != imBest
              # 平手仲裁: MCTS 平均在 2% 內分不出勝負，但面板明確偏好 imBest
              # (URA 需 ≥1.2x MCTS最佳; aoharu 絆/特訓前期重要, 只要不低於 avg 最佳就採)
              and mctsVal[imBest] >= 0.98 * mctsVal[mctsBest]
              and immediate.get(imBest, 0) >= (immediate.get(mctsBest, 0)
                                               if state.scenario == "aoharu"
                                               else 1.2 * max(1.0, immediate.get(mctsBest, 0)))):
            best = imBest
            bestBy = "board"
        elif mctsBest is not None:
            best = mctsBest
            bestBy = "mcts"
        else:
            best = imBest
            bestBy = "board"

    rootVisits = sum(aggVisits.values()) or 1
    stats = [
        {"action": a,
         "visits": aggVisits.get(a, 0),
         "avg": round(mctsVal.get(a, 0)),
         "prec": 100.0 * aggVisits.get(a, 0) / rootVisits,
         "board": immediate.get(a, 0),
         "votes": votes.get(a, 0)}
        for a in sorted(aggVisits, key=lambda k: -aggVisits[k])
    ]

    # 用封包真實面板補上候選名稱與失敗率
    panel_map = {}
    for row in panel_from_commands(normalized):
        panel_map[row["action"]] = row

    for st in stats:
        a = st["action"]
        st["name"] = ACTION_NAMES.get(a, "?")
        p = panel_map.get(a)
        st["failure_rate"] = p["failure_rate"] if p else None
        st["level"] = p["level"] if p else None
        st["param_deltas"] = p["param_deltas"] if p else {}

    stats.sort(key=lambda x: -x["visits"])

    return {
        "state": misc,
        "best": best,
        "best_name": ACTION_NAMES.get(best, "?"),
        "stats": stats,
        "deck": [
            {"position": i + 1,
             "name": c.name,
             "cardId": c.cardId,
             "rarity": c.rarity,
             "type": cardtype_name(c)}
            for i, c in enumerate(state.deck)
        ],
        "aoharu": ({"bursts": state.aoharuBurstCount,
                    "teamRank": state.aoharuTeamRank,
                    "members": sum(1 for a in state.aoharuMemberActive if a),
                    "teamStat": _aoharu_team_stat(state),
                    "trainLevel": [state.getTrainingLevel(t) for t in range(NUM_TRAININGS)]}
                   if state.scenario == "aoharu" else None),
        "note": {"board": "", "mcts": "MCTS 長局平均",
                 "parity": "固定首行動 rollout 平均"}.get(bestBy, "MCTS 長局平均"),
    }