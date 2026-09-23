"""mitmproxy addon: passively decrypt single_mode (URA / 青春盃 / ...) traffic in
real time and write a clean 'current turn' state file for the assistant to read.

    mitmdump -s mitm_addon.py --listen-port 8080

Then point the Windows system proxy at 127.0.0.1:8080 while playing.

目標劇本不鎖死：只要是單人育成 (chara_info 存在) 的封包都嘗試 normalize，
URA / 青春盃 / 傳說共用同一套 normalize 輸出。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crypto
import state as state_module

_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state")
os.makedirs(_STATE_DIR, exist_ok=True)

STATE_FILE = os.path.join(_STATE_DIR, "current_turn.json")
ACTIVITY_FILE = os.path.join(_STATE_DIR, "activity.json")
RAW_DUMP_DIR = os.path.join(_STATE_DIR, "raw_dumps")

PRIORITY_PATHS = (
    "/single_mode/check_event",
    "/single_mode/exec_command",
    "/single_mode_legend/check_event",
    "/single_mode_legend/exec_command",
    "/single_mode_team/check_event",
    "/single_mode_team/exec_command",
)


def _hdr(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def _write_state(normalized: dict):
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


def _touch_activity(turn):
    tmp_path = ACTIVITY_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "turn": turn, "decision": False}, f)
    os.replace(tmp_path, ACTIVITY_FILE)


RAW_DUMP_KEEP = 2000
_dump_count = 0


def _prune_raw_dumps():
    try:
        files = sorted(os.listdir(RAW_DUMP_DIR))
        for name in files[:-RAW_DUMP_KEEP]:
            try:
                os.remove(os.path.join(RAW_DUMP_DIR, name))
            except OSError:
                pass
    except OSError:
        pass


def _dump_raw(path: str, decrypted: dict):
    global _dump_count
    os.makedirs(RAW_DUMP_DIR, exist_ok=True)
    safe = path.strip("/").replace("/", "_")
    dump_path = os.path.join(RAW_DUMP_DIR, f"{int(time.time())}_{safe}.json")
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(decrypted, f, ensure_ascii=False, indent=2)
    print(f"[raw] dumped {path} -> {dump_path}", flush=True)
    _dump_count += 1
    if _dump_count == 1 or _dump_count % 200 == 0:
        _prune_raw_dumps()


def response(flow):
    host = flow.request.pretty_host
    if "komoe" not in host.lower():
        return
    path = flow.request.path.split("?", 1)[0]
    last_segment = path.rsplit("/", 1)[-1]
    if "." in last_segment:  # static asset, skip
        return
    if not flow.response or flow.response.status_code != 200:
        return

    sid = _hdr(flow.request.headers, "SID")
    if not sid:
        return

    try:
        req_body_b64 = flow.request.raw_content.decode("utf-8")
        resp_body_b64 = flow.response.raw_content.decode("utf-8")
        decrypted = crypto.decrypt_response(sid, req_body_b64, resp_body_b64)
        _dump_raw(path, decrypted)

        data = decrypted.get("data", decrypted)
        if not (data or {}).get("chara_info"):
            return  # not a single-mode packet

        if path.endswith("/start"):
            for name in ("succession_factors.json", "race_history.json",
                         "skill_spent.json", "activity.json"):
                try:
                    os.remove(os.path.join(_STATE_DIR, name))
                    print(f"[state] new run -> cleared {name}", flush=True)
                except FileNotFoundError:
                    pass

        state_module.update_skill_spent(decrypted)

        # 優先處理決策封包；其他 single_mode 封包只進 raw dump / 技能花費累計
        if path in PRIORITY_PATHS:
            normalized = state_module.normalize(decrypted)
            if normalized is None:
                return
            pending = normalized.get("pending_events") or []
            settled = not pending
            if normalized.get("race_starting") or normalized.get("career_ended"):
                settled = False
            if settled:
                normalized["_captured_at"] = time.time()
                normalized["_source_path"] = path
                _write_state(normalized)
                print(f"[state] turn={normalized.get('turn')} "
                      f"vital={normalized.get('vital')} from {path} -> wrote {STATE_FILE}",
                      flush=True)
            else:
                _touch_activity(normalized.get("turn"))
                print(f"[state] turn={normalized.get('turn')} pending events {pending} "
                      f"-> deferred", flush=True)
    except Exception as e:
        print(f"[state] failed to decrypt/normalize {path}: {e!r}", flush=True)