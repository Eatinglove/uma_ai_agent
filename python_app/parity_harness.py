"""平行對照 harness: C++ 引擎 vs Python 引擎 (URA)。

比對項目:
1. board   : 各行動立即值 actionValues (無隨機) — 驗證規則移植是否一致
2. parity  : 固定首行動 rollout N 次後的平均最終分數 — 驗證長局分佈 (容差內收斂)
3. recommend: K 棵樹 MCTS 建議 / 候選排序 一致率
   (資訊欄: MCTS 元素 tree 跨 PRNG [random.Random vs mt19937] 的樹結構不同，
    近距候選允許 ±2% 平手，不列入 PASS/FAIL 總判定)

用法: python parity_harness.py [--n 1200] [--seedbase 0] [--per-run 100]
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulator import (ACTION_NAMES, DECK, GameState, legalActions,
                       applyAction, rolloutToEnd, finalScoreRank, _action_values)
from bridge import serialize_state, _engine_exe, _mcts_cpp, _mcts_python


def make_state(seed=1):
    """建立一個可重現的 URA 中段局面 (真實卡組 + 已初始化)。"""
    s = GameState(DECK)
    s.applyInitIfNeeded(random.Random(seed))
    return s


def make_aoharu_state(seed=1, turns=5):
    """建立可重現的 アオハル 中段局面 (先走 turns 回合固定順序決策)。"""
    s = GameState(None)
    s.scenario = "aoharu"
    rng = random.Random(seed)
    s.applyInitIfNeeded(rng)
    for _ in range(turns):
        acts = legalActions(s)
        a = [x for x in (0, 2, 5, 1) if x in acts] or list(acts)
        s = applyAction(s, a[0], rng)
    return s


def py_parity_avg(state, action, n, base):
    tot = 0.0
    for i in range(n):
        rng = random.Random(base + i)
        nxt = applyAction(state, action, rng)
        end = rolloutToEnd(nxt, rng)
        tot += finalScoreRank(end)
    return tot / n


def run_cpp(args, ser):
    exe = _engine_exe()
    with tempfile.TemporaryDirectory(prefix="uma_ai_") as td:
        in_path = os.path.join(td, "in.json")
        out_path = os.path.join(td, "out.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(ser, f, ensure_ascii=False, separators=(",", ":"))
        full = [exe] + args + ["--input", in_path, "--output", out_path]
        proc = subprocess.run(full, capture_output=True, text=True, timeout=180,
                              cwd=os.path.dirname(exe))
        if proc.returncode != 0:
            raise RuntimeError(f"c++ rc={proc.returncode}: {proc.stderr}")
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)


def cmp_board(state, ser):
    py = {a: v for a, v in _action_values(state).items()}
    cpp = {it["action"]: it["value"] for it in run_cpp(["board"], ser)["stats"]}
    print("=== board (立即值 actionValues) ===")
    max_diff = 0.0
    for a in sorted(py):
        d = abs(py[a] - cpp.get(a, float("nan")))
        max_diff = max(max_diff, d)
        print(f"  {ACTION_NAMES[a]:>5}({a})  py={py[a]:12.4f}  cpp={cpp.get(a, float('nan')):12.4f}  d={d:8.4f}")
    print(f"  max diff = {max_diff:.6f}")
    ok = max_diff < 1e-6
    print(("  PASS" if ok else "  FAIL"))
    return ok


def cmp_parity(state, ser, n, base):
    actions = legalActions(state)
    print(f"=== parity (固定首行動, N={n}, seedbase={base}) ===")
    all_ok = True
    py_best, cpp_best = None, None
    for a in actions:
        py_avg = py_parity_avg(state, a, n, base)
        cpp = run_cpp(["parity", "--action", str(a), "--n", str(n),
                       "--seed", str(base)], ser)
        cpp_avg = cpp["avg"]
        d = abs(py_avg - cpp_avg)
        rel = d / max(1.0, abs(py_avg))
        ok = rel < 0.02
        all_ok &= ok
        print(f"  {ACTION_NAMES[a]:>5}({a})  py={py_avg:12.2f}  cpp={cpp_avg:12.2f}  d={d:8.2f}  rel={rel*100:5.2f}%  {'PASS' if ok else 'FAIL'}")
        if py_best is None or py_avg > py_best[1]:
            py_best = (a, py_avg)
        if cpp_best is None or cpp_avg > cpp_best[1]:
            cpp_best = (a, cpp_avg)
    agree = py_best[0] == cpp_best[0]
    print(f"  py最佳={ACTION_NAMES[py_best[0]]}  cpp最佳={ACTION_NAMES[cpp_best[0]]}  argmax一致={'是' if agree else '否'}")
    print("  " + ("PASS" if all_ok else "FAIL"))
    return all_ok and agree


def it_avg(cpp, a):
    for it in cpp["stats"]:
        if it["action"] == a:
            return it["avg"]
    return float("-inf")


def cmp_recommend(state, ser, per_run, base):
    print(f"=== recommend (K=5, per_run={per_run}, seedbase={base}) ===")
    seeds = [base + i for i in range(5)]
    py_val, py_visits, py_votes = _mcts_python(state, seeds, per_run, 1.4)
    py_best = max(py_val, key=py_val.get)
    cpp = run_cpp(["recommend", "--seeds", "5", "--per-run", str(per_run),
                   "--seed", str(base)], ser)
    cpp_stats = {it["action"]: it for it in cpp["stats"]}
    cpp_best = max(cpp_stats, key=lambda a: cpp_stats[a]["avg"])
    print(f"  py最佳={ACTION_NAMES[py_best]}({py_best})  cpp最佳={ACTION_NAMES[cpp_best]}({cpp_best})  "
          f"{'一致' if py_best == cpp_best else '不一致'}")
    print("  各候選: ", end="")
    print(", ".join(f"{ACTION_NAMES[it['action']]}={it['avg']:.0f}({it['visits']}v,{it['votes']}票)"
                    for it in sorted(cpp["stats"], key=lambda x: -x["visits"])))
    ok = py_best == cpp_best
    # 只要數值接近仍算可接受 (建議差一點點無妨)；MCTS 元素 tree 各用
    # random.Random vs mt19937，近距候選翻盤屬同排比較雜訊。
    # 平手容忍度 2% 對齊 parity 的 <2% 收斂門檻。
    if not ok:
        pb = py_val.get(py_best, 0.0)
        cb = cpp_stats.get(cpp_best, {}).get("avg", 0.0)
        py_r = py_val.get(cpp_best, 0.0)
        mb = cpp_stats.get(py_best, {}).get("avg", 0.0)
        ok = (py_r >= 0.98 * pb) and (mb >= 0.98 * cb)
        d = abs(pb - cb)
        print(f"  (注意: py最佳={py_best} {pb:.0f} vs cpp最佳={cpp_best} {cb:.0f}，"
              f"互評 {py_r:.0f}/{mb:.0f}，差距 {d:.0f} @0.98 管道)")
    print("  " + ("PASS" if ok else "NOTE"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--seedbase", type=int, default=0)
    ap.add_argument("--per-run", type=int, default=40)
    ap.add_argument("--state-seed", type=int, default=1)
    ap.add_argument("--scenario", choices=["ura", "aoharu"], default="ura")
    ap.add_argument("--turns", type=int, default=5)
    args = ap.parse_args()

    if args.scenario == "aoharu":
        state = make_aoharu_state(args.state_seed, args.turns)
    else:
        state = make_state(args.state_seed)
    ser = serialize_state(state)
    print(f"回合: turn={state.turn} scenario={args.scenario}")

    ok = True
    ok &= cmp_board(state, ser)
    ok &= cmp_parity(state, ser, args.n, args.seedbase)
    cmp_recommend(state, ser, args.per_run, args.seedbase)  # 資訊欄 (不打 PASS/FAIL)
    print("\n===== " + ("全部 PASS" if ok else "存在 FAIL / 不一致，需檢視") + " =====")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())