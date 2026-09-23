#include "simulator.hpp"

#include <algorithm>
#include <limits>
#include <numeric>
#include <set>
#include <utility>

#include "five_status_score.inc"

// ===========================================================
// 常數 (對齊 python_app/simulator.py)
// ===========================================================
constexpr double PT_SCORE_RATE = 2.0;
constexpr int HINT_PT_RATE = 4;
constexpr double OVER_GOAL_FLOOR = 0.30;  // 目標超過後主屬性收益壓低倍率

// TrainingBasicValue[訓練][Lv 0..4][速,耐,力,根,智,pt,體力]
static const int TRAINING_BASIC_VALUE[NUM_TRAININGS][5][7] = {
    { {11,0,2,0,0,5,-19},{12,0,2,0,0,5,-20},{13,0,2,0,0,5,-21},{14,0,3,0,0,5,-23},{15,0,4,0,0,5,-25} },
    { {0,10,0,4,0,5,-20},{0,11,0,4,0,5,-21},{0,12,0,5,0,5,-22},{0,13,0,5,0,5,-24},{0,14,0,6,0,5,-26} },
    { {0,4,10,0,0,5,-20},{0,4,11,0,0,5,-21},{0,5,12,0,0,5,-22},{0,5,13,0,0,5,-24},{0,6,14,0,0,5,-26} },
    { {2,0,2,9,0,5,-20},{2,0,2,10,0,5,-21},{2,0,2,11,0,5,-22},{3,0,2,12,0,5,-24},{4,0,3,13,0,5,-26} },
    { {2,0,0,0,8,5,5},{2,0,0,0,9,5,5},{2,0,0,0,10,5,5},{3,0,0,0,11,5,5},{4,0,0,0,12,5,5} },
};

// FailRateBasic[訓練][Lv]
static const int FAIL_RATE_BASIC[NUM_TRAININGS][5] = {
    {520,524,528,532,536},
    {507,511,515,519,523},
    {516,520,524,528,532},
    {532,536,540,544,548},
    {320,321,322,323,324},
};

// ===========================================================
// アオハル盃 (aoharu) 靜態資料 (對齊 scenarios.py aoharu())
// ===========================================================
static const double AOHARU_MEMBER_APPEAR_RATE = 5.0 / 6.0;
static const double AOHARU_MEMBER_ARROW_RATE = 0.4;
static const double AOHARU_SOUL_MARK_RATE = 0.4;
static const double AOHARU_SP_MARK_RATE = 0.25;
static const int AOHARU_GAUGE_MAX = 5;
static const double AOHARU_TOKKUN_TRIGGER_RATE = 0.9;
static const double AOHARU_TOKKUN_HINT_RATE = 0.15;
static const int AOHARU_TOKKUN_HINT_PT = 8;
static const int AOHARU_BURST_HINT_PT = 15;
static const int AOHARU_PRE_RACE_RECRUIT_TURN = 23;
static const int AOHARU_LINK_COUNT = 4;
static const int AOHARU_SUPPORT_MEMBER_COUNT = 5;
static const int AOHARU_FILL_TO_BEFORE_P1 = 10;
static const int AOHARU_POST_RACE_RECRUIT_MAX = 4;
static const int AOHARU_BURST_SKILL_TURN = 69;

// 訓練基礎值 [訓練][Lv 1..5 對應 idx 0..4][速,耐,力,根,智,pt,體力] (scenarios.py aoharu)
static const int AOHARU_TRAINING_BASIC_VALUE[NUM_TRAININGS][5][7] = {
    { {8,0,4,0,0,4,-19},{9,0,4,0,0,4,-20},{10,0,4,0,0,4,-21},{11,0,5,0,0,4,-23},{12,0,6,0,0,4,-25} },
    { {0,8,0,6,0,4,-20},{0,9,0,6,0,4,-21},{0,10,0,6,0,4,-22},{0,11,0,7,0,4,-24},{0,12,0,8,0,4,-26} },
    { {0,4,9,0,0,4,-20},{0,4,10,0,0,4,-21},{0,4,11,0,0,4,-22},{0,5,12,0,0,4,-24},{0,6,13,0,0,4,-26} },
    { {3,0,3,6,0,4,-20},{3,0,3,7,0,4,-21},{3,0,3,8,0,4,-22},{4,0,3,9,0,4,-24},{4,0,4,10,0,4,-26} },
    { {2,0,0,0,6,5,5},{2,0,0,0,7,5,5},{2,0,0,0,8,5,5},{3,0,0,0,9,5,5},{4,0,0,0,10,5,5} },
};

// 特訓成長 [訓練][count-cap 1..5 對應 idx 0..4][速,耐,力,根,智,pt]
static const int AOHARU_TOKKUN_BYCOUNT[NUM_TRAININGS][5][6] = {
    { {0,0,0,0,0,0},{2,0,0,0,0,0},{4,0,1,0,0,1},{6,0,3,0,0,2},{8,0,4,0,0,3} },
    { {0,0,0,0,0,0},{0,2,0,0,0,0},{0,4,0,1,0,1},{0,6,0,2,0,2},{0,8,0,3,0,3} },
    { {0,0,0,0,0,0},{0,0,2,0,0,0},{0,1,4,0,0,1},{0,2,6,0,0,2},{0,3,8,0,0,3} },
    { {0,0,0,0,0,0},{0,0,0,2,0,0},{1,0,1,4,0,1},{2,0,2,5,0,2},{3,0,3,10,0,3} },
    { {0,0,0,0,0,0},{0,0,0,0,1,0},{0,0,0,0,2,1},{1,0,0,0,3,2},{2,0,0,0,4,3} },
};

// 特訓成員成長 [訓練][Lv idx][速,耐,力,根,智]
static const int AOHARU_TOKKUN_MEMBER_GAIN[NUM_TRAININGS][5][NUM_STATS] = {
    { {35,7,20,7,7},{45,8,25,8,8},{55,9,30,9,9},{65,10,35,10,10},{75,11,40,11,11} },
    { {7,35,7,20,7},{8,45,8,25,8},{9,55,9,30,9},{10,65,10,35,10},{11,75,11,40,11} },
    { {7,20,35,7,7},{8,25,45,8,8},{9,30,55,9,9},{10,35,65,10,10},{11,40,75,11,11} },
    { {18,7,18,35,7},{21,8,21,45,8},{24,9,24,55,9},{27,10,27,65,10},{30,11,30,75,11} },
    { {20,7,7,7,35},{25,8,8,8,45},{30,9,9,9,55},{35,10,10,10,65},{40,11,11,11,75} },
};

// 魂爆/極爆 bonus [tra][速,耐,力,根,智,pt] ; bonusLink=卡起爆時額外
static const int AOHARU_BURST_BONUS[NUM_TRAININGS][6] = {
    {15,0,7,0,0,0},{0,15,0,7,0,0},{0,7,15,0,0,0},{3,0,3,15,0,0},{2,0,0,0,10,5},
};
static const int AOHARU_BURST_BONUS_LINK[NUM_TRAININGS][6] = {
    {20,0,10,0,0,0},{0,20,0,10,0,0},{0,10,20,0,0,0},{5,0,5,20,0,0},{5,0,0,0,15,5},
};

// 成員爆発 gain [type 它那類?][速,耐,力,根,智] (type: 0速 1耐 2力 3根 4智)
static const int AOHARU_BURST_MEMBER_GAIN[5][NUM_STATS] = {
    {150,80,110,80,70},{80,150,80,110,70},{80,110,150,80,70},{90,80,90,150,70},{110,80,80,80,150},
};

// 團隊均值 → 訓練等級 (rankToLevel)
static const double AOHARU_RANK_TO_LEVEL_THRESH[][2] = {
    {610,5},{510,4},{420,3},{340,3},{260,2},{200,2},{150,1},
};

// 團隊排名獎勵 (rank→bonus)
static const int AOHARU_TEAM_RANK_BONUS[][2] = {
    {5,50},{9,30},{15,20},{20,10},{30,0},
};

struct AoharuOpponent {
    double avg;
    int winBoost;
    int winStat, winSp, loseStat, loseSp;
};
static const std::array<AoharuOpponent, 5> AOHARU_OPPONENT{{
    {175, -4, 3, 10, 1, 5},
    {275, -5, 3, 15, 1, 6},
    {375, -6, 4, 20, 2, 8},
    {375, -7, 5, 25, 2, 10},
    {425, -8, 7, 50, 3, 12},
}};
static const int AOHARU_TEAM_RACE_TURNS[5] = {24, 36, 48, 60, 72};

// 成員 meta (初始 6 相棒 + 4 NPC + 9 招募) 對齊 scenarios.py
struct AoharuMemberDef {
    int tid;
    int type;              // 0速 1耐 2力 3根 4智
    int deYiLv;
    bool npc;
    std::array<int, NUM_STATS> stat;
};
static const std::array<AoharuMemberDef, AOHARU_MAX_MEMBERS> AOHARU_MEMBER_DEFS{{
    {1,0,45,false,{30,22,22,22,22}},    {2,1,40,false,{22,30,22,22,22}},
    {3,0,42,false,{26,24,24,23,23}},    {4,4,45,false,{25,23,23,23,26}},
    {5,2,43,false,{24,23,26,23,24}},    {6,3,44,false,{23,24,24,26,23}},
    {1010,0,40,true,{34,24,24,24,24}},  {1030,1,40,true,{24,34,24,24,24}},
    {1052,4,40,true,{24,24,24,24,34}},  {1056,3,40,true,{24,24,24,34,24}},
    // 招募 (季前賽後)
    {1019,4,40,true,{24,24,30,24,30}},  {1038,0,40,true,{34,22,24,22,24}},
    {1080,2,40,true,{26,24,34,24,24}},  {1081,3,40,true,{24,24,24,34,24}},
    {101,0,40,true,{34,24,24,24,24}},   {103,1,40,true,{24,34,24,24,24}},
    {104,2,40,true,{24,24,34,24,24}},   {108,3,40,true,{24,24,24,34,24}},
    {109,4,40,true,{24,24,24,24,34}},
}};

static int aoharuMemberDeYiLv(int idx) {
    if (idx >= 0 && idx < AOHARU_MAX_MEMBERS) return AOHARU_MEMBER_DEFS[idx].deYiLv;
    return 40;
}
static int aoharuMemberType(int idx) {
    if (idx >= 0 && idx < AOHARU_MAX_MEMBERS) return AOHARU_MEMBER_DEFS[idx].type;
    return idx % 5;
}
static bool aoharuMemberNpc(int idx) {
    if (idx >= 0 && idx < AOHARU_MAX_MEMBERS) return AOHARU_MEMBER_DEFS[idx].npc;
    return true;
}
static std::array<int, NUM_STATS> aoharuMemberBaseStat(int idx) {
    if (idx >= 0 && idx < AOHARU_MAX_MEMBERS) return AOHARU_MEMBER_DEFS[idx].stat;
    return std::array<int, NUM_STATS>{30,30,30,30,30};
}

// 單一成員出線挑欄 (對齊 _club_bucket_pick)
static int aoharuClubBucketFor(int idx, std::mt19937& rng);

// member_bonus_fit.json 內嵌表 (key=tid)
struct AoharuBonusFit { int tid; double v[NUM_TRAININGS][NUM_STATS]; };
static const AoharuBonusFit AOHARU_MEMBER_BONUS_FIT[11] = {
    {1,    {{2.079,0,2.098,0,0},{0,2.673,0,1.623,0},{0,0.873,1.537,0,0},{0.173,0,0.662,0.406,0},{0.752,0,0,0,1.704}}},
    {2,    {{3.004,0,1.362,0,0},{0,3.716,0,2.626,0},{0,1.019,1.988,0,0},{2.606,0,1.242,2.03,0},{1.987,0,0,0,1.53}}},
    {3,    {{1.808,0,1.736,0,0},{0,0.858,0,1.037,0},{0,0.831,3.319,0,0},{0.563,0,1.709,1.159,0},{0.251,0,0,0,0.066}}},
    {4,    {{1.694,0,0.584,0,0},{0,1.8,0,1.216,0},{0,0.487,1.352,0,0},{0.637,0,0.621,1.273,0},{0.974,0,0,0,2.02}}},
    {5,    {{0.751,0,1.531,0,0},{0,2.101,0,1.862,0},{0,0.924,1.197,0,0},{0.636,0,0.567,1.272,0},{0.077,0,0,0,1.068}}},
    {6,    {{2.954,0,0.677,0,0},{0,1.514,0,1.153,0},{0,0.692,1.628,0,0},{1.667,0,0.231,1.061,0},{1.634,0,0,0,1.945}}},
    {103,  {{2.691,0,1.573,0,0},{0,1.983,0,2.377,0},{0,1.787,1.582,0,0},{0,0,0.281,0,0},{0.821,0,0,0,0.374}}},
    {1010, {{1.599,0,0.304,0,0},{0,2.968,0,1.662,0},{0,0.564,2.753,0,0},{1.104,0,0,0.959,0},{0,0,0,0,0.144}}},
    {1030, {{0.195,0,0,0,0},{0,0.522,0,0.953,0},{0,0.148,0.813,0,0},{0.201,0,0.115,0.221,0},{0.203,0,0,0,0.294}}},
    {1052, {{0,0,0.546,0,0},{0,1.011,0,0.633,0},{0,0.381,0,0,0},{0.636,0,0.058,0.515,0},{0,0,0,0,0.497}}},
    {1056, {{1.976,0,0.269,0,0},{0,0.37,0,0.095,0},{0,0.775,0.927,0,0},{0.028,0,0.631,0.392,0},{0.205,0,0,0,1.208}}},
};

// 團隊抽欄權重 (對齊 _aoharu_club_bucket_pick)
static std::vector<int> aoharuClubBucket(const GameState& s) {
    std::vector<int> probs{100,100,100,100,100,50};
    for (size_t i = 0; i < s.aoharuMemberActive.size(); ++i)
        if (s.aoharuMemberActive[i])
            probs[aoharuMemberType((int)i)] += aoharuMemberDeYiLv((int)i);
    return probs;
}

int aoharuAvgTier(double avg) {
    for (auto& t : AOHARU_RANK_TO_LEVEL_THRESH)
        if (avg >= t[0]) return (int)t[1];
    return 1;
}

static bool isAoharuTeamRaceTurn(const GameState& s) {
    for (int t : AOHARU_TEAM_RACE_TURNS) if (s.turn == t) return true;
    return false;
}

static int aoharuTeamRankBonus(int rank) {
    for (auto& r : AOHARU_TEAM_RANK_BONUS)
        if (rank <= r[0]) return r[1];
    return 0;
}

// ===========================================================
// 名稱
// ===========================================================
const char* actionName(int a) {
    static const char* names[COUNT] = {
        "速度訓練","耐力訓練","力量訓練","根性訓練","智力訓練",
        "休息","外出","比賽",
    };
    if (a < 0 || a >= COUNT) return "?";
    return names[a];
}

const char* moodName(int mood) {
    static const char* names[6] = {"?","絶不調","不調","普通","好調","絶好調"};
    if (mood < 1 || mood > 5) return "?";
    return names[mood];
}

// ===========================================================
// 隨機輔助 (對齊 random.Random 語義: randrange/random/choice/sample/shuffle)
// ===========================================================
inline int randrange(std::mt19937& rng, int n) {
    if (n <= 0) return 0;
    std::uniform_int_distribution<int> d(0, n - 1);
    return d(rng);
}
inline double randDouble(std::mt19937& rng) {
    std::uniform_real_distribution<double> d(0.0, 1.0);
    return d(rng);
}
inline bool randBool(std::mt19937& rng, double p) { return randDouble(rng) < p; }

// 加權抽選 (Python _weighted_pick): 傳回 weights 之 index
static int weightedPick(const std::vector<int>& weights, std::mt19937& rng) {
    long total = 0;
    for (int w : weights) total += w;
    long r = randrange(rng, (int)total);
    for (size_t i = 0; i < weights.size(); ++i) {
        r -= weights[i];
        if (r < 0) return (int)i;
    }
    return (int)weights.size() - 1;
}

static void shuffleList(std::vector<int>& v, std::mt19937& rng) {
    for (int i = (int)v.size() - 1; i > 0; --i) {
        int j = randrange(rng, i + 1);
        std::swap(v[i], v[j]);
    }
}

// 從 vector 抽 k 個不重覆 (順序為抽出順序)
static std::vector<int> sampleNoReplace(std::vector<int>& pool, int k, std::mt19937& rng) {
    std::vector<int> out;
    for (int i = 0; i < k && !pool.empty(); ++i) {
        int j = randrange(rng, (int)pool.size());
        out.push_back(pool[j]);
        pool[j] = pool.back();
        pool.pop_back();
    }
    return out;
}

// 單一成員出線挑欄 (對齊 _club_bucket_pick)
static int aoharuClubBucketFor(int idx, std::mt19937& rng) {
    std::vector<int> probs{100,100,100,100,100,50};
    probs[aoharuMemberType(idx)] += aoharuMemberDeYiLv(idx);
    return weightedPick(probs, rng);
}

// ===========================================================
// 屬性/體力/心情 (對齊 GameState.addStatus / addVital / ...)
// ===========================================================
double realStatusGain(int value, double gain) {
    if (gain <= 0) return gain;
    if (value >= 1200) return std::floor(gain / 2.0);
    return gain;
}

void addStatus(GameState& s, int idx, double value, bool over1200) {
    double gain = value;
    if (over1200 && gain > 0 && s.stats[idx] >= 1200)
        gain = std::floor(gain / 2.0);
    double t = s.stats[idx] + gain;
    if (t > s.fiveStatusLimit[idx]) t = s.fiveStatusLimit[idx];
    if (t < 1) t = 1;
    s.stats[idx] = t;
}

static void addAllStatus(GameState& s, double value) {
    for (int i = 0; i < NUM_STATS; ++i) addStatus(s, i, value);
}

void addVital(GameState& s, int value) {
    s.stamina += value;
    if (s.stamina > s.maxVital) s.stamina = s.maxVital;
    if (s.stamina < 0) s.stamina = 0;
}

void addMotivation(GameState& s, int value) {
    if (value < 0) {
        if (s.isPositiveThinking) {
            s.isPositiveThinking = false;
        } else {
            s.mood += value;
            if (s.mood < 1) s.mood = 1;
        }
    } else {
        s.mood += value;
        if (s.mood > 5) s.mood = 5;
    }
}

void addJiBan(GameState& s, int idx, int value) {
    if (idx == 6) {
        s.friendshipNoncardYayoi += value;
        if (s.friendshipNoncardYayoi > 100) s.friendshipNoncardYayoi = 100;
    } else if (idx == 7) {
        s.friendshipNoncardReporter += value;
        if (s.friendshipNoncardReporter > 100) s.friendshipNoncardReporter = 100;
    } else {
        s.cardBond[idx] += value;
        if (s.cardBond[idx] > 100) s.cardBond[idx] = 100;
    }
}

void addTrainingLevelCount(GameState& s, int idx, int n) {
    s.trainCount[idx] += n;
    if (s.trainCount[idx] > 16) s.trainCount[idx] = 16;
}

// ===========================================================
// 卡片出場判定 (對齊 _card_train_probs)
// ===========================================================
static int cardTrainProbs(const GameState& s, int cardIdx, std::mt19937& rng) {
    const SupportCard& c = s.deck[cardIdx];
    if (c.cardType == 5 || c.cardType == 6)
        return weightedPick({100,100,100,100,100,100}, rng);
    int t = (c.cardType >= 0 && c.cardType <= 4) ? c.cardType : c.type;
    std::vector<int> probs{100,100,100,100,100,50};
    int d = (int)c.specialtyRate;
    if (d < 0) d = 0;
    probs[t] += d;
    return weightedPick(probs, rng);
}

// ===========================================================
// 有效加成 (對齊 _correct_card_effect)
// ===========================================================
struct CardEffect {
    double youQing = 0, ganJing = 0, xunLian = 0;
    std::array<int, 6> bonus{0,0,0,0,0,0};
    int vitalBonus = 0;
    double failRateDrop = 0, vitalCostDrop = 0;
};

static void effApply(CardEffect& e, int k, int v) {
    if (k == 1) {
        e.youQing = (100 + e.youQing) * (100 + v) / 100.0 - 100;
    } else if (k == 2) {
        e.ganJing += v;
    } else if (k == 8) {
        e.xunLian += v;
    } else if (k == 27) {
        e.failRateDrop = 100 - (100 - e.failRateDrop) * (100 - v) / 100.0;
    } else if (k == 28) {
        e.vitalCostDrop = 100 - (100 - e.vitalCostDrop) * (100 - v) / 100.0;
    } else if (k == 31) {
        e.vitalBonus += v;
    } else if (k >= 3 && k <= 7) {
        e.bonus[k - 3] += v;
    } else if (k == 30) {
        e.bonus[5] += v;
    } else if (k == 41) {
        for (int i = 0; i < NUM_STATS; ++i) e.bonus[i] += 1;
    }
}

static CardEffect cardEffect(const GameState& s, int pid, int tra, bool isShining,
                             int headNum, int shiningNum) {
    const SupportCard& c = s.deck[pid];
    CardEffect e;
    e.youQing = c.friendPct;
    e.ganJing = c.moodPct;
    e.xunLian = c.trainPct;
    for (int i = 0; i < NUM_STATS; ++i) e.bonus[i] = c.cardBonus[i];
    e.bonus[5] = c.skillPtBonus;
    e.vitalBonus = c.wizVitalBonus;
    e.failRateDrop = c.failRateDrop;
    e.vitalCostDrop = c.vitalCostDrop;

    const int etype = c.uniqueEffectType;
    const std::vector<double>& args = c.uniqueEffectParam;
    const int jiBan = s.cardBond[pid];
    const int cardID = 0;  // cardId 未序列化 (僅 etype 1/2 用 30137 特例 => 保留欄位)

#define ARG(i) ((args.size() > (i)) ? (int)args[i] : 0)

    if (etype == 1 || etype == 2) {
        if (jiBan >= ARG(1)) {
            if (args.size() > 2 && args[2] > 0) effApply(e, ARG(2), ARG(3));
            if (args.size() > 4 && args[4] > 0) effApply(e, ARG(4), ARG(5));
            // (cardID 特例 30137 於序列化時無法取得，直接略過; parall in py 只對 該卡)
        }
    } else if (etype == 3) {
        if (jiBan >= ARG(1) && c.cardType != tra) e.xunLian += 20;
    } else if (etype == 4) {
        double rate = (s.turn <= 33 ? 0.0 : s.turn <= 40 ? 0.2 :
                       s.turn <= 42 ? 0.25 : s.turn <= 58 ? 0.7 : 1.0);
        e.xunLian += rate * ARG(2);
    } else if (etype == 5 || etype == 12 || etype == 15 || etype == 18 ||
               etype == 19 || etype == 22) {
        // pass
    } else if (etype == 6) {
        int a1 = ARG(1), a3 = ARG(3);
        effApply(e, 1, std::max(0, std::min(a1, a1 - s.trainClicked[pid])) * a3);
    } else if (etype == 7) {
        int expectedVital = s.stamina + s.trainVitalChange[tra];
        double rate = std::max(0.3, std::min(1.0, (double)expectedVital / std::max(1, s.maxVital)));
        effApply(e, 1, ARG(5) + (int)(ARG(2) * (1 - rate) / 0.7));
    } else if (etype == 8) {
        e.xunLian += 5 + 3 * std::max(0, std::min(5, (s.maxVital - 100) / 4));
    } else if (etype == 9) {
        double rate = std::accumulate(s.cardBond.begin(), s.cardBond.end(), 0.0) / 600.0;
        e.xunLian += rate * 20;
    } else if (etype == 10) {
        e.xunLian += ARG(2) * std::min(5, headNum);
    } else if (etype == 11) {
        e.xunLian += ARG(2) * std::min(5, 1 + s.getTrainingLevel(tra));
    } else if (etype == 13) {
        if (shiningNum >= 1) effApply(e, ARG(1), ARG(2));
    } else if (etype == 14) {
        double rate = std::max(0.0, std::min(1.0, s.stamina / 100.0));
        e.xunLian += 5 + 15 * rate;
    } else if (etype == 16) {
        int count = 0;
        if (args.size() > 1) {
            if (args[1] == 1) count = 1 + s.turn / 6;
            else if (args[1] == 2) count = (int)(0.7 + s.turn / 12.0);
            else if (args[1] == 3) count = (int)(0.4 + s.turn / 15.0);
        }
        if (args.size() > 4) count = std::min(count, ARG(4));
        if (args.size() > 2) effApply(e, ARG(2), ARG(3) * count);
    } else if (etype == 17) {
        int count = 0;
        for (int i = 0; i < NUM_TRAININGS; ++i)
            count += std::min(5, 1 + s.getTrainingLevel(i));
        e.xunLian += (count / 25.0) * ARG(3);
    } else if (etype == 20) {
        if (jiBan >= 80) {
            std::array<int, 7> count{0,0,0,0,0,0,0};
            for (int i = 0; i < NUM_CARDS; ++i) count[s.deck[i].cardType]++;
            count[5] += count[6];
            for (int i = 0; i < 6; ++i) if (count[i] > 2) count[i] = 2;
            for (int i = 0; i < NUM_STATS; ++i)
                if (count[i] > 0) effApply(e, i + 3, count[i]);
            if (count[5] > 0) effApply(e, 30, count[5]);
        }
    } else if (etype == 21) {
        std::array<int, 7> count{0,0,0,0,0,0,0};
        for (int i = 0; i < NUM_CARDS; ++i) count[s.deck[i].cardType]++;
        int types = 0;
        for (int x : count) if (x > 0) types++;
        if (!args.empty() && types >= ARG(0) && args.size() > 2)
            effApply(e, ARG(1), ARG(2));
    }
#undef ARG
    return e;
}

// ===========================================================
// 失敗率 (對齊 _failureRate)
// ===========================================================
static int failureRate(const GameState& s, int trainType, double failRateMultiply) {
    int lev = s.getTrainingLevel(trainType);
    if (s.isAoharu) lev = std::max(0, std::min(4, lev - 1));  // aoharu level 1..5 -> fail table 0..4
    double x0 = 0.1 * FAIL_RATE_BASIC[trainType][lev];
    double f = 0.0;
    if (s.stamina < x0)
        f = (100 - s.stamina) * (x0 - s.stamina) / 40.0;
    if (f < 0) f = 0;
    if (f > 99) f = 99;
    f *= failRateMultiply;
    int fr = (int)std::ceil(f);
    fr += s.failureRateBias;
    if (fr < 0) fr = 0;
    if (fr > 100) fr = 100;
    return fr;
}

// ===========================================================
// 訓練計算 (對齊 _calcTrainingValueSingle)
// ===========================================================
static void calcTrainingValueSingle(GameState& s, int tra) {
    int level = s.getTrainingLevel(tra);
    int rowIdx = s.isAoharu ? std::max(0, level - 1) : level;
    const int* basicSrc = s.isAoharu ? AOHARU_TRAINING_BASIC_VALUE[tra][rowIdx]
                                     : TRAINING_BASIC_VALUE[tra][rowIdx];
    double basic[7];
    for (int i = 0; i < 7; ++i) basic[i] = basicSrc[i];
    int vitalCostBasic = -basicSrc[6];

    int headNum = 0;
    int shiningNum = 0;
    bool shiningRec[NUM_CARDS] = {false,false,false,false,false,false};

    double totalXunlian = 0;
    double totalGanjing = 0;
    double youQingMult = 1.0;
    double vitMult = 1.0;
    double failMult = 1.0;

    for (int h = 0; h < NUM_TRAININGS; ++h) {
        int pid = s.personDist[tra][h];
        if (pid < 0) break;
        if (pid == 8) { headNum++; continue; }
        if (s.isAoharu && pid >= 10) {
            int idx = pid - 10;
            if (idx >= 0 && idx < AOHARU_MAX_MEMBERS) {
                int tid = AOHARU_MEMBER_DEFS[idx].tid;
                for (auto& f : AOHARU_MEMBER_BONUS_FIT) {
                    if (f.tid == tid) {
                        for (int i = 0; i < NUM_STATS; ++i)
                            if (f.v[tra][i] > 0) basic[i] += f.v[tra][i];
                        break;
                    }
                }
            }
            continue;
        }
        if (pid >= 6) continue;
        headNum++;
        bool sh = s.isCardShining(pid, tra);
        if (sh) { shiningNum++; shiningRec[pid] = true; }
        CardEffect e = cardEffect(s, pid, tra, sh, headNum, shiningNum);
        for (int i = 0; i < 6; ++i)
            if (basic[i] > 0) basic[i] += (int)e.bonus[i];
        if (shiningRec[pid]) {
            youQingMult *= (1 + 0.01 * e.youQing);
            if (tra == TrainWit) vitalCostBasic -= e.vitalBonus;
        }
        totalXunlian += e.xunLian;
        totalGanjing += e.ganJing;
        vitMult *= (1 - 0.01 * e.vitalCostDrop);
        failMult *= (1 - 0.01 * e.failRateDrop);
    }
    s.isTrainShining[tra] = shiningNum > 0;

    int vc;
    if (vitalCostBasic > 0)
        vc = -(int)(vitalCostBasic * vitMult);
    else
        vc = -vitalCostBasic;
    if (vc > s.maxVital - s.stamina) vc = s.maxVital - s.stamina;
    if (vc < -s.stamina) vc = -s.stamina;
    s.trainVitalChange[tra] = vc;
    s.failRate[tra] = failureRate(s, tra, failMult);

    double cardMult = (1 + 0.05 * headNum) *
                      (1 + 0.01 * totalXunlian) *
                      (1 + 0.1 * (s.mood - 3) * (1 + 0.01 * totalGanjing)) *
                      youQingMult;

    for (int i = 0; i < 6; ++i) {
        double umaBonus = (i < NUM_STATS) ? 1 + 0.01 * s.fiveStatusBonus[i] : 1;
        double lower = basic[i] * cardMult * umaBonus;
        if (lower > 100) lower = 100;
        if (i < NUM_STATS) lower = realStatusGain((int)s.stats[i], lower);
        s.trainValue[tra][i] = lower;
    }
}

void calcTrainingValue(GameState& s) {
    for (int tra = 0; tra < NUM_TRAININGS; ++tra)
        calcTrainingValueSingle(s, tra);
}

// ===========================================================
// 卡片出場 + 訓練值 (對齊 cardRandom, URA)
// ===========================================================
void cardRandom(GameState& s, std::mt19937& rng) {
    for (auto& row : s.personDist)
        row.fill(-1);
    if (s.isCurrRacing()) return;

    std::array<std::vector<int>, 6> buckets;

    auto addBucket = [&](int t, int pid) {
        if (0 <= t && t < 6) buckets[t].push_back(pid);
    };

    std::vector<int> b{100,100,100,100,100,200};
    addBucket(weightedPick(b, rng), 6);            // 非卡理事長 (URA/aoharu 一定出現)

    if (s.isAoharu) {
        // 部活成員三階段特訓/爆発標記:
        //   每回合先擲出線率，出線後依狀態擲各自機率:
        //   - 集量條中 (gauge<5): 亮箭 0.4 → 訓練該欄 渦+1 (100%)
        //   - 量條滿 (gauge>=5 未爆): 魂爆標記 0.4 → 訓練該欄 魂爆発
        //   - 魂爆済: 極爆標記 0.25 + 仍可亮箭(成長)
        //   - 極爆済: 僅亮箭(成長)
        for (auto& v : s.aoharuSoulDict) v.clear();
        for (auto& v : s.aoharuSPDict) v.clear();
        s.aoharuMemberArrow.assign(s.aoharuMemberActive.size(), -1);
        for (size_t idx = 0; idx < s.aoharuMemberActive.size(); ++idx) {
            if (!s.aoharuMemberActive[idx]) continue;
            if (!randBool(rng, AOHARU_MEMBER_APPEAR_RATE)) continue;
            int col = aoharuClubBucketFor((int)idx, rng);
            if (col >= NUM_TRAININGS) continue;   // 出場欄無特訓/爆発標記
            // 出線=站上該訓練欄 (不一定亮箭)
            addBucket(col, 10 + (int)idx);
            if (s.turn <= 2) { s.aoharuMemberArrow[idx] = -1; continue; }
            s.aoharuMemberArrow[idx] = randBool(rng, AOHARU_MEMBER_ARROW_RATE) ? col : -1;
            int gauge = s.aoharuMemberGauge[idx];
            int burst = s.aoharuMemberBurst[idx];
            int polar = s.aoharuMemberPolar[idx];
            if (gauge >= AOHARU_GAUGE_MAX && !burst) {
                if (randBool(rng, AOHARU_SOUL_MARK_RATE)) s.aoharuSoulDict[col].push_back((int)idx);
            } else if (burst && !polar) {
                if (randBool(rng, AOHARU_SP_MARK_RATE)) s.aoharuSPDict[col].push_back((int)idx);
            }
        }
    } else if (s.turn >= 13 && !s.isXiahesu()) {
        addBucket(weightedPick(b, rng), 7);        // 記者 aoharu 無記者
    }

    std::array<int, NUM_TRAININGS> headN{0,0,0,0,0};
    for (int i = 0; i < NUM_TRAININGS; ++i) {
        size_t n = buckets[i].size();
        if (n == 1) {
            s.personDist[i][0] = buckets[i][0];
            headN[i] = 1;
        } else if (n > 1) {
            if (s.isAoharu) {
                // アオハル特訓は同一トレに複数名出現可能。部活成員一同保留 (卡/NPC 剩餘 slot 補位)
                int take = (int)std::min<size_t>(n, 5);
                for (int j = 0; j < take; ++j) { s.personDist[i][j] = buckets[i][j]; headN[i]++; }
            } else {
                s.personDist[i][0] = buckets[i][randrange(rng, (int)n)];
                headN[i] = 1;
            }
        }
        buckets[i].clear();
    }

    for (int i = 0; i < NUM_CARDS; ++i)
        addBucket(cardTrainProbs(s, i, rng), i);   // pid = 卡 index

    for (int i = 0; i < NUM_CARDS; ++i) {
        if (s.isAoharu && s.turn < 2) continue;    // アオハル turn1 無 NPC
        addBucket(weightedPick({100,100,100,100,100,100}, rng), 8);  // NPC
    }

    for (int i = 0; i < NUM_TRAININGS; ++i) {
        int maxHead = 5 - headN[i];
        std::vector<int> b2 = buckets[i];
        if ((int)b2.size() <= maxHead) {
            for (int pid : b2) { s.personDist[i][headN[i]] = pid; headN[i]++; }
        } else {
            std::vector<int> picked = sampleNoReplace(b2, maxHead, rng);
            for (int pid : picked) { s.personDist[i][headN[i]] = pid; headN[i]++; }
        }
    }

    for (int i = 0; i < NUM_CARDS; ++i)
        s.hintNow[i] = randBool(rng, 0.06 * (1 + 0.01 * s.deck[i].hintProb)) ? 1 : 0;

    calcTrainingValue(s);
}

// ===========================================================
// アオハル盃: 特訓/魂爆/極爆 (對齊 _aoharu_tokkun_try / _soulburst_try / _apply_tokkun)
// ===========================================================
struct AoharuTokku {
    // pair<src, idx>; src: 0=card 1=member
    std::vector<std::pair<int,int>> tok;
    std::vector<std::pair<int,int>> burst;
    std::vector<std::pair<int,int>> polar;
    int count() const { return (int)(tok.size() + burst.size() + polar.size()); }
};

static void aoharuClampMember(GameState& s, int idx) {
    // 未爆発上限 700, 爆発/極爆後 900 解放
    int cap = (s.aoharuMemberBurst[idx] || s.aoharuMemberPolar[idx]) ? 900 : 700;
    for (int i = 0; i < NUM_STATS; ++i)
        if (s.aoharuMemberStat[idx][i] > cap) s.aoharuMemberStat[idx][i] = cap;
}

static void aoharuTokkunTry(GameState& s, int src, int idx, int tra, std::mt19937& rng,
                            AoharuTokku& tokku) {
    if (s.turn <= 2) return;  // 開幕2ターンはアオハル特訓が発生しない
    if (src == 0) {           // card
        if (s.aoharuCardBurst[idx]) return;   // 卡無極爆
        if (!randBool(rng, AOHARU_TOKKUN_TRIGGER_RATE)) return;
        s.aoharuCardGauge[idx] += 1;
        if (s.aoharuCardGauge[idx] >= AOHARU_GAUGE_MAX) {
            s.aoharuCardBurst[idx] = 1;
            s.aoharuBurstCount += 1;
            tokku.burst.push_back({0, idx});
        } else {
            tokku.tok.push_back({0, idx});
        }
        return;
    }
    // member
    if (idx < 0 || idx >= (int)s.aoharuMemberActive.size()) return;
    if (!s.aoharuMemberActive[idx]) return;
    // 只有「站欄且該欄亮箭」的成員才特訓
    if (s.aoharuMemberArrow[idx] != tra) return;
    if (s.aoharuMemberBurst[idx]) {
        // 爆發済: 亮箭→特訓只成長能力，不再累渦
        int lvbb = s.getTrainingLevel(tra);
        const int* g = AOHARU_TOKKUN_MEMBER_GAIN[tra][std::max(0, std::min(4, lvbb - 1))];
        for (int i = 0; i < NUM_STATS; ++i)
            s.aoharuMemberStat[idx][i] += g[i];  // memberGainMult=1.0
        aoharuClampMember(s, idx);
        tokku.tok.push_back({1, idx});
        return;
    }
    // 集量條中: 亮箭→訓練該欄→渦+1 (100%)
    s.aoharuMemberGauge[idx] += 1;
    if (s.aoharuMemberGauge[idx] >= AOHARU_GAUGE_MAX)
        s.aoharuMemberGauge[idx] = AOHARU_GAUGE_MAX;
    int lv = s.getTrainingLevel(tra);
    const int* gain = AOHARU_TOKKUN_MEMBER_GAIN[tra][std::max(0, std::min(4, lv - 1))];
    for (int i = 0; i < NUM_STATS; ++i)
        s.aoharuMemberStat[idx][i] += gain[i];
    aoharuClampMember(s, idx);
    tokku.tok.push_back({1, idx});
}

static void aoharuSoulburstTry(GameState& s, int idx, int tra, bool polar, AoharuTokku& tokku) {
    if (s.turn <= 2) return;
    if (idx < 0 || idx >= (int)s.aoharuMemberActive.size()) return;
    if (!s.aoharuMemberActive[idx]) return;
    if (polar) {
        if (s.aoharuMemberBurst[idx] != 1 || s.aoharuMemberPolar[idx]) return;
        s.aoharuMemberPolar[idx] = 1;
        s.aoharuBurstCount += 1;
    } else {
        if (s.aoharuMemberBurst[idx]) return;
        if (s.aoharuMemberGauge[idx] < AOHARU_GAUGE_MAX) return;
        s.aoharuMemberBurst[idx] = 1;
        s.aoharuBurstCount += 1;
    }
    const int* g = AOHARU_BURST_MEMBER_GAIN[aoharuMemberType(idx)];
    for (int i = 0; i < NUM_STATS; ++i)
        s.aoharuMemberStat[idx][i] += g[i];
    aoharuClampMember(s, idx);
    (polar ? tokku.polar : tokku.burst).push_back({1, idx});
}

static std::array<int, 6> aoharuTokkunRow(const GameState& s, int tra, int count) {
    int rowIdx = std::max(0, std::min(5, count) - 1);
    std::array<int, 6> row;
    for (int i = 0; i < 6; ++i) row[i] = AOHARU_TOKKUN_BYCOUNT[tra][rowIdx][i];
    bool any = false;
    for (int v : row) if (v) { any = true; break; }
    if (count == 1 && !any) {
        // 單箭通常無加成; 高基礎欄(主屬基礎≥12)偶爾 +1
        int lv = s.getTrainingLevel(tra);
        int basic = AOHARU_TRAINING_BASIC_VALUE[tra][std::max(0, std::min(4, lv - 1))][tra];
        if (basic >= 12) row[tra] = 1;
    }
    return row;
}

static void aoharuAddRow(GameState& s, const std::array<int, 6>& row) {
    for (int i = 0; i < NUM_STATS; ++i)
        if (row[i]) addStatus(s, i, (double)row[i]);
    if (row[5]) s.skillPt += row[5];
}

static void aoharuApplyTokkun(GameState& s, int tra, AoharuTokku& tokku, std::mt19937& rng) {
    int count = tokku.count();
    if (count == 0) return;
    // 依特訓人数 select row (cap 5)
    std::array<int, 6> row = aoharuTokkunRow(s, tra, count);
    // link(編成卡) 特訓時 對非零欄 +1
    int link = 0;
    for (auto& tk : tokku.tok) if (tk.first == 0) link++;
    for (int i = 0; i < 6; ++i)
        if (row[i]) row[i] += link;
    aoharuAddRow(s, row);
    for (auto& tk : tokku.tok)
        if (randBool(rng, AOHARU_TOKKUN_HINT_RATE))
            s.skillPt += AOHARU_TOKKUN_HINT_PT;
    for (auto& b : tokku.burst) {
        const int* bRow = (b.first == 0) ? AOHARU_BURST_BONUS_LINK[tra] : AOHARU_BURST_BONUS[tra];
        std::array<int, 6> row2;
        for (int i = 0; i < 6; ++i) row2[i] = bRow[i];
        aoharuAddRow(s, row2);
        s.skillPt += AOHARU_BURST_HINT_PT;
    }
    for (auto& p : tokku.polar) {
        std::array<int, 6> row2;
        for (int i = 0; i < 6; ++i) row2[i] = AOHARU_BURST_BONUS[tra][i];
        aoharuAddRow(s, row2);
        s.skillPt += AOHARU_BURST_HINT_PT;
    }
    int bn = (int)(tokku.burst.size() + tokku.polar.size());
    if (bn && tra == TrainWit)
        s.stamina = std::min(s.maxVital, s.stamina + 5 * bn);  // 賢さ魂爆/極爆 回復+5/人
}

// ===========================================================
// 行動解算 (對齊 _apply_training)
// ===========================================================
static bool applyTraining(GameState& s, int a, std::mt19937& rng) {
    if (s.isCurrRacing()) return true;   // 固定比賽收益在 events 處理
    if (a == Rest) {
        if (s.isXiahesu()) return false;  // 合宿不能休息
        int r = randrange(rng, 100);
        if (r < 25) addVital(s, 70);
        else if (r < 75) addVital(s, 50);
        else addVital(s, 30);
        return true;
    }
    if (a == Race) {
        if (s.turn <= 13 || s.turn >= 73) return false;
        // 自由參賽獎勵 = 單屬性 +8~10 (隨機欄) + SP45，
        //  皆乘「競賽加成」(加算, 例 +10%/+5%/+5% = ×1.2)，小數點捨去。
        double m = 1 + 0.01 * s.saiHou;
        int col = randrange(rng, NUM_TRAININGS);
        int gain = (int)(m * (8 + randrange(rng, 3)));
        addStatus(s, col, (double)gain);
        s.skillPt += (int)(m * 45);
        addVital(s, -15);
        if (randrange(rng, 10) == 0) addMotivation(s, 1);
        return true;
    }
    if (a == Outing) {
        if (s.isXiahesu()) {
            addVital(s, 40);
            addMotivation(s, 1);
        } else {
            if (randrange(rng, 2)) addMotivation(s, 2);
            else { addMotivation(s, 1); addVital(s, 10); }
        }
        return true;
    }
    if (!(0 <= a && a <= 4)) return false;

    int fail = s.failRate[a];
    if (s.isAoharu && !s.aoharuSPDict[a].empty())
        fail = 0;  // 極・アオハル魂爆発トレは失敗率必 0%
    if (randrange(rng, 100) < fail) {
        if (a == TrainWit) {
            addVital(s, s.trainVitalChange[a]);
            return true;
        }
        if (randrange(rng, 100) < fail) {   // 大失敗
            addStatus(s, a, -10);
            if (s.stats[a] > 1200) addStatus(s, a, -10);
            std::vector<int> others{0,1,2,3,4};
            shuffleList(others, rng);
            for (int k = 0; k < 2 && k < (int)others.size(); ++k) {
                addStatus(s, others[k], -10);
                if (s.stats[others[k]] > 1200) addStatus(s, others[k], -10);
            }
            addMotivation(s, -2);
            if (!s.isAoharu) addVital(s, 10);  // アオハル"失敗不回體"
        } else {                             // 小失敗
            addStatus(s, a, -5);
            if (s.stats[a] > 1200) addStatus(s, a, -5);
            addMotivation(s, -1);
        }
        return true;
    }

    // 成功
    for (int i = 0; i < NUM_STATS; ++i)
        addStatus(s, i, s.trainValue[a][i] * s.statWeights[i], false);
    s.skillPt += s.trainValue[a][5];
    addVital(s, s.trainVitalChange[a]);

    AoharuTokku tokku;
    std::vector<int> hintCards;
    for (int h = 0; h < NUM_TRAININGS; ++h) {
        int pid = s.personDist[a][h];
        if (pid < 0) break;
        if (pid < NUM_CARDS) {
            addJiBan(s, pid, 7);
            s.trainClicked[pid]++;
            if (s.hintNow[pid]) hintCards.push_back(pid);
            if (s.isAoharu) aoharuTokkunTry(s, 0, pid, a, rng, tokku);
        } else if (pid == 6) {
            int j = s.friendshipNoncardYayoi;
            int g = j < 40 ? 2 : j < 60 ? 3 : j < 80 ? 4 : 5;
            s.skillPt += g;
            addJiBan(s, 6, 7);
        } else if (pid == 7) {
            int j = s.friendshipNoncardReporter;
            int g = j < 40 ? 2 : j < 60 ? 3 : j < 80 ? 4 : 5;
            addStatus(s, a, g);
            addJiBan(s, 7, 7);
        } else if (s.isAoharu && pid >= 10) {
            int idx = pid - 10;
            if (idx >= 0 && idx < (int)s.aoharuMemberActive.size() &&
                s.aoharuMemberActive[idx] && s.aoharuMemberArrow[idx] == a) {
                if (!aoharuMemberNpc(idx)) {
                    s.aoharuMemberBond[idx] = std::min(100, s.aoharuMemberBond[idx] + 7);
                }
                aoharuTokkunTry(s, 1, idx, a, rng, tokku);
            }
        } else if (pid == 8) {
        }
    }

    if (s.isAoharu) {
        // 點選魂爆/極爆標記所在欄 → 觸發爆発
        for (int idx : s.aoharuSoulDict[a]) aoharuSoulburstTry(s, idx, a, false, tokku);
        for (int idx : s.aoharuSPDict[a]) aoharuSoulburstTry(s, idx, a, true, tokku);
        aoharuApplyTokkun(s, a, tokku, rng);
    }

    if (!hintCards.empty()) {
        int pick = hintCards[randrange(rng, (int)hintCards.size())];
        addJiBan(s, pick, 5);
        int lv = s.deck[pick].hintLevel;
        if (lv > 0) {
            s.skillPt += lv * HINT_PT_RATE;
        } else {
            if (a == 0) { addStatus(s,0,6); addStatus(s,2,2); }
            else if (a == 1) { addStatus(s,1,6); addStatus(s,3,2); }
            else if (a == 2) { addStatus(s,2,6); addStatus(s,1,2); }
            else if (a == 3) { addStatus(s,3,6); addStatus(s,0,1); addStatus(s,2,1); }
            else if (a == 4) { addStatus(s,4,6); s.skillPt += 5; }
        }
    }

    addTrainingLevelCount(s, a, 1);
    return true;
}

// ===========================================================
// 固定/隨機事件 (對齊 _check_fixed_events / _check_random_events, URA)
// ===========================================================
static void runRace(GameState& s, int basicFiveStatusBonus, int basicPtBonus) {
    double m = 1 + 0.01 * s.saiHou;
    int fb = (int)(m * basicFiveStatusBonus);
    int pb = (int)(m * basicPtBonus);
    addAllStatus(s, fb);
    s.skillPt += pb;
}

static void inheritance(GameState& s, std::mt19937& rng) {
    for (int i = 0; i < NUM_STATS; ++i)
        addStatus(s, i, s.zhongMaBlueCount[i] * 6);
    double factor = (randrange(rng, 65536) / 65536.0) * 2;
    for (int i = 0; i < NUM_STATS; ++i)
        addStatus(s, i, int(factor * s.zhongMaExtraBonus[i]));
    s.skillPt += (int)((0.5 + 0.5 * factor) * s.zhongMaExtraBonus[5]);
    for (int i = 0; i < NUM_STATS; ++i)
        s.fiveStatusLimit[i] += s.zhongMaBlueCount[i] * 2;
    for (int i = 0; i < NUM_STATS; ++i)
        s.fiveStatusLimit[i] += randrange(rng, 8);
}

static bool inRaceTurns(const GameState& s) { return s.isCurrRacing(); }

// ===========================================================
// アオハル盃: チームレース / 部活補充 / 爆発スキル結算
// ===========================================================
static void aoharuJoinMembers(GameState& s, int n) {
    // 依順序啟用未活動者
    for (size_t idx = 0; idx < s.aoharuMemberActive.size() && n > 0; ++idx) {
        if (!s.aoharuMemberActive[idx]) {
            s.aoharuMemberActive[idx] = 1;
            s.aoharuMemberStat[idx] = aoharuMemberBaseStat((int)idx);
            s.aoharuMemberBond[idx] = 0;
            s.aoharuMemberGauge[idx] = 0;
            s.aoharuMemberBurst[idx] = 0;
            s.aoharuMemberPolar[idx] = 0;
            n--;
        }
    }
}

static void aoharuPreP1Recruit(GameState& s) {
    // 季前賽第1戰前: link 四名 + 攜帶支援卡角色(友人卡 cardType==5 除外)
    aoharuJoinMembers(s, AOHARU_LINK_COUNT);
    int sup = 0;
    for (int i = 0; i < NUM_CARDS; ++i)
        if (s.deck[i].cardType != 5) sup++;
    aoharuJoinMembers(s, std::min(sup, AOHARU_SUPPORT_MEMBER_COUNT));
    int cur = s.aoharuMemberCount();
    if (cur < AOHARU_FILL_TO_BEFORE_P1 && cur < AOHARU_MAX_MEMBERS)
        aoharuJoinMembers(s, std::min(AOHARU_FILL_TO_BEFORE_P1 - cur, AOHARU_MAX_MEMBERS - cur));
}

static void aoharuPostRaceRecruit(GameState& s) {
    int cur = s.aoharuMemberCount();
    if (cur >= AOHARU_MAX_MEMBERS) return;
    aoharuJoinMembers(s, std::min(AOHARU_POST_RACE_RECRUIT_MAX, AOHARU_MAX_MEMBERS - cur));
}

static void aoharuBurstSkill(GameState& s) {
    // シニア11月前半結束，依魂爆発回數結算スキル (approx)
    int n = s.aoharuBurstCount;
    if (n >= 13)      { s.skillScore += 510; s.skillPt += 20; }
    else if (n >= 10) { s.skillScore += 170; s.skillPt += 20; }
    else if (n >= 7)  { s.skillScore += 85;  s.skillPt += 15; }
    else if (n >= 4)  { s.skillPt += 15; }
}

static void aoharuTeamRace(GameState& s, std::mt19937& rng) {
    int idx = -1;
    for (int i = 0; i < 5; ++i) if (s.turn == AOHARU_TEAM_RACE_TURNS[i]) { idx = i; break; }
    if (idx < 0) return;
    const AoharuOpponent& opp = AOHARU_OPPONENT[idx];
    int n = s.aoharuMemberCount();
    double teamTotal = 0;
    for (size_t mi = 0; mi < s.aoharuMemberActive.size(); ++mi)
        if (s.aoharuMemberActive[mi])
            for (int i = 0; i < NUM_STATS; ++i) teamTotal += s.aoharuMemberStat[mi][i];
    double memberAvg = teamTotal / std::max(1, n) / 5.0;
    int myTier = aoharuAvgTier(memberAvg);
    int oppTier = aoharuAvgTier(opp.avg);
    double winProb = std::max(0.15, std::min(0.97, 0.55 + 0.10 * (myTier - oppTier)));
    bool won = randBool(rng, winProb);
    int grow, sp, memberGain;
    if (won) {
        s.aoharuTeamRank = std::max(1, std::min(30, s.aoharuTeamRank + opp.winBoost));
        grow = opp.winStat; sp = opp.winSp; memberGain = 50;
    } else {
        s.aoharuTeamRank = std::min(30, s.aoharuTeamRank + 2);  // lossRankBoost
        grow = opp.loseStat; sp = opp.loseSp; memberGain = 10;
    }
    int bonus = aoharuTeamRankBonus(s.aoharuTeamRank);
    addAllStatus(s, (double)(grow + (won ? bonus : 0)));
    s.skillPt += sp;
    for (size_t mi = 0; mi < s.aoharuMemberActive.size(); ++mi) {
        if (!s.aoharuMemberActive[mi]) continue;
        for (int i = 0; i < NUM_STATS; ++i) s.aoharuMemberStat[mi][i] += memberGain;
        aoharuClampMember(s, (int)mi);
    }
    if (s.turn == AOHARU_TEAM_RACE_TURNS[4] && won) addMotivation(s, 1);  // 決勝優勝
}

static void checkFixedEvents(GameState& s, std::mt19937& rng) {
    if (s.isRefreshMind) {
        addVital(s, 5);
        if (randrange(rng, 4) == 0) s.isRefreshMind = false;
    }

    if (s.isAoharu && isAoharuTeamRaceTurn(s)) {
        aoharuTeamRace(s, rng);   // チームレース取代該週一般出賽收益
    } else if (s.isCurrRacing()) {
        if (s.turn < 73) { runRace(s, 3, 45); addJiBan(s, 6, 4); }
        else if (s.turn == 74) runRace(s, 10, 40);
        else if (s.turn == 76) runRace(s, 10, 60);
        else if (s.turn == 78) runRace(s, 10, 80);
    }

    if (s.isAoharu) {
        // 補充只在季前賽前/季前賽(24/36/48/60)結束後；決勝(72)後不再補
        if (s.turn == AOHARU_PRE_RACE_RECRUIT_TURN) {
            aoharuPreP1Recruit(s);
        } else if (isAoharuTeamRaceTurn(s) && s.turn != AOHARU_TEAM_RACE_TURNS[4]) {
            aoharuPostRaceRecruit(s);
        }
        if (s.turn == 70) s.skillPt += 15;  // アオハルスキル +15SP
    }

    if (s.turn == 12) {
    } else if (s.turn == 24) {
        if (s.maxVital - s.stamina >= 20) addVital(s, 20);
        else addAllStatus(s, 5);
    } else if (s.turn == 30) {
        inheritance(s, rng);
    } else if (s.turn == 36) {
    } else if (s.turn == 48) {
        if (s.maxVital - s.stamina >= 30) addVital(s, 30);
        else addAllStatus(s, 8);
    } else if (s.turn == 49) {
        int rd = randrange(rng, 100);
        if (rd < 16) { addVital(s, 30); addAllStatus(s, 10); addMotivation(s, 2); }
        else if (rd < 43) { addVital(s, 20); addAllStatus(s, 5); addMotivation(s, 1); }
        else if (rd < 89) { addVital(s, 20); }
        else { addMotivation(s, -1); }
    } else if (s.turn == 50) {
        s.skillScore += 170;
    } else if (s.turn == 54) {
        inheritance(s, rng);
        if (s.friendshipNoncardYayoi >= 60) {
            s.skillScore += 170;
            addMotivation(s, 1);
        } else {
            addVital(s, -5);
            s.skillPt += 25;
        }
    } else if (s.turn == 60) {
    } else if (s.turn == 69 && s.isAoharu) {
        aoharuBurstSkill(s);
    } else if (s.turn == 71) {
        s.skillScore += 170;
    } else if (s.turn == 78) {
        int rep = s.friendshipNoncardReporter;
        if (rep >= 80) { addAllStatus(s, 5); s.skillPt += 20; }
        else if (rep >= 60) { addAllStatus(s, 3); s.skillPt += 10; }
        else if (rep >= 40) { s.skillPt += 10; }
        else { s.skillPt += 5; }
        addAllStatus(s, 40);
        addAllStatus(s, 5);
        s.skillPt += 20;
    }
}

// ===========================================================
// 行動解算 (對齊 applyAction)
// ===========================================================
GameState applyAction(const GameState& s, int a, std::mt19937& rng) {
    GameState next = s;   // clone
    if (next.isTerminal()) return next;
    if (!next.isCurrRacing()) {
        bool ok = applyTraining(next, a, rng);
        if (!ok) return next;   // 對應 Python raise；實務不會發生
    }
    checkFixedEvents(next, rng);
    next.turn += 1;
    if (next.isTerminal()) return next;
    cardRandom(next, rng);
    return next;
}

// ===========================================================
// 合法行動 (對齊 legalActions)
// ===========================================================
std::vector<int> legalActions(const GameState& s) {
    std::vector<int> out;
    if (s.isCurrRacing()) {
        out.push_back(Race);
        return out;
    }
    if (s.isAoharu) {
        // アオハル盃每回合 5 個訓練欄皆可點選
        for (int t = 0; t < NUM_TRAININGS; ++t) out.push_back(t);
    } else {
        // URA: 至少一欄有卡才限欄，否則全欄可點
        bool hasCard[NUM_TRAININGS];
        bool any = false;
        for (int t = 0; t < NUM_TRAININGS; ++t) {
            hasCard[t] = false;
            for (int h = 0; h < NUM_TRAININGS; ++h) {
                int pid = s.personDist[t][h];
                if (0 <= pid && pid < NUM_CARDS) { hasCard[t] = true; break; }
            }
            if (hasCard[t]) any = true;
        }
        if (any)
            for (int t = 0; t < NUM_TRAININGS; ++t) if (hasCard[t]) out.push_back(t);
        else
            for (int t = 0; t < NUM_TRAININGS; ++t) out.push_back(t);
    }
    if (!s.isXiahesu()) out.push_back(Rest);
    out.push_back(Outing);
    if (s.isRaceAvailable()) out.push_back(Race);
    return out;
}

// ===========================================================
// 手寫策略 (對齊 _status_soft / _status_gain_evaluation / ...)
// ===========================================================
static double statusSoft(double x, double reserve, double reserveInvX2) {
    if (x >= 0) return 0;
    if (x > -reserve) return -x * x * reserveInvX2;
    return x + 0.5 * reserve;
}

static std::array<double, NUM_STATS> statusGainEvaluation(const GameState& s) {
    std::array<double, NUM_STATS> result{0,0,0,0,0};
    int remainTurn = TOTAL_TURN - s.turn;
    double reserve = 40.0 * remainTurn * (1 - remainTurn / (double)(TOTAL_TURN * 2));
    double reserveInvX2 = 1 / (2 * reserve + 1e-12);
    double finalBonus0 = 75.0;
    if (remainTurn >= 1) finalBonus0 += 20;
    if (remainTurn >= 2) finalBonus0 += 20;
    double remain[NUM_STATS];
    double remainLim[NUM_STATS];
    for (int i = 0; i < NUM_STATS; ++i) {
        remainLim[i] = s.fiveStatusLimit[i] - s.stats[i] - finalBonus0;
        double lim = s.fiveStatusLimit[i];
        if (s.statTargets[i] > 0) lim = std::min(lim, s.statTargets[i]);
        remain[i] = lim - s.stats[i] - finalBonus0;
    }
    for (int tra = 0; tra < NUM_TRAININGS; ++tra) {
        double res = 0.0;
        for (int sta = 0; sta < NUM_STATS; ++sta) {
            double w = s.statWeights[sta];
            // 已超過目標: 主屬性收益壓低但不歸零 (保留副訓練/技能點/羈絆的價值)
            bool goalOver = (s.statTargets[sta] > 0 && remain[sta] < 0);
            if (goalOver) {
                double full = 6.0 * (statusSoft(s.trainValue[tra][sta] - remainLim[sta],
                                                reserve, reserveInvX2)
                                   - statusSoft(-remainLim[sta], reserve, reserveInvX2));
                res += w * std::max(0.0, OVER_GOAL_FLOOR * full);
            } else {
                double s0 = statusSoft(-remain[sta], reserve, reserveInvX2);
                double s1 = statusSoft(s.trainValue[tra][sta] - remain[sta],
                                       reserve, reserveInvX2);
                res += w * 6.0 * (s1 - s0);
            }
        }
        res += PT_SCORE_RATE * s.trainValue[tra][5];
        result[tra] = res;
    }
    return result;
}

static double vitalEvaluation(int vital, int maxVital) {
    if (vital <= 50) return 2.0 * vital;
    if (vital <= 70) return 1.5 * (vital - 50) + vitalEvaluation(50, maxVital);
    if (vital <= maxVital) return 1.0 * (vital - 70) + vitalEvaluation(70, maxVital);
    return vitalEvaluation(maxVital, maxVital);
}

static int calcMaxVitalEq(const GameState& s) {
    int t = s.turn;
    if (t >= 77) return 0;
    if (t > 72) return 10;
    if (t == 72) return 30;
    int nonRace = 0;
    for (int i = 72; i > t; --i) {
        bool race = false;
        for (int r : s.raceTurns) if (r == i) { race = true; break; }
        if (!race) nonRace++;
        if (nonRace >= 6) break;
    }
    int eq = 30 + 15 * nonRace;
    if (eq > s.maxVital) eq = s.maxVital;
    return eq;
}

std::array<double, COUNT> actionValues(const GameState& s) {
    std::array<double, COUNT> values{};
    values.fill(-1e9);   // Python 以 dict 缺席表示「無此行動」，C++ 用哨兵對齊 .get(a,-1e9)

    double vitalFactor = 3.5 + (s.turn / (double)TOTAL_TURN) * (7.0 - 3.5);
    int maxVitalEq = calcMaxVitalEq(s);
    double vitalBefore = vitalEvaluation(std::min(maxVitalEq, s.stamina), s.maxVital);

    int act, vitalGain;
    if (s.isXiahesu()) { act = Outing; vitalGain = 40; }
    else { act = Rest; vitalGain = 50; }
    // 回復計分上限 = 安全訓練線 (70), 不是滿體: 體力 ≥70 時休息幾乎無效。
    int vitSafe = std::min(maxVitalEq, 70);
    int afterRest = std::min(vitSafe, vitalGain + s.stamina);
    double value = 0.0;
    if (afterRest > s.stamina)
        value = vitalFactor * (vitalEvaluation(afterRest, s.maxVital) - vitalBefore);
    if (s.mood < 5 && act == Outing && afterRest > s.stamina) value += 200;
    values[act] = value;

    if (s.isRaceAvailable()) {
        int afterRace = std::min(maxVitalEq, -15 + s.stamina);
        // アオハル盃は練習(特訓)優先，額外比賽價值遠低 (會吃掉一週特訓機會)
        double raceFlat = s.isAoharu ? 40.0 : 150.0;
        values[Race] = raceFlat + vitalFactor * (vitalEvaluation(afterRace, s.maxVital) - vitalBefore);
    }

    std::array<double, NUM_STATS> statusE = statusGainEvaluation(s);
    bool carded[NUM_TRAININGS];
    bool anyCard = false;
    for (int t = 0; t < NUM_TRAININGS; ++t) {
        carded[t] = false;
        for (int h = 0; h < NUM_TRAININGS; ++h) {
            int pid = s.personDist[t][h];
            if (0 <= pid && pid < NUM_CARDS) { carded[t] = true; break; }
        }
        if (carded[t]) anyCard = true;
    }
    if (!anyCard)
        for (int t = 0; t < NUM_TRAININGS; ++t) carded[t] = true;

    for (int tra = 0; tra < NUM_TRAININGS; ++tra) {
        if (!carded[tra]) continue;
        value = statusE[tra];
        std::vector<int> hintIds;
        for (int h = 0; h < NUM_TRAININGS; ++h) {
            int pid = s.personDist[tra][h];
            if (pid < 0) break;
            if (0 <= pid && pid < NUM_CARDS && s.hintNow[pid]) hintIds.push_back(pid);
        }
        double hintProb = hintIds.empty() ? 0.0 : 1.0 / hintIds.size();
        for (int h = 0; h < NUM_TRAININGS; ++h) {
            int pid = s.personDist[tra][h];
            if (pid < 0) break;
            if (pid < NUM_CARDS) {
                const SupportCard& c = s.deck[pid];
                if (c.cardType >= 0 && c.cardType <= 4 && s.cardBond[pid] < 80) {
                    int jAdd = std::min(80 - s.cardBond[pid], 7);
                    value += jAdd * 12;
                }
            }
        }
        for (int pid : hintIds) {
            int lv = s.deck[pid].hintLevel;
            double hb = (lv == 0) ? 1.6 * 30 : HINT_PT_RATE * PT_SCORE_RATE * lv;
            value += hb * hintProb;
        }
        int afterTrain = std::min(maxVitalEq, s.trainVitalChange[tra] + s.stamina);
        // 體力扣罰依失敗率縮放: 低失敗率 (<~20%) 的好訓練即使體力低也該點。
        double pen = 0.5 + s.failRate[tra] / 100.0;
        value += 1.0 * vitalFactor * pen * (vitalEvaluation(afterTrain, s.maxVital) - vitalBefore);

        // 高體力機會成本: 體力高時優先消耗 (智自回體無此優勢)，避免扣體訓練長局被低估
        int vitalCost = -s.trainVitalChange[tra];
        if (s.stamina >= 70 && vitalCost > 0) {
            value += 5.0 * vitalCost * std::max(0.0, std::min(1.0, (s.stamina - 60) / 40.0));
        }

        // アオハル特訓價值: 這欄有幾名部活成員 → 囤渦/快爆發的期望
        if (s.isAoharu) {
            double memberValue = 0.0;
            int nPart = 0;
            for (int h = 0; h < NUM_TRAININGS; ++h) {
                int p = s.personDist[tra][h];
                if (p < 0 || p < 10) continue;
                int idx = p - 10;
                if (idx < 0 || idx >= (int)s.aoharuMemberActive.size()) continue;
                if (!s.aoharuMemberActive[idx]) continue;
                if (s.aoharuMemberArrow[idx] != tra) continue;
                int g = s.aoharuMemberGauge[idx];
                if (s.aoharuMemberBurst[idx]) {
                    memberValue += 8.0;   // 已爆發: 剩極爆機會 + 成員續成長
                    nPart += 1;
                } else {
                    int eff = std::min(g + 1, AOHARU_GAUGE_MAX);
                    double nearBurst = (eff == AOHARU_GAUGE_MAX) ? 70.0 : 0.0;
                    memberValue += eff * 5.0 + nearBurst;
                    nPart += 1;
                }
            }
            // 魂爆/極爆標記: 拉力依該欄參與人數縮放 (站欄者 + 標記者去重)
            std::set<int> part;
            for (int h = 0; h < NUM_TRAININGS; ++h) {
                int p = s.personDist[tra][h];
                if (p < 10) continue;
                int idx = p - 10;
                if (idx >= 0 && idx < (int)s.aoharuMemberActive.size() && s.aoharuMemberActive[idx])
                    part.insert(idx);
            }
            for (int idx : s.aoharuSoulDict[tra]) part.insert(idx);
            for (int idx : s.aoharuSPDict[tra]) part.insert(idx);
            int markN = (int)part.size();
            double scale = markN >= 3 ? 1.0 : markN == 2 ? 0.55 : 0.18;  // 單爆近無吸引力
            if (!s.aoharuSoulDict[tra].empty()) memberValue += 115.0 * scale;
            if (!s.aoharuSPDict[tra].empty()) memberValue += 145.0 * scale;
            value += memberValue;
        }

        int failRate = s.failRate[tra];
        if (failRate > 0) {
            int bigFailProb = (failRate >= 20) ? failRate : 0;
            double failValueAvg = 0.01 * bigFailProb * (-500) + (1 - 0.01 * bigFailProb) * (-150);
            value = 0.01 * failRate * failValueAvg + (1 - 0.01 * failRate) * value;
        }

        // 面板祝福: 真實主屬性成長 ≥2x 該訓練基礎值 (遊戲給的大面板), 0%失敗時加權
        {
            int level = s.getTrainingLevel(tra);
            int rowIdx = s.isAoharu ? std::max(0, level - 1) : level;
            int mainBase = s.isAoharu ? AOHARU_TRAINING_BASIC_VALUE[tra][rowIdx][tra]
                                      : TRAINING_BASIC_VALUE[tra][rowIdx][tra];
            if (mainBase > 0) {
                double mult = s.trainValue[tra][tra] / (double)mainBase;
                if (mult >= 2.0 && s.failRate[tra] == 0)
                    value += 60.0 * std::min(mult - 1.5, 1.5);
            }
        }
        values[tra] = value;
    }
    return values;
}

int rolloutPolicy(const GameState& s, std::mt19937& rng) {
    (void)rng;
    if (s.isCurrRacing()) return Race;
    double bestValue = -1e4;
    int bestAction = Rest;
    std::array<double, COUNT> v = actionValues(s);
    for (int a = 0; a < COUNT; ++a) {
        if (v[a] > bestValue) { bestValue = v[a]; bestAction = a; }
    }
    return bestAction;
}

GameState rolloutToEnd(GameState s, std::mt19937& rng) {
    while (!s.isTerminal()) {
        int a = rolloutPolicy(s, rng);
        s = applyAction(s, a, rng);
    }
    return s;
}

// ===========================================================
// 計分 (對齊 finalScoreRank)
// ===========================================================
double _getSkillScore(const GameState& s) {
    return PT_SCORE_RATE * s.skillPt + s.skillScore;
}

double finalScoreRank(const GameState& s) {
    double total = 0;
    for (int i = 0; i < NUM_STATS; ++i) {
        int idx = (int)s.stats[i];
        int lim = (int)s.fiveStatusLimit[i];
        if (idx > lim) idx = lim;
        double sc;
        if (idx >= 0 && idx < (int)(sizeof(FIVE_STATUS_FINAL_SCORE)/sizeof(int)))
            sc = FIVE_STATUS_FINAL_SCORE[idx];
        else
            sc = FIVE_STATUS_FINAL_SCORE[(sizeof(FIVE_STATUS_FINAL_SCORE)/sizeof(int)) - 1];
        total += s.stratWeight[i] * sc;
    }
    total += s.stratSkill * (double)(int)_getSkillScore(s);
    return total;
}