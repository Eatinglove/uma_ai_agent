#pragma once

#include <array>
#include <cmath>
#include <random>
#include <string>
#include <vector>

// ===========================================================
// URA 引擎 (對齊 python_app/simulator.py 現行規則)
// ===========================================================
enum Action {
    TrainSpeed = 0, TrainStamina, TrainPower, TrainGuts, TrainWit,
    Rest, Outing, Race, COUNT
};
constexpr int NUM_TRAININGS = 5;
constexpr int NUM_STATS = 5;
constexpr int NUM_CARDS = 6;
constexpr int TOTAL_TURN = 78;   // URA 共 78 週 (1-based)，終局 turn>78
constexpr int AOHARU_MAX_MEMBERS = 19;  // 部活成員上限 (含初始 6 相棒 + 4 NPC + 9 招募)

// 屬性/行動名稱 (供除錯輸出)
const char* actionName(int a);
const char* moodName(int mood);

int aoharuAvgTier(double avg);   // 團隊均值→訓練等級 1..5 (scenarios.py rankToLevel)

// ===========================================================
// 支援卡 (與 carddata.py SupportCard 數值欄位對齊)
// ===========================================================
struct SupportCard {
    int type = 4;            // enum: 0速 1耐 2力 3根 4智 (carddata _TYPE_TO_ENUM)
    int cardType = 4;        // 0..6 (cardDB cardType 原值: 5友 6團)
    std::array<int, NUM_STATS> cardBonus{0,0,0,0,0};
    int skillPtBonus = 0;
    std::array<int, NUM_STATS> initStats{0,0,0,0,0};
    int initSkillPt = 0;
    int initialBond = 0;
    double friendPct = 0;    // 友情%
    double moodPct = 0;      // 幹勁%
    double trainPct = 0;     // 訓練%
    double specialtyRate = 0;// 得意率%
    double saiHou = 0;       // 賽後%
    double hintProb = 0;     // 啟發出現率%
    double failRateDrop = 0; // 成功率下降%
    double vitalCostDrop = 0;// 體力消費下降%
    int wizVitalBonus = 0;   // 智彩圈回體
    int hintLevel = 0;       // 技能啟發等級
    int uniqueEffectType = 0;
    std::vector<double> uniqueEffectParam;
};

// ===========================================================
// 遊戲狀態
// ===========================================================
struct GameState {
    int turn = 1;
    int stamina = 100;
    int mood = 3;

    std::array<double, NUM_STATS> stats{0,0,0,0,0};
    std::array<int, NUM_TRAININGS> trainCount{0,0,0,0,0};

    std::array<int, NUM_CARDS> cardBond{0,0,0,0,0,0};
    std::array<int, NUM_CARDS> cardBond80Turn{0,0,0,0,0,0};

    int fans = 0;
    double skillPt = 0;
    int shiningCount = 0;
    bool initialized = true;   // load 時 bridge 已初始化

    int umaStars = 3;
    std::array<int, NUM_STATS> fiveStatusBonus{0,0,0,0,0};
    std::array<int, NUM_STATS> fiveStatusLimit{1400,1400,1400,1400,1400};
    int skillScore = 0;
    int maxVital = 100;

    int failureRateBias = 0;
    bool isPositiveThinking = false;
    bool isRefreshMind = false;
    int friendshipNoncardYayoi = 0;      // 非卡理事長羈絆
    int friendshipNoncardReporter = 0;   // 記者羈絆
    double saiHou = 0.0;

    std::array<int, NUM_STATS> zhongMaBlueCount{4,4,4,3,3};
    std::array<int, 6> zhongMaExtraBonus{30,0,30,0,0,150};

    std::vector<int> raceTurns;   // 1-based 生涯出賽週
    std::array<int, NUM_CARDS> hintNow{0,0,0,0,0,0};
    std::array<std::array<int, NUM_TRAININGS>, NUM_TRAININGS> personDist{};
    std::array<int, NUM_TRAININGS> isTrainShining{0,0,0,0,0};
    std::array<std::array<double, 6>, NUM_TRAININGS> trainValue{};  // [tra][0..5] (i==5 為 pt)
    std::array<int, NUM_TRAININGS> trainVitalChange{0,0,0,0,0};
    std::array<int, NUM_TRAININGS> failRate{0,0,0,0,0};
    std::array<int, NUM_CARDS> trainClicked{0,0,0,0,0,0};

    // ---- アオハル盃 (aoharu) ----
    bool isAoharu = false;
    int aoharuTeamRank = 30;
    int aoharuBurstCount = 0;
    std::vector<int> aoharuMemberActive;                 // 0/1
    std::vector<int> aoharuMemberBond;                   // 羈絆 (0..100)
    std::vector<int> aoharuMemberGauge;                  // 渦量條 (0..5)
    std::vector<int> aoharuMemberBurst;                  // 魂爆済 0/1
    std::vector<int> aoharuMemberPolar;                  // 極爆済 0/1
    std::vector<std::array<int, NUM_STATS>> aoharuMemberStat;   // 成員五圍
    std::vector<int> aoharuMemberArrow;                  // 白箭頭欄 (-1=無)
    std::array<int, NUM_CARDS> aoharuCardGauge{0,0,0,0,0,0};
    std::array<int, NUM_CARDS> aoharuCardBurst{0,0,0,0,0,0};
    std::array<std::vector<int>, NUM_TRAININGS> aoharuSoulDict;  // 魂爆標記 [欄]
    std::array<std::vector<int>, NUM_TRAININGS> aoharuSPDict;    // 極爆標記 [欄]

    // 無 aoharu 資料時 (URA / 舊 dump) 懶初始化成人數上限的空資料
    void aoharuEnsure() {
        if ((int)aoharuMemberActive.size() < AOHARU_MAX_MEMBERS) {
            aoharuMemberActive.assign(AOHARU_MAX_MEMBERS, 0);
            aoharuMemberBond.assign(AOHARU_MAX_MEMBERS, 0);
            aoharuMemberGauge.assign(AOHARU_MAX_MEMBERS, 0);
            aoharuMemberBurst.assign(AOHARU_MAX_MEMBERS, 0);
            aoharuMemberPolar.assign(AOHARU_MAX_MEMBERS, 0);
            aoharuMemberArrow.assign(AOHARU_MAX_MEMBERS, -1);
            aoharuMemberStat.assign(AOHARU_MAX_MEMBERS, {30,30,30,30,30});
        }
    }
    int aoharuMemberCount() const {
        int n = 0;
        for (int a : aoharuMemberActive) if (a) n++;
        return n;
    }

    std::array<double, NUM_STATS> stratWeight{1,1,1,1,1};
    double stratSkill = 1.0;
    std::array<double, NUM_STATS> statWeights{1,1,1,1,1};   // 目標育成: 各屬性訓練權重 (速 耐 力 根 智)
    std::array<double, NUM_STATS> statTargets{0,0,0,0,0};   // 目標育成數值 (0=未設, 用五圍上限)

    std::array<SupportCard, NUM_CARDS> deck;

    // ---- 回合判定 ----
    bool isTerminal() const { return turn > TOTAL_TURN; }
    bool isXiahesu() const { return (37 <= turn && turn <= 40) || (61 <= turn && turn <= 64); }
    bool isCurrRacing() const {
        for (int t : raceTurns) if (t == turn) return true;
        return false;
    }
    bool isRaceAvailable() const { return 14 <= turn && turn <= 72; }
    int getTrainingLevel(int tra) const { return isAoharu ? aoharuTrainingLevel(tra) : (isXiahesu() ? 4 : (trainCount[tra] / 4)); }
    int aoharuTrainingLevel(int tra) const {
        const std::array<double, NUM_STATS>& my = stats;
        if (isXiahesu()) return 5;
        int n = 0;
        double tot = my[tra];
        for (size_t i = 0; i < aoharuMemberActive.size(); ++i)
            if (aoharuMemberActive[i]) { n++; tot += aoharuMemberStat[i][tra]; }
        return aoharuAvgTier(tot / (n + 1));
    }
    bool isCardShining(int cardIdx, int tra) const {
        const SupportCard& c = deck[cardIdx];
        return (0 <= c.cardType && c.cardType <= 4 && cardBond[cardIdx] >= 80 &&
                c.cardType == tra);
    }
};

// ===========================================================
// 引擎函式 (simulator.cpp)
// ===========================================================
void addStatus(GameState& s, int idx, double value, bool over1200 = true);
double realStatusGain(int value, double gain);
void addVital(GameState& s, int value);
void addMotivation(GameState& s, int value);
void addJiBan(GameState& s, int idx, int value);
void addTrainingLevelCount(GameState& s, int idx, int n);

std::vector<int> legalActions(const GameState& s);
GameState applyAction(const GameState& s, int a, std::mt19937& rng);
GameState rolloutToEnd(GameState s, std::mt19937& rng);
double finalScoreRank(const GameState& s);

// bridge 側 (Python) 對齊用的立即值函式 (rolloutPolicy / MCTS 候選共用)
std::array<double, COUNT> actionValues(const GameState& s);
int rolloutPolicy(const GameState& s, std::mt19937& rng);

void cardRandom(GameState& s, std::mt19937& rng);
void calcTrainingValue(GameState& s);