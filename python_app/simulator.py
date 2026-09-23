"""python 移植版 URA 模擬底座（UmaAi master 公式，剔除機甲劇本內容）。

- 回合語意: turn 由 1 起算（1..78）。生涯強制出賽 = umaDB races[]+1（出道第 12 週），
  URA 決賽固定在第 74/76/78 週。isRacing 週只能比賽。
- 數值: TrainingBasicValue / FailRateBasic / BasicFiveStatusLimit / FiveStatusFinalScore
  來自 UmaAi master（mee1080/umasim 系），ScorePtRate=2.0、EventProb=0.35、
  EventStrength=20、hintPtRate=4。
- 已移除: overdrive / 齒輪 / 機甲升級 / UGE / 友人卡（涼花、理事長）。非卡理事長(id=6)
  與記者(id=7)保留。團卡(id=6)視為普通卡近似處理。
- 對外介面(保留): GameState / legalActions / applyAction / rolloutToEnd /
  REST / OUTING / RACE / NUM_CARDS / NUM_TRAININGS / CFG / TRAIN_* /
  ACTION_NAMES / MOOD_NAMES / DECK / SupportCard / WIZ。
"""
import json
import math
import os
import random

from scenarios import SCENARIOS, SCENARIO_BY_ID, get as _scn

# ---- アオハル 部活成員加成 ----
# 模型: 面板 = floor((base + Σ c[member][col-stat]) × g × mood)。每個成員對某欄
# 的加成是固定常數(ステボ式加進基準值)。無 参加人数補正 乘法。
_MEMBER_BONUS = {}
try:
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "member_bonus_fit.json")
    if os.path.exists(_p):
        _MEMBER_BONUS = json.load(open(_p, encoding="utf-8"))["member"]
except Exception:
    pass


def _member_bonus_add(basic, tra, pid):
    """把部活成員 (pid=10+idx) 的擬合加成加進 basic。"""
    idx = pid - 10
    meta = _aoharu_member_meta(idx)
    ctab = _MEMBER_BONUS.get(str(meta.get("tid")), {})
    if not ctab:
        return
    for i in range(5):
        v = ctab.get("%d-%d" % (tra, i))
        if v:
            basic[i] += v


# ---- 列舉 (與舊版一致) ----
SPEED, STAMINA, POWER, GUTS, WIZ = range(5)
NUM_STATS = 5

TRAIN_SPEED, TRAIN_STAMINA, TRAIN_POWER, TRAIN_GUTS, TRAIN_WIT, REST, OUTING, RACE = range(8)
NUM_TRAININGS = 5
NUM_ACTIONS = 8
NUM_CARDS = 6

ACTION_NAMES = {
    TRAIN_SPEED: "速度訓練", TRAIN_STAMINA: "耐力訓練",
    TRAIN_POWER: "力量訓練", TRAIN_GUTS: "根性訓練", TRAIN_WIT: "智力訓練",
    REST: "休息", OUTING: "外出", RACE: "比賽",
}

MOOD_NAMES = {1: "絶不調", 2: "不調", 3: "普通", 4: "好調", 5: "絶好調"}

TOTAL_TURN = 78  # URA 共 78 週 (1-based), 最後一週(78)是 URA3

# ---- 由 UmaAi master 抽取的常數 ----
# URA 上限 (2022/08 上限突破後為 1200+200)；超過 1200 的實際上昇量減半
BASIC_FIVE_STATUS_LIMIT = [1400, 1400, 1400, 1400, 1400]
_AOHARU_FIVE_STATUS_LIMIT = [1300, 1300, 1300, 1300, 1800]
PT_SCORE_RATE = 2.0
HINT_PT_RATE = 4
OVER_GOAL_FLOOR = 0.30   # 目標數值已超過: 主屬性收益壓低倍率 (副訓練/技能點收益仍保留)

# TrainingBasicValue[訓練][Lv(0..4)][速,耐,力,根,智,pt,體力]
TRAINING_BASIC_VALUE = [
    [  # 速
        [11, 0, 2, 0, 0, 5, -19],
        [12, 0, 2, 0, 0, 5, -20],
        [13, 0, 2, 0, 0, 5, -21],
        [14, 0, 3, 0, 0, 5, -23],
        [15, 0, 4, 0, 0, 5, -25],
    ],
    [  # 耐
        [0, 10, 0, 4, 0, 5, -20],
        [0, 11, 0, 4, 0, 5, -21],
        [0, 12, 0, 5, 0, 5, -22],
        [0, 13, 0, 5, 0, 5, -24],
        [0, 14, 0, 6, 0, 5, -26],
    ],
    [  # 力
        [0, 4, 10, 0, 0, 5, -20],
        [0, 4, 11, 0, 0, 5, -21],
        [0, 5, 12, 0, 0, 5, -22],
        [0, 5, 13, 0, 0, 5, -24],
        [0, 6, 14, 0, 0, 5, -26],
    ],
    [  # 根
        [2, 0, 2, 9, 0, 5, -20],
        [2, 0, 2, 10, 0, 5, -21],
        [2, 0, 2, 11, 0, 5, -22],
        [3, 0, 2, 12, 0, 5, -24],
        [4, 0, 3, 13, 0, 5, -26],
    ],
    [  # 智
        [2, 0, 0, 0, 8, 5, 5],
        [2, 0, 0, 0, 9, 5, 5],
        [2, 0, 0, 0, 10, 5, 5],
        [3, 0, 0, 0, 11, 5, 5],
        [4, 0, 0, 0, 12, 5, 5],
    ],
]

# FailRateBasic[訓練][Lv]  (順序: 速耐力根智)
FAIL_RATE_BASIC = [
    [520, 524, 528, 532, 536],
    [507, 511, 515, 519, 523],
    [516, 520, 524, 528, 532],
    [532, 536, 540, 544, 548],
    [320, 321, 322, 323, 324],
]

_DEFAULT_RACE_TURNS_1BASED = [12, 24, 36, 48, 60, 72, 74, 76, 78]

# 種馬藍因子預設值 (無 parent 資訊時使用)
_DEFAULT_ZHONGMA_BLUE = [4, 4, 4, 3, 3]
_DEFAULT_ZHONGMA_EXTRA = [30, 0, 30, 0, 0, 150]


def _load_score_table():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "data", "fiveStatusScore.py")
    ns = {}
    with open(p, encoding="utf-8") as f:
        exec(compile(f.read(), p, "exec"), ns)
    return ns["FINAL_SCORE"]


FIVE_STATUS_FINAL_SCORE = _load_score_table()

_uma_db = None


def _load_uma_db():
    global _uma_db
    if _uma_db is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "umaDB.json")
        with open(p, encoding="utf-8") as f:
            _uma_db = json.load(f)
    return _uma_db


def _load_uma_info(uma_id):
    """由 umaDB.json 取得 {star, fiveStatusInitial[5], fiveStatusBonus[5], races[0-based]}。"""
    info = _load_uma_db().get(str(uma_id))
    if not info:
        return None
    return {
        "star": int(info.get("star") or 3),
        "initial": [int(x) for x in info.get("fiveStatusInitial") or [100] * 5],
        "bonus": [int(x) for x in info.get("fiveStatusBonus") or [0] * 5],
        "races": [int(x) for x in info.get("races") or []],
    }


def _race_turns_1based(uma_id=None, scenario="ura"):
    races0 = _load_uma_info(uma_id)["races"] if uma_id else []
    finals = _scn(scenario).get("finalRaceTurns") or _DEFAULT_RACE_TURNS_1BASED[6:]
    if not races0:
        return sorted(set(list(_DEFAULT_RACE_TURNS_1BASED[:6]) + list(finals)))
    turns = [r + 1 for r in races0]
    for u in finals:
        if u not in turns:
            turns.append(u)
    return sorted(turns)


def _weighted_pick(weights, rng):
    total = sum(weights)
    r = rng.randrange(total)
    for i, w in enumerate(weights):
        r -= w
        if r < 0:
            return i
    return len(weights) - 1


def _rand_bool(rng, p):
    return rng.random() < p


# ---- 支援卡 ----
class SupportCard:
    __slots__ = ("name", "cardId", "rarity", "type",
                 "cardBonus", "skillPtBonus",
                 "initStats", "initSkillPt", "initialBond",
                 "friendPct", "moodPct", "trainPct", "specialtyRate",
                 "bondBonusStat", "bondBonusSkillPt",
                 "bondBonusFriendPct", "bondBonusMoodPct", "bondBonusTrainPct",
                 "hintLevel", "saiHou", "hintProb", "failRateDrop", "vitalCostDrop",
                 "wizVitalBonus", "cardType", "uniqueEffectType", "uniqueEffectParam")

    def __init__(self, name, type,
                 cardBonus, skillPtBonus,
                 initStats, initSkillPt, initialBond,
                 friendPct, moodPct, trainPct, specialtyRate,
                 bondBonusStat, bondBonusSkillPt,
                 bondBonusFriendPct, bondBonusMoodPct, bondBonusTrainPct,
                 cardId=None, rarity=None,
                 hintLevel=0, saiHou=0.0, hintProb=0.0,
                 failRateDrop=0.0, vitalCostDrop=0.0, wizVitalBonus=0,
                 cardType=None, uniqueEffectType=0, uniqueEffectParam=None):
        self.name = name
        self.cardId = cardId
        self.rarity = rarity
        self.type = type
        self.cardBonus = list(cardBonus)
        self.skillPtBonus = skillPtBonus
        self.initStats = list(initStats)
        self.initSkillPt = initSkillPt
        self.initialBond = initialBond
        self.friendPct = friendPct
        self.moodPct = moodPct
        self.trainPct = trainPct
        self.specialtyRate = specialtyRate
        self.bondBonusStat = list(bondBonusStat)
        self.bondBonusSkillPt = bondBonusSkillPt
        self.bondBonusFriendPct = bondBonusFriendPct
        self.bondBonusMoodPct = bondBonusMoodPct
        self.bondBonusTrainPct = bondBonusTrainPct
        self.hintLevel = hintLevel
        self.saiHou = saiHou
        self.hintProb = hintProb
        self.failRateDrop = failRateDrop
        self.vitalCostDrop = vitalCostDrop
        self.wizVitalBonus = wizVitalBonus
        self.cardType = cardType if cardType is not None else type
        self.uniqueEffectType = uniqueEffectType
        self.uniqueEffectParam = list(uniqueEffectParam) if uniqueEffectParam else []

    def deYiLv(self):
        return self.specialtyRate

    def ganJing(self):
        return self.moodPct

    def xunLian(self):
        return self.trainPct

    def youQing(self):
        return self.friendPct


_DEFAULT_CARD_IDS = [30215, 30178, 30226, 30234, 30214, 30201]


def buildDeck():
    """預設 deck：優先由 master 真卡 cardDB.json 載入 (滿破)，失敗時退回內建近似值。"""
    try:
        from carddata import load_card_db
        db = load_card_db()
        if any(cid not in db or 4 not in db[cid] for cid in _DEFAULT_CARD_IDS):
            raise LookupError("cardDB 缺卡")
        return [db[cid][4] for cid in _DEFAULT_CARD_IDS]
    except Exception:
        pass
    return [
        SupportCard("愛如往昔", SPEED, [1, 0, 1, 0, 0], 1,
                    [0, 0, 0, 0, 0], 60, 40,
                    25, 40, 15, 100,
                    [1, 0, 0, 0, 0], 1, 0, 0, 0),
        SupportCard("大鳴大放", SPEED, [0, 0, 1, 0, 0], 0,
                    [0, 0, 0, 0, 0], 0, 35,
                    25, 20, 15, 120,
                    [0, 0, 0, 0, 0], 0, 10, 15, 0),
        SupportCard("空中神宮", STAMINA, [0, 0, 0, 0, 0], 1,
                    [0, 0, 0, 0, 0], 40, 30,
                    35, 30, 15, 80,
                    [0, 2, 0, 0, 0], 0, 0, 0, 0),
        SupportCard("目白阿爾丹", POWER, [1, 0, 0, 0, 0], 0,
                    [0, 0, 0, 0, 0], 0, 30,
                    20, 60, 0, 35,
                    [0, 0, 2, 0, 0], 0, 0, 0, 0),
        SupportCard("美妙姿勢", GUTS, [1, 0, 0, 0, 0], 0,
                    [20, 0, 0, 0, 0], 0, 25,
                    20, 30, 0, 35,
                    [0, 0, 0, 0, 0], 0, 0, 0, 10),
        SupportCard("成田大進", WIZ, [0, 0, 0, 0, 0], 1,
                    [30, 0, 0, 0, 0], 0, 25,
                    35, 20, 15, 65,
                    [0, 0, 0, 0, 2], 0, 0, 0, 0),
    ]


DECK = buildDeck()


# ---- 全域設定 (保留舊版欄位供 bridge 讀 CFG.maxStamina) ----
class Config:
    __slots__ = ("totalTurns", "summerCampTurns", "mandatoryRaceTurns",
                 "maxStamina", "raceStaminaCost")

    def __init__(self):
        self.totalTurns = TOTAL_TURN
        self.summerCampTurns = [(37, 40), (61, 64)]
        self.mandatoryRaceTurns = _DEFAULT_RACE_TURNS_1BASED
        self.maxStamina = 100
        self.raceStaminaCost = 15


CFG = Config()


# ---- 狀態 ----
class GameState:
    __slots__ = ("turn", "stamina", "mood",
                 "stats", "trainCount",
                 "cardBond", "cardNow", "cardBond80Turn",
                 "fans", "skillPt", "shiningCount", "initialized",
                 "deck",
                 "umaId", "umaStars", "fiveStatusBonus", "fiveStatusLimit",
                 "skillScore", "maxVital", "failureRateBias",
                 "isPositiveThinking", "isRefreshMind",
                 "friendshipNoncardYayoi", "friendshipNoncardReporter", "saihou",
                 "zhongMaBlueCount", "zhongMaExtraBonus",
                 "raceTurns", "hintNow", "personDist", "isTrainShining",
                 "trainValue", "trainVitalChange", "failRate", "trainClicked",
                 "strategy", "statWeights", "statTargets",
                 "scenario",
                 "aoharuMemberActive", "aoharuMemberBond", "aoharuMemberGauge",
                 "aoharuMemberBurst", "aoharuMemberPolar", "aoharuMemberStat",
                 "aoharuCardGauge", "aoharuCardBurst",
                 "aoharuBurstCount", "aoharuTeamRank",
                 "aoharuSoulDict", "aoharuSPDict",
                 "aoharuMemberArrow", "trainInfo", "report")

    def __init__(self, deck=None):
        self.turn = 1
        self.stamina = CFG.maxStamina
        self.mood = 3
        self.stats = [0] * NUM_STATS
        self.trainCount = [0] * NUM_TRAININGS
        self.cardBond = [0] * NUM_CARDS
        self.cardNow = [0] * NUM_CARDS
        self.cardBond80Turn = [0] * NUM_CARDS
        self.fans = 0
        self.skillPt = 0
        self.shiningCount = 0
        self.initialized = False
        self.deck = deck if deck is not None else DECK

        self.umaId = None
        self.umaStars = 3
        self.fiveStatusBonus = [0] * 5
        self.fiveStatusLimit = list(BASIC_FIVE_STATUS_LIMIT)
        self.skillScore = 0
        self.maxVital = 100
        self.failureRateBias = 0
        self.isPositiveThinking = False
        self.isRefreshMind = False
        self.friendshipNoncardYayoi = 0
        self.friendshipNoncardReporter = 0
        self.saihou = 0.0
        self.zhongMaBlueCount = list(_DEFAULT_ZHONGMA_BLUE)
        self.zhongMaExtraBonus = list(_DEFAULT_ZHONGMA_EXTRA)
        self.raceTurns = []
        self.hintNow = [False] * NUM_CARDS
        self.personDist = [[-1] * 5 for _ in range(5)]
        self.isTrainShining = [False] * 5
        self.trainValue = [[0] * 6 for _ in range(5)]
        self.trainVitalChange = [0] * 5
        self.failRate = [0] * 5
        self.trainClicked = [0] * NUM_CARDS
        self.strategy = {"weight": [1.0] * NUM_STATS, "skill": 1.0}
        self.statWeights = [1.0] * NUM_STATS   # 目標育成: 各屬性訓練權重 (速 耐 力 根 智)
        self.statTargets = None           # 目標育成: [速,耐,力,根,智] 數值 (None=用五圍上限)
        self.scenario = "ura"
        n = _scn("aoharu")["maxMemberCount"]
        self.aoharuMemberActive = [0] * n
        self.aoharuMemberBond = [0] * n
        self.aoharuMemberGauge = [0] * n
        self.aoharuMemberBurst = [0] * n
        self.aoharuMemberPolar = [0] * n
        self.aoharuMemberStat = [[0] * NUM_STATS for _ in range(n)]
        self.aoharuCardGauge = [0] * NUM_CARDS
        self.aoharuCardBurst = [0] * NUM_CARDS
        self.aoharuBurstCount = 0
        self.aoharuTeamRank = 30
        self.aoharuSoulDict = [[] for _ in range(5)]
        self.aoharuSPDict = [[] for _ in range(5)]
        self.aoharuMemberArrow = [-1] * n
        self.trainInfo = [None] * 5   # 本回合各訓練欄的加成分解 (log 用)
        self.report = []              # 本回合行動詳細 log (沙盒顯示用)

    # ---- 拷貝 ----
    def clone(self):
        g = GameState(self.deck)
        g.turn = self.turn
        g.stamina = self.stamina
        g.mood = self.mood
        g.stats = list(self.stats)
        g.trainCount = list(self.trainCount)
        g.cardBond = list(self.cardBond)
        g.cardNow = list(self.cardNow)
        g.cardBond80Turn = list(self.cardBond80Turn)
        g.fans = self.fans
        g.skillPt = self.skillPt
        g.shiningCount = self.shiningCount
        g.initialized = self.initialized
        g.umaId = self.umaId
        g.umaStars = self.umaStars
        g.fiveStatusBonus = list(self.fiveStatusBonus)
        g.fiveStatusLimit = list(self.fiveStatusLimit)
        g.skillScore = self.skillScore
        g.maxVital = self.maxVital
        g.failureRateBias = self.failureRateBias
        g.isPositiveThinking = self.isPositiveThinking
        g.isRefreshMind = self.isRefreshMind
        g.friendshipNoncardYayoi = self.friendshipNoncardYayoi
        g.friendshipNoncardReporter = self.friendshipNoncardReporter
        g.saihou = self.saihou
        g.zhongMaBlueCount = list(self.zhongMaBlueCount)
        g.zhongMaExtraBonus = list(self.zhongMaExtraBonus)
        g.raceTurns = list(self.raceTurns)
        g.hintNow = list(self.hintNow)
        g.personDist = [list(row) for row in self.personDist]
        g.isTrainShining = list(self.isTrainShining)
        g.trainValue = [list(row) for row in self.trainValue]
        g.trainVitalChange = list(self.trainVitalChange)
        g.failRate = list(self.failRate)
        g.trainClicked = list(self.trainClicked)
        g.strategy = dict(self.strategy)
        g.strategy["weight"] = list(self.strategy.get("weight", [1.0] * NUM_STATS))
        g.scenario = self.scenario
        g.aoharuMemberActive = list(self.aoharuMemberActive)
        g.aoharuMemberArrow = list(getattr(self, "aoharuMemberArrow", [-1] * len(g.aoharuMemberActive)))
        g.aoharuMemberBond = list(self.aoharuMemberBond)
        g.aoharuMemberGauge = list(self.aoharuMemberGauge)
        g.aoharuMemberBurst = list(self.aoharuMemberBurst)
        g.aoharuMemberPolar = list(self.aoharuMemberPolar)
        g.aoharuMemberStat = [list(row) for row in self.aoharuMemberStat]
        g.aoharuCardGauge = list(self.aoharuCardGauge)
        g.aoharuCardBurst = list(self.aoharuCardBurst)
        g.aoharuBurstCount = self.aoharuBurstCount
        g.aoharuTeamRank = self.aoharuTeamRank
        g.aoharuSoulDict = [list(row) for row in self.aoharuSoulDict]
        g.aoharuSPDict = [list(row) for row in self.aoharuSPDict]
        g.trainInfo = list(self.trainInfo)
        return g

    # ---- 回合判定 ----
    def isTerminal(self):
        return self.turn > TOTAL_TURN

    def isXiahesu(self):
        return (37 <= self.turn <= 40) or (61 <= self.turn <= 64)

    def isSummerCamp(self):
        return self.isXiahesu()

    def isCurrRacing(self):
        return self.turn in self.raceTurns

    def isMandatoryRaceTurn(self):
        return self.isCurrRacing()

    def isRaceAvailable(self):
        return 14 <= self.turn <= 72

    def getTrainingLevel(self, trainingIndex):
        if self.isXiahesu():
            return 4
        return self.trainCount[trainingIndex] // 4

    def trainLevel(self, trainingIndex):
        return self.getTrainingLevel(trainingIndex)

    def isCardShining(self, cardIdx, trainIdx):
        c = self.deck[cardIdx]
        return 0 <= c.cardType <= 4 and self.cardBond[cardIdx] >= 80 and c.cardType == trainIdx

    # ---- 屬性/體力/心情 ----
    def addStatus(self, idx, value, over1200=True):
        gain = value
        if over1200 and gain > 0 and self.stats[idx] >= 1200:
            gain = gain // 2
        t = self.stats[idx] + gain
        if t > self.fiveStatusLimit[idx]:
            t = self.fiveStatusLimit[idx]
        if t < 1:
            t = 1
        self.stats[idx] = t

    def addStat(self, s, v):
        self.addStatus(s, v)

    def addAllStatus(self, value):
        for i in range(5):
            self.addStatus(i, value)

    def addVital(self, value):
        self.stamina += value
        if self.stamina > self.maxVital:
            self.stamina = self.maxVital
        if self.stamina < 0:
            self.stamina = 0

    def addMotivation(self, value):
        if value < 0:
            if self.isPositiveThinking:
                self.isPositiveThinking = False
            else:
                self.mood += value
                if self.mood < 1:
                    self.mood = 1
        else:
            self.mood += value
            if self.mood > 5:
                self.mood = 5

    def moodUp(self, d=1):
        self.addMotivation(d)

    def moodDown(self, d=1):
        self.addMotivation(-d)

    def addJiBan(self, idx, value):
        if idx == 6:
            self.friendshipNoncardYayoi += value
            if self.friendshipNoncardYayoi > 100:
                self.friendshipNoncardYayoi = 100
        elif idx == 7:
            self.friendshipNoncardReporter += value
            if self.friendshipNoncardReporter > 100:
                self.friendshipNoncardReporter = 100
        else:
            self.cardBond[idx] += value
            if self.cardBond[idx] > 100:
                self.cardBond[idx] = 100

    def addYayoiJiBan(self, value):
        self.addJiBan(6, value)

    def getYayoiJiBan(self):
        return self.friendshipNoncardYayoi

    def addTrainingLevelCount(self, idx, n):
        self.trainCount[idx] += n
        if self.trainCount[idx] > 16:
            self.trainCount[idx] = 16

    # ---- 劇本機制 (アオハル盃) ----
    # トレLv: URA 看訓練次數；アオハル盃看チームステータス (G..S)。
    def getTrainingLevel(self, trainingIndex):
        if self.scenario == "aoharu":
            return self._aoharuTrainingLevel(trainingIndex)
        if self.isXiahesu():
            return 4
        return self.trainCount[trainingIndex] // 4

    def _aoharuTrainingLevel(self, tra):
        if self.isXiahesu():
            return 5  # 合宿全 Lv MAX (aoharu level 1..5)
        n = 0
        tot = self.stats[tra]
        for idx in range(len(self.aoharuMemberActive)):
            if self.aoharuMemberActive[idx]:
                n += 1
                tot += self.aoharuMemberStat[idx][tra]
        avg = tot / (n + 1)
        lv = 1
        for th, l in _scn("aoharu")["rankToLevel"]:
            if avg >= th:
                lv = l
                break
        return lv

    def runRace(self, basicFiveStatusBonus, basicPtBonus):
        raceMultiply = 1 + 0.01 * self.saihou
        fb = int(raceMultiply * basicFiveStatusBonus)
        pb = int(raceMultiply * basicPtBonus)
        self.addAllStatus(fb)
        self.skillPt += pb

    def _realStatusGain(self, value, gain):
        """遊戲真值：屬性達 1200 後，實際上昇量減半 (單次訓練上限 100→50)。"""
        if gain <= 0:
            return gain
        if value >= 1200:
            return gain // 2
        return gain

    def _failureRate(self, trainType, failRateMultiply):
        lev = self.getTrainingLevel(trainType)
        if self.scenario == "aoharu":
            lev = max(0, min(4, lev - 1))  # aoharu level 1..5 -> fail table 0..4
        x0 = 0.1 * FAIL_RATE_BASIC[trainType][lev]
        f = 0.0
        if self.stamina < x0:
            f = (100 - self.stamina) * (x0 - self.stamina) / 40.0
        if f < 0:
            f = 0
        if f > 99:
            f = 99
        f *= failRateMultiply
        fr = math.ceil(f)
        fr += self.failureRateBias
        if fr < 0:
            fr = 0
        if fr > 100:
            fr = 100
        return fr

    # ---- 初始化 (newGame 對應) ----
    def applyInitIfNeeded(self, rng=None):
        if self.initialized:
            return
        rng = rng if rng is not None else _GLOBAL_RNG
        info = _load_uma_info(self.umaId)
        if info:
            self.umaStars = info["star"]
            self.fiveStatusBonus = list(info["bonus"])
            self.raceTurns = _race_turns_1based(self.umaId, self.scenario)
            base = [max(1, info["initial"][i] - 10 * (5 - info["star"]))
                    for i in range(5)]
        else:
            base = [100] * 5
            self.raceTurns = _race_turns_1based(None, self.scenario)

        for i in range(5):
            self.stats[i] = base[i] + self.zhongMaBlueCount[i] * 7
        cap = (_AOHARU_FIVE_STATUS_LIMIT if self.scenario == "aoharu"
               else BASIC_FIVE_STATUS_LIMIT)
        for i in range(5):
            self.fiveStatusLimit[i] = (
                cap[i] + int(self.zhongMaBlueCount[i] * 5.34 * 2))

        self.skillPt = 120
        self.skillScore = (170 * (self.umaStars - 2) if self.umaStars >= 3
                           else 120 * self.umaStars)

        for i, c in enumerate(self.deck):
            for k in range(5):
                self.stats[k] += c.initStats[k]
            self.skillPt += c.initSkillPt
            self.cardBond[i] = c.initialBond
            self.cardBond80Turn[i] = 1 if self.cardBond[i] >= 80 else -1
            self.saihou += getattr(c, "saiHou", 0) or 0

        self.maxVital = CFG.maxStamina
        self.stamina = CFG.maxStamina
        self.initialized = True
        if self.scenario == "aoharu":
            aoh = _scn("aoharu")
            for idx in range(len(aoh["members"])):
                self.aoharuMemberActive[idx] = 1
                self.aoharuMemberStat[idx] = list(aoh["members"][idx]["stat"])
            self.aoharuTeamRank = aoh["teamRank"]["startRank"]
        self.cardRandom(rng)

    # ---- 卡片出場 + 訓練值計算 ----
    def cardRandom(self, rng):
        """隨機分配人頭(卡/NPC/理事長/記者)、擲紅點、計算訓練值與失敗率。"""
        self.personDist = [[-1] * 5 for _ in range(5)]
        if self.isCurrRacing():
            return  # 比賽週不分配

        headN = [0] * 5
        buckets = [[] for _ in range(5)]

        def add_bucket(t, pid):
            if 0 <= t < 5:
                buckets[t].append(pid)

        # 非卡理事長 (URA 沒有友人卡，理事長一定出現)
        b = [100, 100, 100, 100, 100, 200]
        add_bucket(_weighted_pick(b, rng), 6)
        if self.scenario == "aoharu":
            # 部活成員三階段特訓/爆発標記: 
            #   每回合先擲出線率，出線後依狀態擲各自機率:
            #   - 集量條中(gauge<5): 亮箭0.4 → 訓練該欄 渦+1 (100%)
            #   - 量條滿(gauge>=5 未爆): 魂爆標記0.4 → 訓練該欄 魂爆発
            #   - 魂爆済: 極爆標記0.25 + 仍可亮箭(成長)
            #   - 極爆済: 僅亮箭(成長)
            aoh = _scn("aoharu")
            self.aoharuSoulDict = [[] for _ in range(5)]
            self.aoharuSPDict = [[] for _ in range(5)]
            self.aoharuMemberArrow = [-1] * len(self.aoharuMemberActive)
            for idx in range(len(self.aoharuMemberActive)):
                if not self.aoharuMemberActive[idx]:
                    continue
                if not _rand_bool(rng, aoh["memberAppearRate"]):
                    continue
                col = _club_bucket_pick(_aoharu_member_meta(idx), rng)
                if col >= NUM_TRAININGS:
                    continue  # 出場欄無特訓/爆発標記
                # 出線=站上該訓練欄 (不一定亮箭)；
                # 有出現的成員每個各自擲 40% 亮箭。亮箭與標記互相獨立。
                # 白箭頭 turn 3 才出現 (turn1/2 guide 全空，但站欄存在)。
                add_bucket(col, 10 + idx)
                if self.turn <= 2:
                    self.aoharuMemberArrow[idx] = -1
                    continue
                self.aoharuMemberArrow[idx] = col if _rand_bool(rng, aoh["memberArrowRate"]) else -1
                gauge = self.aoharuMemberGauge[idx]
                burst = self.aoharuMemberBurst[idx]
                polar = self.aoharuMemberPolar[idx]
                if gauge >= aoh["tokkun"]["gaugeMax"] and not burst:
                    if _rand_bool(rng, aoh["soulMarkRate"]):
                        self.aoharuSoulDict[col].append(idx)
                elif burst and not polar:
                    if _rand_bool(rng, aoh["spMarkRate"]):
                        self.aoharuSPDict[col].append(idx)
        elif self.turn >= 13 and not self.isXiahesu():
            # 記者 (第 13 週後，夏合宿不在)
            add_bucket(_weighted_pick(b, rng), 7)

        for i in range(5):
            n = len(buckets[i])
            if n == 1:
                self.personDist[i][0] = buckets[i][0]
                headN[i] = 1
            elif n > 1:
                if self.scenario == "aoharu":
                    # アオハル特訓は同一トレに複数名出現可能 (2人以上でボーナス)。
                    # 部活成員一同保留下來 (卡/NPC 仍在剩餘 slot 補位)。
                    take = min(n, 5)
                    for j in range(take):
                        self.personDist[i][j] = buckets[i][j]
                    headN[i] = take
                else:
                    self.personDist[i][0] = rng.choice(buckets[i])
                    headN[i] = 1
            buckets[i] = []

        for i in range(6):
            c = self.deck[i]
            add_bucket(_card_train_probs(c, rng), i)

        for _ in range(6):  # NPC (アオハル盃: turn 1 不出現)
            if self.scenario != "aoharu" or self.turn >= 2:
                add_bucket(_weighted_pick([100] * 6, rng), 8)

        for i in range(5):
            maxHead = 5 - headN[i]
            b2 = buckets[i]
            if len(b2) <= maxHead:
                for pid in b2:
                    self.personDist[i][headN[i]] = pid
                    headN[i] += 1
            else:
                for pid in rng.sample(b2, maxHead):
                    self.personDist[i][headN[i]] = pid
                    headN[i] += 1

        # 紅點
        self.hintNow = [
            _rand_bool(rng, 0.06 * (1 + 0.01 * self.deck[i].hintProb))
            for i in range(6)
        ]

        self._calcTrainingValue()

    def _calcTrainingValue(self):
        for tra in range(5):
            self._calcTrainingValueSingle(tra)

    def _calcTrainingValueSingle(self, tra):
        s = self
        level = s.getTrainingLevel(tra)
        basicTable = _scn(s.scenario).get("trainingBasicValue") or TRAINING_BASIC_VALUE
        rowIdx = level - 1 if s.scenario == "aoharu" else level
        basic = list(basicTable[tra][rowIdx])
        vitalCostBasic = -basic[6]

        headNum = 0
        shiningNum = 0
        shiningRec = [False] * 6

        totalXunlian = 0
        totalGanjing = 0
        youQingMult = 1.0
        vitMult = 1.0
        failMult = 1.0

        for h in range(5):
            pid = s.personDist[tra][h]
            if pid < 0:
                break
            if pid == 8:
                headNum += 1
                continue
            if pid >= 10 and s.scenario == "aoharu":
                # アオハル 部活成員 (pid=10+idx): 擬合常數加進基準值。
                _member_bonus_add(basic, tra, pid)
                continue
            if pid >= 6:
                continue
            headNum += 1
            sh = s.isCardShining(pid, tra)
            if sh:
                shiningNum += 1
                shiningRec[pid] = True
            eff = s._cardEffect(pid, tra, sh, headNum, shiningNum)
            for i in range(6):
                if basic[i] > 0:
                    basic[i] += int(eff["bonus"][i])
            if shiningRec[pid]:
                youQingMult *= (1 + 0.01 * eff["youQing"])
                if tra == TRAIN_WIT:
                    vitalCostBasic -= eff["vitalBonus"]
            totalXunlian += eff["xunLian"]
            totalGanjing += eff["ganJing"]
            vitMult *= (1 - 0.01 * eff["vitalCostDrop"])
            failMult *= (1 - 0.01 * eff["failRateDrop"])

        s.isTrainShining[tra] = shiningNum > 0

        if vitalCostBasic > 0:
            vc = -int(vitalCostBasic * vitMult)
        else:
            vc = -vitalCostBasic
        if vc > s.maxVital - s.stamina:
            vc = s.maxVital - s.stamina
        if vc < -s.stamina:
            vc = -s.stamina
        s.trainVitalChange[tra] = vc
        s.failRate[tra] = s._failureRate(tra, failMult)

        cardMult = ((1 + 0.05 * headNum) *
                    (1 + 0.01 * totalXunlian) *
                    (1 + 0.1 * (s.mood - 3) * (1 + 0.01 * totalGanjing)) *
                    youQingMult)

        for i in range(6):
            umaBonus = 1 + 0.01 * s.fiveStatusBonus[i] if i < 5 else 1
            lower = basic[i] * cardMult * umaBonus
            if lower > 100:
                lower = 100
            if i < 5:
                lower = s._realStatusGain(s.stats[i], lower)
            s.trainValue[tra][i] = lower
        s.trainInfo[tra] = {
            "basic": list(basic),
            "cardMult": cardMult,
            "youQingMult": youQingMult,
            "headNum": headNum,
            "xunlianPart": (1 + 0.01 * totalXunlian),
            "ganjingPart": (totalGanjing, 1 + 0.1 * (s.mood - 3) * (1 + 0.01 * totalGanjing)),
            "mood": s.mood,
            "umaBonus": [1 + 0.01 * s.fiveStatusBonus[i] if i < 5 else 1 for i in range(6)],
            "attended": [(pid, bool(s.isCardShining(pid, tra))) for pid in s.personDist[tra]
                         if 0 <= pid < 6],
            "nMembers": sum(1 for pid in s.personDist[tra]
                            if 10 <= pid < 10 + len(s.aoharuMemberActive)),
        }


def _card_train_probs(c, rng):
    """依照卡型建立出場權重（得意率）並抽訓練分類，團/友卡全 100。"""
    ct = getattr(c, "cardType", None)
    if ct in (5, 6):
        return _weighted_pick([100, 100, 100, 100, 100, 100], rng)
    t = ct if ct in (0, 1, 2, 3, 4) else c.type
    probs = [100, 100, 100, 100, 100, 50]
    probs[t] += max(0, int(c.specialtyRate))
    return _weighted_pick(probs, rng)


def _club_bucket_pick(member, rng):
    """部活成員參加哪種訓練：依得意率偏向其專精屬性 (近似)。"""
    probs = [100, 100, 100, 100, 100, 50]
    probs[int(member["type"])] += int(member.get("deYiLv") or 0)
    return _weighted_pick(probs, rng)


def _aoharu_member_meta(idx):
    """部活成員 idx 的配置資料 (初期/招募)。"""
    aoh = _scn("aoharu")
    members = aoh.get("members") or []
    if idx < len(members):
        return members[idx]
    recruit = aoh.get("recruit") or []
    j = idx - len(members)
    if j < len(recruit):
        return recruit[j]
    return {"name": "部活·?", "type": idx % 5, "deYiLv": 40,
            "stat": [30, 30, 30, 30, 30]}


def _aoharu_team_stat(s):
    """各屬性之チーム総和 (部活成員のみ)。"""
    out = [0] * NUM_STATS
    for idx in range(len(s.aoharuMemberActive)):
        if s.aoharuMemberActive[idx]:
            for i in range(NUM_STATS):
                out[i] += s.aoharuMemberStat[idx][i]
    return out


def _aoharu_team_total(s):
    """チーム総合力 = 成員総和 + 育成馬投入 (近似)。"""
    total = sum(_aoharu_team_stat(s))
    total += int(0.5 * sum(s.stats))
    return total


def _aoharu_rank_bonus(rank):
    for maxRank, bonus in _scn("aoharu")["teamRank"]["rankBonus"]:
        if rank <= maxRank:
            return bonus
    return 0


def _aoharu_join_members(s, n):
    """加入 n 名招募成員（依順序啟用未活動者）。"""
    aoh = _scn("aoharu")
    for idx in range(len(s.aoharuMemberActive)):
        if n <= 0:
            break
        if not s.aoharuMemberActive[idx]:
            s.aoharuMemberActive[idx] = 1
            s.aoharuMemberStat[idx] = list(_aoharu_member_meta(idx)["stat"])
            s.aoharuMemberBond[idx] = 0
            s.aoharuMemberGauge[idx] = 0
            s.aoharuMemberBurst[idx] = 0
            s.aoharuMemberPolar[idx] = 0
            n -= 1


def _aoharu_pre_p1_recruit(s):
    """季前賽第1戰前第一次補充 (負責人 2026-09):
    link 四名 + 攜帶支援卡角色 (友人卡 cardType==5 除外)；
    仍 <fillToBeforeP1 人時觸發特殊事件補充至 10。"""
    if s.scenario != "aoharu":
        return
    aoh = _scn("aoharu")
    _aoharu_join_members(s, int(aoh.get("linkCount") or 4))
    nSup = int(aoh.get("supportMemberCount") or 5)
    sup = sum(1 for c in s.deck if getattr(c, "cardType", None) != 5)
    _aoharu_join_members(s, min(sup, nSup))
    cur = s.aoharuMemberActive.count(1)
    fill = int(aoh.get("fillToBeforeP1") or 10)
    cap = int(aoh.get("maxMemberCount") or 19)
    if cur < fill and cur < cap:
        _aoharu_join_members(s, min(fill - cur, cap - cur))


def _aoharu_post_race_recruit(s):
    """季前賽結束隨機補充：每次最多 4 人，達上限 maxMemberCount 停。"""
    if s.scenario != "aoharu":
        return
    aoh = _scn("aoharu")
    cap = int(aoh.get("maxMemberCount") or 19)
    cur = s.aoharuMemberActive.count(1)
    mx = int(aoh.get("postRaceRecruitMax") or 4)
    _aoharu_join_members(s, min(mx, cap - cur))


def _aoharu_avg_tier(avg):
    """能力平均 → ランク (1..5)。"""
    lv = 1
    for th, l in _scn("aoharu")["rankToLevel"]:
        if avg >= th:
            lv = l
            break
    return lv


def _aoharu_team_race(s, rng):
    """ターン終了時のチームレース（勝敗/順位/成長/成員加入）。"""
    aoh = _scn("aoharu")
    idx = aoh["teamRaceTurns"].index(s.turn)
    opp = aoh["opponent"][idx]
    n = s.aoharuMemberActive.count(1)
    teamTotal = sum(_aoharu_team_stat(s))
    memberAvg = teamTotal / max(1, n) / 5
    myTier = _aoharu_avg_tier(memberAvg)
    oppTier = _aoharu_avg_tier(opp["oppAvg"])
    winProb = max(0.15, min(0.97, 0.55 + 0.10 * (myTier - oppTier)))
    won = _rand_bool(rng, winProb)
    tr = aoh["teamRank"]
    if won:
        s.aoharuTeamRank = max(1, min(30, s.aoharuTeamRank + opp.get("winBoost", tr.get("lossRankBoost", 2))))
        grow = opp["winStat"]
        sp = opp["winSp"]
        memberGain = 50
    else:
        s.aoharuTeamRank = min(30, s.aoharuTeamRank + tr.get("lossRankBoost", 2))
        grow = opp["loseStat"]
        sp = opp["loseSp"]
        memberGain = 10
    bonus = _aoharu_rank_bonus(s.aoharuTeamRank)
    s.addAllStatus(grow + (bonus if won else 0))
    s.skillPt += sp
    rankDelta = opp.get("winBoost", -tr.get("lossRankBoost", 2)) if won else tr.get("lossRankBoost", 2)
    _rep(s, f"チームレース vs {opp.get('rank', '?')}ランク: {'勝利' if won else '敗北'} → ランク{rankDelta:+d}, "
            f"育成馬全能力 +{grow + (bonus if won else 0):+d}, SP +{int(sp):+d}"
            + (f", ランクボーナス +{bonus}" if won and bonus else ""))
    for mi in range(len(s.aoharuMemberActive)):
        if s.aoharuMemberActive[mi]:
            for i in range(NUM_STATS):
                s.aoharuMemberStat[mi][i] += memberGain
            _aoharu_clamp_member(s, mi)
    _rep(s, f"  全部活成員 能力 +{memberGain} ({s.aoharuMemberActive.count(1)}人)")
    if s.turn == aoh["teamRaceTurns"][-1]:
        if won:
            s.moodUp(1)  # 決勝優勝：心情上昇 (approx)
            _rep(s, "決勝優勝: 幹勁 +1 (全員喜悅)")


def _aoharu_burst_skill(s):
    """シニア11月前半(=burstSkillTurn)結束時，依魂爆発回數結算スキル (approx)。"""
    n = s.aoharuBurstCount
    if n >= 13:
        s.skillScore += 510   # アオハル燃焼 Lv3
        s.skillPt += 20
    elif n >= 10:
        s.skillScore += 170   # アオハル燃焼 Lv1
        s.skillPt += 20
    elif n >= 7:
        s.skillScore += 85    # アオハル点火 Lv3
        s.skillPt += 15
    elif n >= 4:
        s.skillPt += 15
    # else: なし


def _aoharu_soulburst_try(s, idx, tra, rng, tokku, polar):
    """點選魂爆/極爆標記所在欄 → 觸發爆発:
    量條滿(gauge>=5, 未魂爆) → 魂爆発一次(state1)；之後等極爆標記
    → 極魂爆一次(state2)，再之後不再爆発。爆発加成/成長記入 tokku。"""
    if s.turn <= 2 or not s.aoharuMemberActive[idx]:
        return
    aoh = _scn("aoharu")
    bst = aoh["burst"]
    m = _aoharu_member_meta(idx)
    if polar:
        if s.aoharuMemberBurst[idx] != 1 or s.aoharuMemberPolar[idx]:
            return
        s.aoharuMemberPolar[idx] = 1
        s.aoharuBurstCount += 1
    else:
        if s.aoharuMemberBurst[idx]:
            return
        if s.aoharuMemberGauge[idx] < int(aoh["tokkun"]["gaugeMax"]):
            return
        s.aoharuMemberBurst[idx] = 1
        s.aoharuBurstCount += 1
    g = bst["memberGain"][m["type"]]
    for i in range(NUM_STATS):
        s.aoharuMemberStat[idx][i] += g[i]
    _aoharu_clamp_member(s, idx)
    tokku["polar" if polar else "burst"].append(("member", idx))
    _rep(s, f"  ★ {m['name']} {'極・魂爆発' if polar else '魂爆発'}: 成員能力 "
            f"{_row_str([int(x) for x in g])}")


def _aoharu_add_row(s, row):
    for i in range(NUM_STATS):
        if row[i]:
            s.addStatus(i, row[i])
    if len(row) > 5 and row[5]:
        s.skillPt += row[5]


def _aoharu_clamp_member(s, idx):
    """未爆発上限700, 爆発/極爆後900解放。"""
    cap = 900 if (s.aoharuMemberBurst[idx] or s.aoharuMemberPolar[idx]) else 700
    for i in range(NUM_STATS):
        if s.aoharuMemberStat[idx][i] > cap:
            s.aoharuMemberStat[idx][i] = cap


def _aoharu_tokkun_try(s, src, idx, tra, rng, tokku):
    """單一參與者(編成卡/部活成員)的特訓判定，結果記入 tokku。"""
    if s.turn <= 2:
        return  # 開幕2ターンはアオハル特訓が発生しない
    aoh = _scn("aoharu")
    tk = aoh["tokkun"]
    if src == "card":
        if s.aoharuCardBurst[idx]:
            return  # 已爆發過：卡片無極爆
        if not _rand_bool(rng, tk["triggerRate"]):
            return
        s.aoharuCardGauge[idx] += 1
        if s.aoharuCardGauge[idx] >= int(tk["gaugeMax"]):
            s.aoharuCardBurst[idx] = 1
            s.aoharuBurstCount += 1
            tokku["burst"].append((src, idx))
        else:
            tokku["tok"].append((src, idx))
    else:
        if idx < 0 or not s.aoharuMemberActive[idx]:
            return
        # 只有「站欄且該欄亮箭」的成員才特訓。
        # 站欄但無箭 (出線未亮箭) → 不 bump 渦、不成長。
        if s.aoharuMemberArrow[idx] != tra:
            return
        if s.aoharuMemberBurst[idx]:
            # 爆發済(魂爆済/極爆済): 亮箭→特訓只成長能力，不再累渦。
            # (極爆由 sp 標記決定，不走隨機 polarRate)
            lvbb = s.getTrainingLevel(tra)
            g = tk["memberGain"][tra][max(0, min(4, lvbb - 1))]
            for i in range(NUM_STATS):
                s.aoharuMemberStat[idx][i] += int(g[i] * float(tk.get("memberGainMult", 1.0)))
            _aoharu_clamp_member(s, idx)
            tokku["tok"].append((src, idx))
            return
        # 集量條中 (gauge<gaugeMax)：亮箭 → 訓練該欄 → 渦+1 (實測 100%，無二次機率)
        s.aoharuMemberGauge[idx] += 1
        gaugeMax = int(tk["gaugeMax"])
        if s.aoharuMemberGauge[idx] >= gaugeMax:
            s.aoharuMemberGauge[idx] = gaugeMax  # 量條滿停滯，爆発待魂爆標記+點欄
        lv = s.getTrainingLevel(tra)
        gain = tk["memberGain"][tra][max(0, min(4, lv - 1))]
        for i in range(NUM_STATS):
            s.aoharuMemberStat[idx][i] += int(gain[i] * float(tk.get("memberGainMult", 1.0)))
        _aoharu_clamp_member(s, idx)
        tokku["tok"].append((src, idx))


def _aoharu_apply_tokkun(s, tra, tokku, rng):
    """把本週特訓/爆発/極爆的加成套用至育成馬。"""
    count = len(tokku["tok"]) + len(tokku["burst"]) + len(tokku["polar"])
    if count == 0:
        return
    aoh = _scn("aoharu")
    tk = aoh["tokkun"]
    bst = aoh["burst"]
    # 依特訓人数 count 選一列 (cap 5)
    row = _aoharu_tokkun_row(s, tra, count)
    # link(シナリオリンク=編成卡) 特訓時 對非零欄 +1
    link = sum(1 for src, _ in tokku["tok"] if src == "card")
    if link:
        row = [v + (link if v else 0) for v in row]
    _aoharu_add_row(s, row)
    for _ in tokku["tok"]:
        if _rand_bool(rng, tk["hintRate"]):
            s.skillPt += int(tk["hintPt"])
    for src, _idx in tokku["burst"]:
        bRow = bst["bonusLink"][tra] if src == "card" else bst["bonus"][tra]
        _aoharu_add_row(s, bRow)
        s.skillPt += int(bst["hintPt"])
    for _src, _idx in tokku["polar"]:
        _aoharu_add_row(s, bst["bonus"][tra])
        s.skillPt += int(bst["hintPt"])
    bn = len(tokku["burst"]) + len(tokku["polar"])
    if bn and tra == 4:
        # 追加體力消費已全數移除 (2022改版)，賢さ魂爆発のみ回復量+5/人 維持
        s.addVital(5 * bn)
        _rep(s, f"賢さ魂爆発/極爆 {bn}人: 体力 +{5 * bn}")


# 全域隨機 (applyInitIfNeeded 未帶 rng 時用)
_GLOBAL_RNG = random.Random()


# ---- 行動解算 ----
_TRAIN_NAME = ("速", "耐", "力", "根", "智")


def _rep(s, line):
    if s.scenario == "aoharu":
        s.report.append(line)


def _act_name(tra):
    if tra == REST:
        return "休息"
    if tra == OUTING:
        return "外出"
    if tra == RACE:
        return "比賽"
    if 0 <= tra < NUM_TRAININGS:
        return f"{_TRAIN_NAME[tra]}訓練"
    return "?"


def _over1200(s, i):
    return " (再-10: 能力>1200)" if s.stats[i] > 1200 else ""


def _base_vital_cost(s, tra):
    info = s.trainInfo[tra] if 0 <= tra < 5 else None
    if info and len(info["basic"]) > 6:
        return int(info["basic"][6])
    return 0


def _factor_parts(info):
    parts = []
    if info["headNum"]:
        parts.append(f"人數{info['headNum']}×{1 + 0.05 * info['headNum']:.2f}")
    xl = info["xunlianPart"]
    if xl > 1.005:
        parts.append(f"特訓級×{xl:.2f}")
    gan = info["ganjingPart"]
    if gan[1] != 1.0:
        parts.append(f"幹勁{info['mood']}×{gan[1]:.2f}"
                     + (f" (合宿{int(gan[0])}人)" if gan[0] else ""))
    if info["youQingMult"] != 1.0:
        parts.append(f"友情×{info['youQingMult']:.2f}")
    return parts


def _rep_train_gain(s, tra):
    """詳細列出成功訓練的屬性增加來源 (為什麼加這點數)。"""
    if s.scenario != "aoharu":
        return
    info = s.trainInfo[tra]
    if not info:
        return
    parts = _factor_parts(info)
    eff = info["cardMult"]
    effDesc = "".join(f"[{p}]" for p in parts) if parts else "(無補正)"
    att = " ".join(f"卡{pid}{'◎彩圈' if sh else ''}" for pid, sh in info["attended"]) or "―"
    members = info["nMembers"]
    _rep(s, f"{_act_name(tra)}: 効率{eff:.2f} = {effDesc}")
    gain = []
    for i in range(NUM_STATS):
        v = s.trainValue[tra][i] * s.statWeights[i]
        if not v:
            continue
        why = f"基礎{info['basic'][i]:g} ×効率{eff:.2f} ×UMA{info['umaBonus'][i]:.2f} ×目標{float(s.statWeights[i]):g}"
        _rep(s, f"  {_TRAIN_NAME[i]} +{v:g} = {why}")
        gain.append(v)
    sp = s.trainValue[tra][5]
    if sp:
        _rep(s, f"  スキルPt +{sp:g} = 基礎{info['basic'][5]:g} ×効率{eff:.2f}")
    _rep(s, f"  出席: {att}" + (f", 部活+路人 {members}人" if members else ""))
    return


def _row_str(row):
    out = []
    for i in range(NUM_STATS):
        if row[i]:
            out.append(f"{_TRAIN_NAME[i]}{int(row[i]):+d}")
    if len(row) > 5 and row[5]:
        out.append(f"SP{int(row[5]):+d}")
    return " ".join(out) if out else "―"


def _aoharu_tokkun_row(s, tra, count):
    """依特訓人數選 byCount 加成列 (cap 5)。
    count==1 時絕大多數無加成，但該欄主屬基礎值極高(等級↑)時仍可能 +1。"""
    aoh = _scn("aoharu")
    tk = aoh["tokkun"]
    rowIdx = max(0, min(5, count) - 1)
    row = list(tk["byCount"][tra][rowIdx])
    if count == 1 and not any(row):
        # 單箭通常無加成；高基礎欄(主屬基礎≥12)偶爾 +1
        lv = s.getTrainingLevel(tra)
        basic = (aoh.get("trainingBasicValue") or TRAINING_BASIC_VALUE)[tra][max(0, min(4, lv - 1))]
        if basic[tra] >= 12:
            row[tra] = 1
    return row


def _report_tokku(s, tra, tokku):
    if s.scenario != "aoharu":
        return
    count = len(tokku["tok"]) + len(tokku["burst"]) + len(tokku["polar"])
    if count == 0:
        return
    aoh = _scn("aoharu")
    tk = aoh["tokkun"]
    row = _aoharu_tokkun_row(s, tra, count)
    link = sum(1 for src, _ in tokku["tok"] if src == "card")
    line = f"アオハル特訓 {count}人 → 育成馬 {_row_str(row)}"
    if link:
        line += f" (リンク{link}人: 非零欄+{link})"
    _rep(s, line)
    for src, idx in tokku["tok"]:
        nm = f"卡{idx} {s.deck[idx].name}" if src == "card" else _aoharu_member_meta(idx)["name"]
        _rep(s, f"  ├ {nm} 特訓")
    for src, idx in tokku["burst"]:
        nm = f"卡{idx} {s.deck[idx].name}" if src == "card" else _aoharu_member_meta(idx)["name"]
        bRow = aoh["burst"]["bonusLink"][tra] if src == "card" else aoh["burst"]["bonus"][tra]
        _rep(s, f"  ★ {nm} アオハル魂爆発: 育成馬 {_row_str(bRow)} +SP{int(aoh['burst']['hintPt'])}")
    for _src, idx in tokku["polar"]:
        _rep(s, f"  ★★ {_aoharu_member_meta(idx)['name']} 極・アオハル魂爆発: 育成馬 "
                f"{_row_str(aoh['burst']['bonus'][tra])} +SP{int(aoh['burst']['hintPt'])}")


def _apply_training(s, tra, rng):
    """處理 訓練/休息/外出/比賽 本身（不含固定/隨機事件）。回傳是否成功。"""
    if s.isCurrRacing():
        assert tra == RACE
        return True  # 固定比賽收益在 checkFixedEvents 處理

    if tra == REST:
        if s.isXiahesu():
            return False  # 合宿只能外出
        r = rng.randrange(100)
        if r < 25:
            s.addVital(70)
            _rep(s, "休息: 体力 +70 (機率25%)")
        elif r < 75:
            s.addVital(50)
            _rep(s, "休息: 体力 +50 (機率50%)")
        else:
            s.addVital(30)
            _rep(s, "休息: 体力 +30 (機率25%)")
        return True

    if tra == RACE:
        if s.turn <= 13 or s.turn >= 73:
            return False
        # 自由參賽獎勵 = 單屬性 +8~10 (隨機欄) + SP45，
        #  皆乘「競賽加成」(加算, 例 +10%/+5%/+5% = ×1.2)，小數點捨去。
        m = 1 + 0.01 * s.saihou
        col = rng.randrange(NUM_TRAININGS)
        gain = int(m * rng.randrange(8, 11))
        s.addStatus(col, gain)
        _rep(s, f"自主比賽: {_act_name(col)} +{gain}")
        s.skillPt += int(m * 45)
        _rep(s, f"自主比賽: SP +{int(m * 45)}")
        s.addVital(-15)
        _rep(s, "自主比賽: 体力 -15")
        if rng.randrange(10) == 0:
            s.addMotivation(1)
            _rep(s, "自主比賽: 成績/運氣 → 幹勁 +1 (10%)")
        return True

    if tra == OUTING:
        if s.isXiahesu():
            s.addVital(40)
            s.addMotivation(1)
            _rep(s, "合宿外出: 体力 +40, 幹勁 +1")
        else:
            if rng.randrange(2):
                s.addMotivation(2)
                _rep(s, "外出: 幹勁 +2 (50%)")
            else:
                s.addMotivation(1)
                s.addVital(10)
                _rep(s, "外出: 幹勁 +1 体力 +10 (50%)")
        return True

    if not (0 <= tra <= 4):
        return False

    _rep(s, _act_name(tra))
    fail = s.failRate[tra]
    if s.scenario == "aoharu" and s.aoharuSPDict[tra]:
        fail = 0  # 極・アオハル魂爆発トレは失敗率必 0% (官方/神ゲー確認)
    if rng.randrange(100) < fail:  # 失敗
        if tra == TRAIN_WIT:
            # 賢さ失敗無副作用，僅體力照常回復 (gamewith/namu確認)
            s.addVital(s.trainVitalChange[tra])
            _rep(s, f"失敗(賢さ): 無副作用, 体力 {s.trainVitalChange[tra]:+d}")
            return True
        if rng.randrange(100) < fail:  # 大失敗 (大失敗率=失敗率，二次擲骰)
            s.addStatus(tra, -10)
            if s.stats[tra] > 1200:
                s.addStatus(tra, -10)
            others = list(range(5))
            rng.shuffle(others)
            for i in others[:2]:  # 隨機2個(可與對象重疊=疊到-20) -10
                s.addStatus(i, -10)
                if s.stats[i] > 1200:
                    s.addStatus(i, -10)
            s.addMotivation(-2)
            _rep(s, f"{_act_name(tra)} 大失敗: {_act_name(tra)} -10{_over1200(s, tra)}, "
                    f"隨機2欄 -10(可疊加), 幹勁 -2")
            if s.scenario != "aoharu":
                s.addVital(10)  # アオハル盃: 失敗不回復體力
        else:  # 小失敗
            s.addStatus(tra, -5)
            if s.stats[tra] > 1200:
                s.addStatus(tra, -5)
            s.addMotivation(-1)
            _rep(s, f"{_act_name(tra)} 失敗: {_act_name(tra)} -5{_over1200(s, tra)}, 幹勁 -1")
        return True

    # 成功
    _rep_train_gain(s, tra)
    for i in range(5):
        s.addStatus(i, s.trainValue[tra][i] * s.statWeights[i], over1200=False)
    s.skillPt += s.trainValue[tra][5]
    s.addVital(s.trainVitalChange[tra])
    _rep(s, f"{_act_name(tra)} 成功: 体力 {s.trainVitalChange[tra]:+d} (基礎消費 {_base_vital_cost(s, tra):+d})")

    tokku = {"tok": [], "burst": [], "polar": []}
    hintCards = []
    for h in range(5):
        pid = s.personDist[tra][h]
        if pid < 0:
            break
        if pid < 6:
            s.addJiBan(pid, 7)
            s.trainClicked[pid] += 1
            _rep(s, f"卡{pid} {s.deck[pid].name} 情誼 +7")
            if s.hintNow[pid]:
                hintCards.append(pid)
            if s.scenario == "aoharu":
                _aoharu_tokkun_try(s, "card", pid, tra, rng, tokku)
        elif pid == 6:  # 非卡理事長
            j = s.friendshipNoncardYayoi
            g = 2 if j < 40 else 3 if j < 60 else 4 if j < 80 else 5
            s.skillPt += g
            s.addJiBan(6, 7)
            _rep(s, f"理事長 情誼 +7, スキルPt +{g}")
        elif pid == 7:  # 記者
            j = s.friendshipNoncardReporter
            g = 2 if j < 40 else 3 if j < 60 else 4 if j < 80 else 5
            s.addStatus(tra, g)
            s.addJiBan(7, 7)
            _rep(s, f"記者 情誼 +7, {_act_name(tra)} +{g}")
        elif s.scenario == "aoharu" and 10 <= pid < 10 + len(s.aoharuMemberActive):
            idx = pid - 10
            if s.aoharuMemberActive[idx] and s.aoharuMemberArrow[idx] == tra:
                if not _aoharu_member_meta(idx).get("npc"):
                    s.aoharuMemberBond[idx] = min(100, s.aoharuMemberBond[idx] + 7)
                    _rep(s, f"M{idx} {_aoharu_member_meta(idx)['name']} 情誼 +7")
                else:
                    _rep(s, f"M{idx} {_aoharu_member_meta(idx)['name']}(NPC) 訓練 (無情誼)")
                _aoharu_tokkun_try(s, "member", idx, tra, rng, tokku)
        elif pid == 8:
            pass

    if s.scenario == "aoharu":
        # 點選魂爆/極爆標記所在欄 → 觸發爆発 (量條滿待爆 / 魂爆済待極爆)
        for idx in s.aoharuSoulDict[tra]:
            _aoharu_soulburst_try(s, idx, tra, rng, tokku, False)
        for idx in s.aoharuSPDict[tra]:
            _aoharu_soulburst_try(s, idx, tra, rng, tokku, True)
        _aoharu_apply_tokkun(s, tra, tokku, rng)
        _report_tokku(s, tra, tokku)

    if hintCards:
        pick = rng.choice(hintCards)
        s.addJiBan(pick, 5)
        _rep(s, f"紅點連結: 卡{pick} {s.deck[pick].name} 情誼 +5")
        lv = s.deck[pick].hintLevel or 0
        if lv > 0:
            s.skillPt += int(lv * HINT_PT_RATE)
            _rep(s, f"紅點: スキルPt +{int(lv * HINT_PT_RATE)} (ヒントLv{lv})")
        else:  # 0 級只給屬性
            if tra == 0:
                s.addStatus(0, 6); s.addStatus(2, 2)
                _rep(s, "紅點: 速 +6 力 +2")
            elif tra == 1:
                s.addStatus(1, 6); s.addStatus(3, 2)
                _rep(s, "紅點: 耐 +6 根 +2")
            elif tra == 2:
                s.addStatus(2, 6); s.addStatus(1, 2)
                _rep(s, "紅點: 力 +6 耐 +2")
            elif tra == 3:
                s.addStatus(3, 6); s.addStatus(0, 1); s.addStatus(2, 1)
                _rep(s, "紅點: 根 +6 速 +1 力 +1")
            elif tra == 4:
                s.addStatus(4, 6); s.skillPt += 5
                _rep(s, "紅點: 智 +6 スキルPt +5")

    s.addTrainingLevelCount(tra, 1)
    return True


def applyAction(s, a, rng):
    n = s.clone()
    n.applyInitIfNeeded(rng)
    if n.isTerminal():
        return n
    if not n.isCurrRacing():
        ok = _apply_training(n, a, rng)
        if not ok:
            raise ValueError(f"game: illegal action {a} at turn {n.turn}")
    _check_event_after_train(n, rng)
    if n.isTerminal():
        return n
    n.cardRandom(rng)
    return n


def _check_event_after_train(s, rng):
    _check_fixed_events(s, rng)
    s.turn += 1


def _check_fixed_events(s, rng):
    if s.isRefreshMind:
        s.addVital(5)
        if rng.randrange(4) == 0:
            s.isRefreshMind = False

    if s.scenario == "aoharu" and s.turn in _scn("aoharu")["teamRaceTurns"]:
        # チームレース是シナリオ固定事件 (6月/12月後半ターン終了時)，
        # 與育成馬自身賽程無關——該週沒排生涯賽的馬也要照常開打。
        # 與自身賽重疊時取代該週一般出賽收益 (近似)。
        _aoharu_team_race(s, rng)
    elif s.isCurrRacing():
        if s.turn < 73:
            s.runRace(3, 45)
            s.addYayoiJiBan(4)
        elif s.turn == 74:
            s.runRace(10, 40)
        elif s.turn == 76:
            s.runRace(10, 60)
        elif s.turn == 78:
            s.runRace(10, 80)

    if s.scenario == "aoharu":
        aoh = _scn("aoharu")
        # 補充只在季前賽前/季前賽(24/36/48/60)結束後；
        # 決勝(72) 後不再補。turn 23 為ジュニア12月前半結束 (第1戰前)。
        if s.turn == aoh["preRaceRecruitTurn"]:
            pre = s.aoharuMemberActive.count(1)
            _aoharu_pre_p1_recruit(s)
            _rep(s, f"部活補充(季前賽前): {pre}→{s.aoharuMemberActive.count(1)}人 "
                    f"({_recruit_names(s, pre)})")
        elif s.turn in aoh["teamRaceTurns"] and s.turn != aoh["teamRaceTurns"][-1]:
            pre = s.aoharuMemberActive.count(1)
            _aoharu_post_race_recruit(s)
            if s.aoharuMemberActive.count(1) != pre:
                _rep(s, f"部活補充(盃賽後): {pre}→{s.aoharuMemberActive.count(1)}人 "
                        f"({_recruit_names(s, pre)})")
        if s.turn == 70:
            # シニア11月前半 アオハルスキル +15SP
            s.skillPt += 15
            _rep(s, "アオハルスキル (シニア11月前半): SP +15")

    if s.turn == 12:  # 出道賽
        assert s.isCurrRacing()
        _rep(s, "出道賽: 固定比賽收益 (フレンド同時)")
    elif s.turn == 24:  # 第一年年底
        if s.maxVital - s.stamina >= 20:
            s.addVital(20)
            _rep(s, "年末: 体力 +20")
        else:
            s.addAllStatus(5)
            _rep(s, "年末: 体力已滿 → 全能力 +5")
    elif s.turn == 30:  # 第二年繼承
        _inheritance(s, rng)
        _rep(s, "第二年繼承: 青因子%+因子 (能力/SP獎勵)")
    elif s.turn == 36:
        pass  # 第二年合宿開始
    elif s.turn == 48:  # 第二年年底
        if s.maxVital - s.stamina >= 30:
            s.addVital(30)
            _rep(s, "年末: 体力 +30")
        else:
            s.addAllStatus(8)
            _rep(s, "年末: 体力已滿 → 全能力 +8")
    elif s.turn == 49:  # 抽獎
        rd = rng.randrange(100)
        if rd < 16:
            s.addVital(30); s.addAllStatus(10); s.addMotivation(2)
            _rep(s, "抽獎 大賞: 体力+30 全能力+10 幹勁+2")
        elif rd < 43:
            s.addVital(20); s.addAllStatus(5); s.addMotivation(1)
            _rep(s, "抽獎 中賞: 体力+20 全能力+5 幹勁+1")
        elif rd < 89:
            s.addVital(20)
            _rep(s, "抽獎: 体力 +20")
        else:
            s.addMotivation(-1)
            _rep(s, "抽獎 空運: 幹勁 -1")
    elif s.turn == 50:  # 固有等級+1
        s.skillScore += 170
    elif s.turn == 54:  # 第三年繼承
        _inheritance(s, rng)
        _rep(s, "第三年繼承: 青因子%+因子 (能力/SP獎勵)")
        if s.getYayoiJiBan() >= 60:
            s.skillScore += 170
            s.addMotivation(1)
            _rep(s, "繼承: 逢坂親密≥60 → スキル+170 幹勁+1")
        else:
            s.addVital(-5)
            s.skillPt += 25
            _rep(s, "繼承: 逢坂親密<60 → 体力-5 SP+25")
    elif s.turn == 60:
        pass  # 第三年合宿開始
    elif s.turn == 69 and s.scenario == "aoharu":
        # シニア11月前半 結束：魂爆発回數結算限定スキル
        _aoharu_burst_skill(s)
        _rep(s, f"アオハル燃焼結算 (爆発{s.aoharuBurstCount}回)")
    elif s.turn == 71:  # 固有等級+1
        s.skillScore += 170
    elif s.turn == 78:  # ura3 結算
        rep = s.friendshipNoncardReporter
        if rep >= 80:
            s.addAllStatus(5); s.skillPt += 20
        elif rep >= 60:
            s.addAllStatus(3); s.skillPt += 10
        elif rep >= 40:
            s.skillPt += 10
        else:
            s.skillPt += 5
        s.addAllStatus(40)
        s.addAllStatus(5)
        s.skillPt += 20
        _rep(s, "URA 結算: 全能力大幅加成 + SP")


def _inheritance(s, rng):
    for i in range(5):
        s.addStatus(i, s.zhongMaBlueCount[i] * 6)
    factor = (rng.randrange(65536) / 65536.0) * 2
    for i in range(5):
        s.addStatus(i, int(factor * s.zhongMaExtraBonus[i]))
    s.skillPt += int((0.5 + 0.5 * factor) * s.zhongMaExtraBonus[5])
    for i in range(5):
        s.fiveStatusLimit[i] += s.zhongMaBlueCount[i] * 2
    for i in range(5):
        s.fiveStatusLimit[i] += rng.randrange(8)


def _recruit_names(s, fromCount):
    aoh = _scn("aoharu")
    members = aoh.get("members") or []
    recruit = aoh.get("recruit") or []
    names = []
    for idx in range(fromCount, len(s.aoharuMemberActive)):
        if s.aoharuMemberActive[idx]:
            if idx < len(members):
                names.append(members[idx]["name"])
            else:
                j = idx - len(members)
                if j < len(recruit):
                    names.append(recruit[j]["name"])
    return ", ".join(names) if names else ""


# ---- 合法行動 ----
def legalActions(s):
    if s.isCurrRacing():
        return [RACE]
    if s.scenario == "aoharu":
        # アオハル盃每回合 5 個訓練欄都可點選
        out = list(range(NUM_TRAININGS))
    else:
        hasCard = [any(0 <= p < 6 for p in s.personDist[t]) for t in range(NUM_TRAININGS)]
        if any(hasCard):
            out = [t for t in range(NUM_TRAININGS) if hasCard[t]]
        else:
            out = list(range(NUM_TRAININGS))
    if not s.isXiahesu():
        out.append(REST)
    out.append(OUTING)
    if s.isRaceAvailable():
        out.append(RACE)
    return out


def hasGoodShiningToday(s, trainingType):
    for i in range(NUM_CARDS):
        if (s.cardNow[i] == trainingType and s.deck[i].cardType == trainingType
                and s.cardBond[i] >= 80):
            return True
    return False


# ---- 手寫策略 (HandwrittenLogic 移植, 供 rollout 使用) ----
def _status_soft(x, reserve, reserveInvX2):
    if x >= 0:
        return 0
    if x > -reserve:
        return -x * x * reserveInvX2
    return x + 0.5 * reserve


def _status_gain_evaluation(s):
    result = [0.0] * 5
    remainTurn = TOTAL_TURN - s.turn
    reserve = 40.0 * remainTurn * (1 - remainTurn / (TOTAL_TURN * 2))
    reserveInvX2 = 1 / (2 * reserve + 1e-12)
    finalBonus0 = 75.0
    if remainTurn >= 1:
        finalBonus0 += 20
    if remainTurn >= 2:
        finalBonus0 += 20
    remain = [0.0] * NUM_STATS
    remainLim = [0.0] * NUM_STATS
    for i in range(5):
        remainLim[i] = s.fiveStatusLimit[i] - s.stats[i] - finalBonus0
        lim = s.fiveStatusLimit[i]
        if s.statTargets:
            t = s.statTargets[i] if len(s.statTargets) > i else 0
            if t and t > 0:
                lim = min(lim, t)
        remain[i] = lim - s.stats[i] - finalBonus0
    for tra in range(5):
        res = 0.0
        for sta in range(5):
            w = s.statWeights[sta]
            # 已超過目標: 主屬性收益壓低但不歸零 (保留副訓練/技能點/羈絆的價值)
            goalOver = (s.statTargets is not None and len(s.statTargets) > sta
                        and s.statTargets[sta] > 0 and remain[sta] < 0)
            if goalOver:
                full = 6.0 * (_status_soft(s.trainValue[tra][sta] - remainLim[sta],
                                           reserve, reserveInvX2)
                              - _status_soft(-remainLim[sta], reserve, reserveInvX2))
                res += w * max(0.0, OVER_GOAL_FLOOR * full)
            else:
                s0 = _status_soft(-remain[sta], reserve, reserveInvX2)
                s1 = _status_soft(s.trainValue[tra][sta] - remain[sta],
                                  reserve, reserveInvX2)
                res += w * 6.0 * (s1 - s0)
        res += PT_SCORE_RATE * s.trainValue[tra][5]
        result[tra] = res
    return result


def _vital_evaluation(vital, maxVital):
    if vital <= 50:
        return 2.0 * vital
    if vital <= 70:
        return 1.5 * (vital - 50) + _vital_evaluation(50, maxVital)
    if vital <= maxVital:
        return 1.0 * (vital - 70) + _vital_evaluation(70, maxVital)
    return _vital_evaluation(maxVital, maxVital)


def _calc_max_vital_eq(s):
    t = s.turn
    if t >= 77:
        return 0
    if t > 72:
        return 10
    if t == 72:
        return 30
    nonRace = 0
    for i in range(72, t, -1):
        if i not in s.raceTurns:
            nonRace += 1
        if nonRace >= 6:
            break
    eq = 30 + 15 * nonRace
    return min(eq, s.maxVital)


def _action_values(s):
    """計算各行動的立即值 {action: value}（rolloutPolicy 挑選 / MCTS 候選篩選共用）。"""
    values = {}

    vitalFactor = 3.5 + (s.turn / TOTAL_TURN) * (7.0 - 3.5)
    maxVitalEq = _calc_max_vital_eq(s)
    vitalBefore = _vital_evaluation(min(maxVitalEq, s.stamina), s.maxVital)

    # 休息/外出
    if s.isXiahesu():
        act, vitalGain = OUTING, 40
    else:
        act, vitalGain = REST, 50
    # 回復計分上限 = 安全訓練線 (70), 不是滿體: 體力夠高 (≥70) 時休息幾乎無效，
    # 愈接近滿體的回復邊際價值愈低——只剩「回到可安全練欄」的實際價值。
    vitSafe = min(maxVitalEq, 70)
    afterRest = min(vitSafe, vitalGain + s.stamina)
    if afterRest > s.stamina:
        value = vitalFactor * (_vital_evaluation(afterRest, s.maxVital) - vitalBefore)
    else:
        value = 0.0
    if s.mood < 5 and act == OUTING and afterRest > s.stamina:
        value += 200
    values[act] = value

    # 額外比賽
    if s.isRaceAvailable():
        afterRace = min(maxVitalEq, -15 + s.stamina)
        # アオハル盃は練習(特訓)優先，目標以外の出走は控えるべき。
        # 額外比賽在 aoharu 的價值遠低於 URA (會吃掉一週的特訓機會)。
        raceFlat = 40 if s.scenario == "aoharu" else 150
        value = raceFlat + vitalFactor * (_vital_evaluation(afterRace, s.maxVital) - vitalBefore)
        values[RACE] = value

    statusE = _status_gain_evaluation(s)
    carded = [any(0 <= p < 6 for p in s.personDist[t]) for t in range(5)]
    if not any(carded):
        carded = [True] * 5
    for tra in range(5):
        if not carded[tra]:
            continue
        value = statusE[tra]
        hintIds = [pid for pid in s.personDist[tra] if 0 <= pid < 6 and s.hintNow[pid]]
        hintProb = 1.0 / len(hintIds) if hintIds else 0.0
        for h in range(5):
            pid = s.personDist[tra][h]
            if pid < 0:
                break
            if pid < 6:
                if s.deck[pid].cardType in (0, 1, 2, 3, 4) and s.cardBond[pid] < 80:
                    jAdd = min(80 - s.cardBond[pid], 7)
                    value += jAdd * 12
        for pid in hintIds:
            lv = s.deck[pid].hintLevel or 0
            hb = 1.6 * 30 if lv == 0 else HINT_PT_RATE * PT_SCORE_RATE * lv
            value += hb * hintProb

        afterTrain = min(maxVitalEq, s.trainVitalChange[tra] + s.stamina)
        # 體力扣罰依失敗率縮放: 低失敗率 (<~20%) 的好訓練即使體力低也該點
        # ——真正傷害是失敗/大失敗，不是耗體本身。fail 0% → 懲罰減半。
        _pen = 0.5 + s.failRate[tra] / 100.0
        value += 1.0 * vitalFactor * _pen * (_vital_evaluation(afterTrain, s.maxVital) - vitalBefore)

        # 高體力機會成本: 體力高時優先消耗 (智自回體無此優勢)，避免扣體訓練長局被低估
        vitalCost = -s.trainVitalChange[tra]
        if s.stamina >= 70 and vitalCost > 0:
            value += 5.0 * vitalCost * max(0.0, min(1.0, (s.stamina - 60) / 40.0))

# アオハル特訓價值: 這欄有幾名部活成員 → 囤渦/快爆發的期望。
        # (真實 aoharu 核心是「特訓人數多且接近魂爆発のトレ優先」)
        if s.scenario == "aoharu":
            tk = _scn("aoharu")["tokkun"]
            bst = _scn("aoharu")["burst"]
            gaugeMax = int(tk["gaugeMax"])
            memberValue = 0.0
            nPart = 0  # 該欄實際會成長/爆發的成員數（含標記）
            for p in s.personDist[tra]:
                if not (10 <= p < 10 + len(s.aoharuMemberActive)):
                    continue
                idx = p - 10
                if not s.aoharuMemberActive[idx]:
                    continue
                if s.aoharuMemberArrow[idx] != tra:
                    continue
                g = s.aoharuMemberGauge[idx]
                if s.aoharuMemberBurst[idx]:
                    memberValue += 8.0  # 已爆發：剩極爆機會 + 成員續成長
                    nPart += 1
                else:
                    eff = min(g + 1, gaugeMax)
                    nearBurst = 70.0 if eff == gaugeMax else 0.0
                    memberValue += eff * 5.0 + nearBurst
                    nPart += 1
            # 魂爆/極爆標記: 點選即爆発。拉力依該欄參與人數縮放：
            # 單爆 = 整個訓練欄只有標記者一人 (無其他人參與)，價值極低；
            # 該欄參與的人多 (站欄者 + 標記者) 就不是單爆，標記價值回到全額。
            _part = set()
            for p in s.personDist[tra]:
                if not (10 <= p < 10 + len(s.aoharuMemberActive)):
                    continue
                idx = p - 10
                if s.aoharuMemberActive[idx]:
                    _part.add(idx)
            _part.update(s.aoharuSoulDict[tra])
            _part.update(s.aoharuSPDict[tra])
            markN = len(_part)

            def _mark_scale(n):
                if n >= 3:
                    return 1.0
                if n == 2:
                    return 0.55
                return 0.18  # 單爆（無人參與）近乎無吸引力
            sscale = _mark_scale(markN)
            if s.aoharuSoulDict[tra]:
                memberValue += 115.0 * sscale
            if s.aoharuSPDict[tra]:
                memberValue += 145.0 * sscale
            value += memberValue

        failRate = s.failRate[tra]
        if failRate > 0:
            bigFailProb = failRate if failRate >= 20 else 0
            failValueAvg = 0.01 * bigFailProb * (-500) + (1 - 0.01 * bigFailProb) * (-150)
            value = 0.01 * failRate * failValueAvg + (1 - 0.01 * failRate) * value

        # 面板祝福: 真實主屬性成長 ≥2x 該訓練基礎值 (遊戲給的大面板), 0%失敗時加權
        level = s.getTrainingLevel(tra)
        basicTable = _scn(s.scenario).get("trainingBasicValue") or TRAINING_BASIC_VALUE
        rowIdx = level - 1 if s.scenario == "aoharu" else level
        mainBase = basicTable[tra][rowIdx][tra]
        if mainBase > 0:
            mult = s.trainValue[tra][tra] / mainBase
            if mult >= 2.0 and s.failRate[tra] == 0:
                value += 60.0 * min(mult - 1.5, 1.5)

        values[tra] = value

    return values


def rolloutPolicy(s, rng):
    if s.isCurrRacing():
        return RACE
    bestValue, bestAction = -1e4, REST
    for a, value in _action_values(s).items():
        if value > bestValue:
            bestValue, bestAction = value, a
    return bestAction


def rolloutToEnd(s, rng):
    while not s.isTerminal():
        a = rolloutPolicy(s, rng)
        s = applyAction(s, a, rng)
    return s


# ---- 計分 ----
def _get_skill_score(s):
    return PT_SCORE_RATE * s.skillPt + s.skillScore


# 上面 _applyEffect 需要 jiBan / pid，重寫成乾淨版本：
def _correct_card_effect(s, pid, tra, isShining, headNum, shiningNum):
    c = s.deck[pid]
    eff = {
        "youQing": c.youQing(), "ganJing": c.ganJing(), "xunLian": c.xunLian(),
        "bonus": list(c.cardBonus) + [c.skillPtBonus],
        "vitalBonus": c.wizVitalBonus,
        "failRateDrop": c.failRateDrop, "vitalCostDrop": c.vitalCostDrop,
    }

    def apply(k, v):
        if k == 1:
            eff["youQing"] = (100 + eff["youQing"]) * (100 + v) / 100 - 100
        elif k == 2:
            eff["ganJing"] += v
        elif k == 8:
            eff["xunLian"] += v
        elif k == 27:
            eff["failRateDrop"] = 100 - (100 - eff["failRateDrop"]) * (100 - v) / 100
        elif k == 28:
            eff["vitalCostDrop"] = 100 - (100 - eff["vitalCostDrop"]) * (100 - v) / 100
        elif k == 31:
            eff["vitalBonus"] += v
        elif 3 <= k <= 7:
            eff["bonus"][k - 3] += v
        elif k == 30:
            eff["bonus"][5] += v
        elif k == 41:
            for i in range(5):
                eff["bonus"][i] += 1

    etype = c.uniqueEffectType
    args = list(c.uniqueEffectParam or [])
    jiBan = s.cardBond[pid]
    cardID = c.cardId or 0

    if etype in (1, 2):
        if jiBan >= (args[1] if len(args) > 1 else 0):
            if len(args) > 2 and args[2] > 0:
                apply(args[2], args[3])
            if len(args) > 4 and args[4] > 0:
                apply(args[4], args[5])
            if cardID // 10 == 30137:
                apply(1, 10); apply(2, 15)
    elif etype == 3:
        if jiBan >= (args[1] if len(args) > 1 else 0) and c.cardType != tra:
            eff["xunLian"] += 20
    elif etype == 4:
        rate = (0.0 if s.turn <= 33 else
                0.2 if s.turn <= 40 else
                0.25 if s.turn <= 42 else
                0.7 if s.turn <= 58 else 1.0)
        eff["xunLian"] += rate * (args[2] if len(args) > 2 else 0)
    elif etype == 5:
        pass
    elif etype == 6:
        a1 = args[1] if len(args) > 1 else 0
        a3 = args[3] if len(args) > 3 else 0
        apply(1, max(0, min(a1, a1 - s.trainClicked[pid])) * a3)
    elif etype == 7:
        expectedVital = s.stamina + s.trainVitalChange[tra]
        rate = max(0.3, min(1.0, expectedVital / max(1, s.maxVital)))
        a5 = args[5] if len(args) > 5 else 0
        a2 = args[2] if len(args) > 2 else 0
        apply(1, a5 + int(a2 * (1 - rate) / 0.7))
    elif etype == 8:
        eff["xunLian"] += 5 + 3 * max(0, min(5, (s.maxVital - 100) // 4))
    elif etype == 9:
        rate = sum(s.cardBond) / 600.0
        eff["xunLian"] += rate * 20
    elif etype == 10:
        eff["xunLian"] += (args[2] if len(args) > 2 else 0) * min(5, headNum)
    elif etype == 11:
        eff["xunLian"] += (args[2] if len(args) > 2 else 0) * min(5, 1 + s.getTrainingLevel(tra))
    elif etype == 12:
        pass
    elif etype == 13:
        if shiningNum >= 1:
            apply(args[1] if len(args) > 1 else 0, args[2] if len(args) > 2 else 0)
    elif etype == 14:
        rate = max(0.0, min(1.0, s.stamina / 100.0))
        eff["xunLian"] += 5 + 15 * rate
    elif etype == 15 or etype == 18 or etype == 19 or etype == 22:
        pass
    elif etype == 16:
        if len(args) > 1:
            if args[1] == 1:
                count = 1 + s.turn // 6
            elif args[1] == 2:
                count = int(0.7 + s.turn / 12.0)
            elif args[1] == 3:
                count = int(0.4 + s.turn / 15.0)
            else:
                count = 0
        else:
            count = 0
        if len(args) > 4:
            count = min(count, args[4])
        if len(args) > 2:
            apply(args[2], (args[3] if len(args) > 3 else 0) * count)
    elif etype == 17:
        count = 0
        for i in range(5):
            count += min(5, 1 + s.getTrainingLevel(i))
        eff["xunLian"] += (count / 25.0) * (args[3] if len(args) > 3 else 0)
    elif etype == 20:
        if jiBan >= 80:
            cardTypeCount = [0] * 7
            for i in range(6):
                t = s.deck[i].cardType
                cardTypeCount[t] += 1
            cardTypeCount[5] += cardTypeCount[6]
            for i in range(6):
                if cardTypeCount[i] > 2:
                    cardTypeCount[i] = 2
            for i in range(5):
                if cardTypeCount[i] > 0:
                    apply(i + 3, cardTypeCount[i])
            if cardTypeCount[5] > 0:
                apply(30, cardTypeCount[5])
    elif etype == 21:
        cardTypeCount = [0] * 7
        for i in range(6):
            t = s.deck[i].cardType
            cardTypeCount[t] += 1
        cardTypes = sum(1 for x in cardTypeCount if x > 0)
        if len(args) > 0 and cardTypes >= args[0]:
            if len(args) > 2:
                apply(args[1], args[2])
    return eff


# 把 _cardEffect 指向正確版本
def _card_effect_fixed(s, pid, tra, isShining, headNum, shiningNum):
    return _correct_card_effect(s, pid, tra, isShining, headNum, shiningNum)


GameState._cardEffect = _card_effect_fixed


def evaluate(s):
    """評價點 (= finalScore_rank)。"""
    return finalScoreRank(s)


def finalScoreRank(s):
    """評價點 (= finalScore_rank)。依照 s.strategy 對屬性/技能加權。

    strategy = {"weight": [速,耐,力,根,智] 權重 (預設全 1),
                "skill": 技能分 (2*skillPt + skillScore) 權重}
    """
    total = 0
    strat = s.strategy or {}
    w = strat.get("weight") or [1.0] * NUM_STATS
    for i in range(5):
        idx = min(int(s.stats[i]), int(s.fiveStatusLimit[i]))
        sc = FIVE_STATUS_FINAL_SCORE[idx] if idx < len(FIVE_STATUS_FINAL_SCORE) else FIVE_STATUS_FINAL_SCORE[-1]
        total += (float(w[i]) if i < len(w) else 1.0) * sc
    total += float(strat.get("skill") or 1.0) * int(_get_skill_score(s))
    return total


def finalScore(s):
    return finalScoreRank(s)


GameState.evaluate = evaluate
GameState.finalScoreRank = finalScoreRank
GameState.finalScore = finalScore