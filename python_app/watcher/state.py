"""Normalize a decrypted single_mode response into a clean 'current turn' state.

通用版 (URA / 青春盃 / 其他單人劇本共用)。
欄位來源:
  - chara_info: 五圍、體力、心情、回合、技能點、卡片、羈絆、訓練等級
  - home_info: 當回合行動面板 (command_info_array)
傳奇劇本專屬的 legend_data_set 不在此處理。
"""
import json
import os

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state")
os.makedirs(_CACHE_DIR, exist_ok=True)

_FACTOR_CACHE = os.path.join(_CACHE_DIR, "succession_factors.json")

# 藍色(屬性)因子 factor_id = [type][star]：type 1=速 2=耐力 3=力 4=根性 5=智力，個位=星數
_FACTOR_TYPE = {1: "speed", 2: "stamina", 3: "power", 4: "guts", 5: "wiz"}


def _extract_factors(data: dict):
    arr = data.get("event_effected_factor_array")
    factors = []
    if arr:
        for slot in arr:
            for fi in slot.get("factor_info_array", []):
                fid = fi.get("factor_id", 0)
                if 100 <= fid <= 599:
                    typ = _FACTOR_TYPE.get(fid // 100)
                    star = fid % 10
                    if typ and 1 <= star <= 3:
                        factors.append({"type": typ, "star": star})
        if factors:
            try:
                with open(_FACTOR_CACHE, "w", encoding="utf-8") as f:
                    json.dump(factors, f)
            except Exception:
                pass
            return factors
    try:
        with open(_FACTOR_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


_RACE_CACHE = os.path.join(_CACHE_DIR, "race_history.json")


def _extract_race_turns(data: dict):
    rh = data.get("race_history")
    if rh is not None:
        turns = sorted({r["turn"] for r in rh if "turn" in r})
        try:
            with open(_RACE_CACHE, "w", encoding="utf-8") as f:
                json.dump(turns, f)
        except Exception:
            pass
        return turns
    try:
        with open(_RACE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


_SKILL_SPENT_CACHE = os.path.join(_CACHE_DIR, "skill_spent.json")


def update_skill_spent(decrypted: dict):
    """跨所有封包累計本回育成花了幾點技能(LP)。skill_point 只給餘額，買技能的
    下降在專屬 endpoint 觀察，差異即精確花費(含折扣)。"""
    data = decrypted.get("data", decrypted)
    sp = (data.get("chara_info") or {}).get("skill_point")
    if sp is None:
        return
    try:
        with open(_SKILL_SPENT_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {"last": None, "spent": 0}
    last = cache.get("last")
    if last is not None and sp < last:
        cache["spent"] = cache.get("spent", 0) + (last - sp)
    cache["last"] = sp
    try:
        with open(_SKILL_SPENT_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _read_skill_spent() -> int:
    try:
        with open(_SKILL_SPENT_CACHE, encoding="utf-8") as f:
            return int(json.load(f).get("spent", 0))
    except Exception:
        return 0


def _kv_list_to_dict(items, key_field, value_field):
    return {str(item[key_field]): item[value_field] for item in items}


_LONG_STATIC_KEYS = {
    "race_history", "succession_factors", "succession_factor_array",
    "skill_info_array", "skill_rank_info_array", "collect_skill_info_array",
    "event_effected_factor_array", "scenario_factor_array",
    "race_horse_info_array", "mark_array",
}

def _extract_aoharu(data: dict):
    """青春盃 (single_mode_team) 專屬狀態: 每欄特訓標記 + 19名成員渦/爆発狀態 + チーム情報。
    直接給助理 (模擬器) 用，對齊實戰。"""
    td = data.get("team_data_set")
    if not isinstance(td, dict):
        return None
    marks = {}
    for c in td.get("command_info_array") or []:
        marks[c.get("command_id")] = {
            "soul": c.get("soul_event_partner_array") or [],
            "sp": c.get("sp_soul_event_partner_array") or [],
            "guide": c.get("guide_event_partner_array") or [],
        }
    return {
        "members": td.get("evaluation_info_array") or [],
        "marks": marks,
        "team": td.get("team_info") or {},
        "scenario_progress": td.get("scenario_progress"),
        "history": td.get("team_race_history_array") or [],
    }

def _scenario_raw(data: dict) -> dict:
    """把 chara_info / home_info 以外、且非長靜態列表的欄位保留給助理比對。
    青春盃的成員/渦/爆發/順位等 scenario 專屬結構若出現在封包裡，會自動進
    current_turn.json.scenario_raw，第一包就讓我們看出實際 wire 命名。"""
    out = {}
    for k, v in data.items():
        if k in ("chara_info", "home_info", "team_data_set"):
            continue
        if k in _LONG_STATIC_KEYS:
            continue
        out[k] = v
    home = data.get("home_info") or {}
    home_extra = {k: v for k, v in home.items() if k != "command_info_array"}
    if home_extra:
        out["home_info_extra"] = home_extra
    return out


def normalize(decrypted: dict) -> dict:
    data = decrypted.get("data", decrypted)
    chara = data.get("chara_info", {})
    if not chara:
        return None

    home = data.get("home_info", {})
    commands = []
    for cmd in home.get("command_info_array", []):
        commands.append({
            "command_type": cmd["command_type"],
            "command_id": cmd["command_id"],
            "is_enable": bool(cmd["is_enable"]),
            "training_partner_array": cmd.get("training_partner_array", []),
            "tips_event_partner_array": cmd.get("tips_event_partner_array", []),
            "failure_rate": cmd.get("failure_rate", 0),
            "level": cmd.get("level", 0),
            "param_deltas": _kv_list_to_dict(
                cmd.get("params_inc_dec_info_array", []), "target_type", "value"),
        })

    return {
        "turn": chara.get("turn"),
        "vital": chara.get("vital"),
        "max_vital": chara.get("max_vital"),
        "motivation": chara.get("motivation"),
        "scenario_id": chara.get("scenario_id"),
        "skill_point": chara.get("skill_point"),
        "card_id": chara.get("card_id"),
        "talent_level": chara.get("talent_level"),
        "rarity": chara.get("rarity"),
        "status": {
            "speed":  chara.get("speed"),
            "stamina": chara.get("stamina"),
            "power":  chara.get("power"),
            "wiz":    chara.get("wiz"),
            "guts":   chara.get("guts"),
        },
        "max_status": {
            "speed":  chara.get("max_speed"),
            "stamina": chara.get("max_stamina"),
            "power":  chara.get("max_power"),
            "wiz":    chara.get("max_wiz"),
            "guts":   chara.get("max_guts"),
        },
        "training_level": _kv_list_to_dict(
            chara.get("training_level_info_array", []), "command_id", "level"),
        "bonds": {
            str(e["target_id"]): e["evaluation"]
            for e in chara.get("evaluation_info_array", [])
        },
        "support_cards": chara.get("support_card_array", []),
        "factors": _extract_factors(data),
        "commands": commands,
        "race_turns": _extract_race_turns(data),
        "pending_events": [e.get("event_id") for e in (data.get("unchecked_event_array") or [])],
        "race_starting": bool(data.get("race_start_info")),
        "career_ended": chara.get("state") == 3,
        "scenario_raw": _scenario_raw(data),
        "aoharu": _extract_aoharu(data),
        "skill_point_spent": _read_skill_spent(),
    }