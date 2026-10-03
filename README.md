# UMA MCTS Assistant

ウマ娘（賽馬娘 Pretty Derby）單人育成的 MCTS 對弈助手。透過擷取遊戲封包還原「當前回合」狀態，用多棵樹的 MCTS 聚合（votes）幫你推薦下一步訓練，支援 **URA／アオハル盃** 兩種劇本，並能用瀏覽器或終端機模擬環境反覆練習。

---

## 它能做什麼

- **即時推薦**：攔截遊戲流量 → 還原當回合畫面 → MCTS 多樹投票給出最佳行動（含白箭頭特訓、魂爆/極爆標記、休息時機）。
- **アオハル盃完整還原**：部活成員、渦+1→魂爆→極爆三階段、白箭頭兩段式出線、休息隨機 30/50/70、季前賽補人、自由出賽等機制都實作在模擬器裡。
- **Web Sandbox**：瀏覽器操作模擬環境，可並排對照實戰 marks 與行動履歴（含每欄渦+1／爆発／能力 diff）。
- **互動式 Sandbox**：終端機版模擬環境，0-7 鍵操作（訓練/休/外/賽），支援 `--live` 繼承實戰進度。
- **C++ 引擎**：同一套模擬規則以 C++（mt19937）實作，提供 `recommend / parity / board` CLI，並有 parity harness 對照 Python 確保兩邊行為一致。

---

## 專案結構

```
uma_ai/
├── AGENTS.md                  # AI 開發筆記（決策紀律、機制細節；可不隨 repo 上傳）
├── CMakeLists.txt             # C++ 引擎建置
├── README.md
├── cpp_cores/
│   ├── simulator.cpp          # C++ 模擬器（與 Python 同步）
│   └── main.cpp               # CLI: recommend / parity / board / run
├── build/                     # cmake 產物（uma_ai.exe 靜態連結）
├── python_app/
│   ├── app.py                 # Flask Web Sandbox（/sim）
│   ├── bridge.py              # 狀態序列化 + recommend(匯總 MCTS 多樹) + C++ 橋接
│   ├── simulator.py           # 主模擬器（URA + アオハル）
│   ├── scenarios.py           # 劇本/成員/卡資料表
│   ├── mcts.py                # MCTS 核心（多樹聚合、UCB）
│   ├── carddata.py            # 卡牌資料載入
│   ├── member_bonus_fit.json  # 成員加成擬合（simulator 執行時讀取，勿刪）
│   ├── parity_harness.py      # C++ vs Python 一致性對照
│   ├── interactive_aoharu.py  # 終端機模擬環境
│   ├── watcher/               # mitmproxy addon：解密封包 → state/current_turn.json
│   ├── tools/                 # master.mdb 資料匯出工具（refresh_data.ps1）
│   ├── state/                 # 實戰擷取結果（current_turn.json 等）
│   ├── app_static/            # 網頁 assets（見下方說明）
│   └── dev_scratch/           # 診斷/研究殘留腳本（非主程式，可忽略或刪除）
```

> 注意：`python_app/static` / `templates` 是 Web Sandbox 的前端檔案。實際資料夾名請以目錄為準。

---

## 安裝

### 需求

- **Python 3.10+**（開發環境為 3.14）
- **CMake + MinGW g++**（若要建置/使用 C++ 引擎）
- **Windows**（系統 Proxy 設定、mitmproxy 證書）

### 安裝 Python 依賴

`start.ps1` 會自動檢查並安裝缺失套件，或可手動安裝：

```
pip install flask mitmproxy msgpack lz4 pycryptodome
```

### 建置 C++ 引擎（可選）

若 `build/uma_ai.exe` 不存在或想重建：

```
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build
```

g++ 靜態連結，產物不需額外 DLL。

---

## 使用方式

### 1. 實戰即時推薦（需遊戲本體）

1. 啟動 `啟動助手.bat`（或 `python_app\start.ps1`）。
2. 首次執行確認信任 mitmproxy 證書（位置 `~\.mitmproxy\`）。
   - 開遊戲前先啟動；`start.ps1` 會把系統 Proxy 指向 127.0.0.1:8080。
3. 進遊戲跑一回合 → watcher 自動把當下狀態寫到 `python_app\state\current_turn.json`。
4. 開啟 http://127.0.0.1:5000 查看推薦（URA/アオハル皆適用）。

> 遊戲結束、關閉視窗即可還原系統 Proxy。

### 2. Web Sandbox（免遊戲，瀏覽器練習）

```
python_app\启动模拟沙盒.bat        # 或 python app.py --port 5000
→ 開啟 http://127.0.0.1:5000/sim
```

操作：點訓練欄(速/耐/力/根/智)/休/外/賽按鈕，或鍵盤 `0-7` 快捷；可 `① 新規一局`（填 seed）、`② 實戰繼承`（讀 current_turn.json）、`③ 重繪`。右欄顯示白箭頭・魂爆●・極爆★ 標記、實戰 marks 對照與行動履歴。

API：`GET /api/sim/state`、`POST /api/sim/action`（`{action}` / `{reset, mode, seed}`）。

### 3. 互動式 Sandbox（終端機）

```
python python_app\interactive_aoharu.py                 # 全新一局
python python_app\interactive_aoharu.py --seed 7        # 固定 random seed
python python_app\interactive_aoharu.py --live          # 繼承實戰 current_turn.json
python python_app\interactive_aoharu.py --auto "0,2,5"  # 非互動跑一串
```

指令：`0 速/1 耐/2 力/3 根/4 智/5 休/6 外/7 賽`、`s` 重印棋盤、`w` 印 watcher 格式 marks、`d N` 成員明細、`q` 結束。每回合標記 白箭頭（部活成員）/ 魂爆● / 極爆★ 與渦條進度。


---

## 決策說明

- **以 MCTS 多樹聚合（votes）為準**，非立即值：剩餘回合多、主屬接近上限時立即值會高估高屬欄，深層 rollout 才能反映成長遞減，長局應缺項優先。
- URA 的路線：`python_app\state\target.json` 可設定目標距離（`demo_recommend.py --target 1400` 等）；アオハル無需設定。

---

*本專案僅供研究/學習用途，與遊戲官方無關。*
