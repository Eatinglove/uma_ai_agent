"""carddata.py: 從遊戲 master.mdb 導出的最新 cardDB.json (489 張支援卡) / umaDB.json (224 隻馬) 建立資料。

UI cardDB 格式 (cardValue[0..4] = 突破次數):
  cardType: 0速 1耐 2力 3根 4智 5友 6團
  bonus[6]: [速,耐,力,根,智,pt]
  initialBonus[6]: [速,耐,力,根,智,pt]
  youQing: 友情% (閃彩乘算)   ganJing: 幹勁% (心情乘區)
  xunLian: 訓練%               initialJiBan: 初始羈絆
  deYiLv: 得意率%              hintLevel: 技能啟發等級
  saiHou: 賽後%                hintProbIncrease: 啟發出現率%
  failRateDrop / vitalCostDrop: 失敗率/體力消費下降%
  wizVitalBonus: 智彩圈回體
"""
import json
import os

from simulator import SupportCard, TRAIN_SPEED, TRAIN_STAMINA, TRAIN_POWER, TRAIN_GUTS, WIZ

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CARD_DB_PATH = os.path.join(DATA_DIR, "cardDB.json")
UMA_DB_PATH = os.path.join(DATA_DIR, "umaDB.json")

TYPE_NAMES = {0: "速", 1: "耐", 2: "力", 3: "根", 4: "智", 5: "友", 6: "團"}
_TYPE_TO_ENUM = {0: TRAIN_SPEED, 1: TRAIN_STAMINA, 2: TRAIN_POWER,
                 3: TRAIN_GUTS, 4: WIZ, 5: WIZ, 6: WIZ}
_ENUM_TO_TYPE = {v: k for k, v in _TYPE_TO_ENUM.items()}

_db = None
_db_loaded = False
_ssr_avg = {}
_uma_db = None
_uma_loaded = False


def load_card_db(force=False):
    global _db, _db_loaded, _ssr_avg
    if _db_loaded and not force:
        return _db
    _db = {}
    with open(CARD_DB_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    sums = {}
    counts = {}

    for sid, entry in raw.items():
        cardId = int(sid)
        cardType = int(entry.get("cardType") or 0)
        rarity = entry.get("rarity")
        name = entry.get("cardName") or f"[?]卡{cardId}"
        for x, v in enumerate(entry.get("cardValue") or []):
            if not v.get("filled", True):
                continue
            bonus = (v.get("bonus") or [0] * 6)[:6]
            initial = (v.get("initialBonus") or [0] * 6)[:6]
            card = SupportCard(
                name=name,
                type=_TYPE_TO_ENUM.get(cardType, WIZ),
                cardBonus=bonus[:5],
                skillPtBonus=bonus[5] if len(bonus) > 5 else 0,
                initStats=initial[:5],
                initSkillPt=initial[5] if len(initial) > 5 else 0,
                initialBond=int(v.get("initialJiBan") or 0),
                friendPct=float(v.get("youQing") or 0),
                moodPct=float(v.get("ganJing") or 0),
                trainPct=float(v.get("xunLian") or 0),
                specialtyRate=float(v.get("deYiLv") or 0),
                bondBonusStat=[0] * 5, bondBonusSkillPt=0,
                bondBonusFriendPct=0, bondBonusMoodPct=0, bondBonusTrainPct=0,
                cardId=cardId, rarity=rarity,
                hintLevel=int(v.get("hintLevel") or 0),
                saiHou=float(v.get("saiHou") or 0),
                hintProb=float(v.get("hintProbIncrease") or 0),
                failRateDrop=float(v.get("failRateDrop") or 0),
                vitalCostDrop=float(v.get("vitalCostDrop") or 0),
                wizVitalBonus=int(v.get("wizVitalBonus") or 0),
                cardType=cardType,
                uniqueEffectType=int(entry.get("uniqueEffectType") or 0),
                uniqueEffectParam=entry.get("uniqueEffectParam"))
            _db.setdefault(cardId, {})[x] = card
            # SSR 滿破平均 (缺卡 fallback)
            if rarity == 3 and x == 4:
                t = card.type
                if t not in sums:
                    sums[t] = [0.0] * 5
                    counts[t] = 0
                s = sums[t]
                for k in range(5):
                    s[k] += card.cardBonus[k]
                s[4] += card.skillPtBonus
                counts[t] += 1

    for t, count in counts.items():
        s = sums[t]
        _ssr_avg[t] = SupportCard(
            name=f"[{TYPE_NAMES.get(t, '?')}]平均SSR", type=t,
            cardBonus=[round(a / count, 2) for a in s[:5]],
            skillPtBonus=round(s[4] / count, 2),
            initStats=[0] * 5, initSkillPt=0, initialBond=0,
            friendPct=0.0, moodPct=0.0, trainPct=0.0, specialtyRate=0.0,
            bondBonusStat=[0] * 5, bondBonusSkillPt=0,
            bondBonusFriendPct=0, bondBonusMoodPct=0, bondBonusTrainPct=0,
            cardId=None, rarity=3)

    _db_loaded = True
    return _db


def _missing_card_type(cid):
    """未知卡 → 卡型: 由 cardId 逼近已知相似卡型 (SSR 一律當速卡近似)。"""
    return TRAIN_SPEED


def _fallback_for_missing(cid, info):
    return _ssr_avg.get(TRAIN_SPEED, _generic_fallback(TRAIN_SPEED))


def load_uma_db(force=False):
    """載入最新馬娘資料 (umaDB.json, 來自 master.mdb)。"""
    global _uma_db, _uma_loaded
    if _uma_loaded and not force:
        return _uma_db
    with open(UMA_DB_PATH, encoding="utf-8") as f:
        _uma_db = json.load(f)
    _uma_loaded = True
    return _uma_db


def uma_name(card_id):
    """馬娘卡 id (如 104603) → 名字。"""
    if not card_id:
        return None
    return load_uma_db().get(str(card_id), {}).get("name")


def cardtype_name(card):
    """支援卡 enum type → 型別名稱 (速/耐/力/根/智/友/團)。"""
    orig = getattr(card, "cardType", None)
    if orig is not None and orig in TYPE_NAMES:
        return TYPE_NAMES[orig]
    return "?"


def build_deck_from(support_cards):
    """用玩家實際支援卡組 (封包 support_card_array) 建 deck (6 張)。"""
    db = load_card_db()
    deck = []
    missing = []
    ordered = sorted(support_cards or [], key=lambda c: c.get("position") or 0)
    for info in ordered[:6]:
        cid = int((info or {}).get("support_card_id") or 0)
        lb = min(4, max(0, int((info or {}).get("limit_break_count") or 0)))
        entry = db.get(cid)
        if entry and lb in entry:
            deck.append(entry[lb])
        elif entry:
            keys = sorted(entry.keys())
            deck.append(entry[min(keys, key=lambda k: abs(k - lb))])
        else:
            missing.append(cid)
            deck.append(_fallback_for_missing(cid, info))
    if missing:
        print(f"[carddata] missing cards, using SSR avg fallback: {missing}", flush=True)
    return deck


def _generic_fallback(cardType):
    return SupportCard(
        name="[?]未知卡", type=cardType,
        cardBonus=[0, 0, 0, 0, 0], skillPtBonus=0,
        initStats=[0] * 5, initSkillPt=0, initialBond=0,
        friendPct=20.0, moodPct=20.0, trainPct=10.0, specialtyRate=60.0,
        bondBonusStat=[0] * 5, bondBonusSkillPt=0,
        bondBonusFriendPct=0, bondBonusMoodPct=0, bondBonusTrainPct=0,
        cardId=None, rarity=3)