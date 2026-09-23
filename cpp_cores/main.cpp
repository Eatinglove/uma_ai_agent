#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

#include "mcts.hpp"
#include "simulator.hpp"

// ===========================================================
// 中文輸出調校 (Windows 限定)
// ===========================================================
static void setupConsole() {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
#endif
}

// ===========================================================
// 迷你 JSON parser (自有 engine input schema 用，不引入外部函式庫)
// ===========================================================
namespace jmini {

struct Value;
using Object = std::vector<std::pair<std::string, Value>>;
using Array = std::vector<Value>;

struct Value {
    enum Kind { Null, Bool, Num, Str, Obj, Arr } kind = Null;
    bool b = false;
    double num = 0.0;
    std::string str;
    Object obj;
    Array arr;

    const Value* find(const std::string& key) const {
        if (kind == Obj)
            for (const auto& p : obj)
                if (p.first == key) return &p.second;
        return nullptr;
    }
    const Value* child(size_t i) const {
        if (kind == Arr && i < arr.size()) return &arr[i];
        return nullptr;
    }
    size_t size() const { return kind == Arr ? arr.size() : (kind == Obj ? obj.size() : 0); }
};

class Parser {
public:
    explicit Parser(const std::string& text) : s_(text) {}

    Value parse() {
        Value v = parseValue();
        skipWs();
        if (pos_ != s_.size())
            fail("trailing characters");
        return v;
    }

private:
    const std::string& s_;
    size_t pos_ = 0;

    void fail(const std::string& msg) { throw std::runtime_error("json parse: " + msg); }
    void skipWs() {
        while (pos_ < s_.size() && (s_[pos_] == ' ' || s_[pos_] == '\t' ||
                                    s_[pos_] == '\n' || s_[pos_] == '\r'))
            ++pos_;
    }
    char peek() {
        if (pos_ >= s_.size()) fail("unexpected end");
        return s_[pos_];
    }
    void expect(char c) {
        if (peek() != c) fail(std::string("expected '") + c + "'");
        ++pos_;
    }

    static void appendUtf8(std::string& out, unsigned cp) {
        if (cp < 0x80) {
            out += (char)cp;
        } else if (cp < 0x800) {
            out += (char)(0xC0 | (cp >> 6));
            out += (char)(0x80 | (cp & 0x3F));
        } else {
            out += (char)(0xE0 | (cp >> 12));
            out += (char)(0x80 | ((cp >> 6) & 0x3F));
            out += (char)(0x80 | (cp & 0x3F));
        }
    }

    std::string parseString() {
        expect('"');
        std::string out;
        while (pos_ < s_.size()) {
            char c = s_[pos_++];
            if (c == '"') return out;
            if (c == '\\') {
                if (pos_ >= s_.size()) fail("bad escape");
                char e = s_[pos_++];
                switch (e) {
                    case '"': out += '"'; break;
                    case '\\': out += '\\'; break;
                    case '/': out += '/'; break;
                    case 'b': out += '\b'; break;
                    case 'f': out += '\f'; break;
                    case 'n': out += '\n'; break;
                    case 'r': out += '\r'; break;
                    case 't': out += '\t'; break;
                    case 'u': {
                        if (pos_ + 4 > s_.size()) fail("bad \\u");
                        unsigned cp = 0;
                        for (int i = 0; i < 4; ++i) {
                            char h = s_[pos_++];
                            cp <<= 4;
                            if (h >= '0' && h <= '9') cp |= (h - '0');
                            else if (h >= 'a' && h <= 'f') cp |= (h - 'a' + 10);
                            else if (h >= 'A' && h <= 'F') cp |= (h - 'A' + 10);
                            else fail("bad \\u digit");
                        }
                        appendUtf8(out, cp);
                        break;
                    }
                    default: fail("bad escape char");
                }
            } else {
                out += c;
            }
        }
        fail("unterminated string");
        return out;
    }

    Value parseNumber() {
        Value v; v.kind = Value::Num;
        size_t start = pos_;
        if (peek() == '-') ++pos_;
        while (pos_ < s_.size() && isdigit(s_[pos_])) ++pos_;
        bool fraction = false;
        if (pos_ < s_.size() && s_[pos_] == '.') { fraction = true; ++pos_; while (pos_ < s_.size() && isdigit(s_[pos_])) ++pos_; }
        if (pos_ < s_.size() && (s_[pos_] == 'e' || s_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < s_.size() && (s_[pos_] == '+' || s_[pos_] == '-')) ++pos_;
            while (pos_ < s_.size() && isdigit(s_[pos_])) ++pos_;
        }
        v.num = std::strtod(s_.substr(start, pos_ - start).c_str(), nullptr);
        return v;
    }

    Value parseValue() {
        skipWs();
        char c = peek();
        Value v;
        if (c == '{') {
            v.kind = Value::Obj; ++pos_; skipWs();
            if (peek() == '}') { ++pos_; return v; }
            while (true) {
                skipWs();
                std::string key = parseString();
                skipWs(); expect(':');
                Value val = parseValue();
                v.obj.emplace_back(std::move(key), std::move(val));
                skipWs();
                char d = peek();
                if (d == ',') { ++pos_; continue; }
                if (d == '}') { ++pos_; return v; }
                fail("expected , or }");
            }
        } else if (c == '[') {
            v.kind = Value::Arr; ++pos_; skipWs();
            if (peek() == ']') { ++pos_; return v; }
            while (true) {
                v.arr.push_back(parseValue());
                skipWs();
                char d = peek();
                if (d == ',') { ++pos_; continue; }
                if (d == ']') { ++pos_; return v; }
                fail("expected , or ]");
            }
        } else if (c == '"') {
            v.kind = Value::Str; v.str = parseString();
        } else if (c == 't') {
            if (s_.compare(pos_, 4, "true") == 0) { pos_ += 4; v.kind = Value::Bool; v.b = true; }
            else fail("bad literal");
        } else if (c == 'f') {
            if (s_.compare(pos_, 5, "false") == 0) { pos_ += 5; v.kind = Value::Bool; v.b = false; }
            else fail("bad literal");
        } else if (c == 'n') {
            if (s_.compare(pos_, 4, "null") == 0) { pos_ += 4; v.kind = Value::Null; }
            else fail("bad literal");
        } else if (c == '-' || isdigit(c)) {
            return parseNumber();
        } else {
            fail("unexpected char");
        }
        return v;
    }
};

// ---- 讀取輔助 ----
static const Value* field(const Value& o, const std::string& key) { return o.find(key); }

static int getInt(const Value& o, const std::string& key, int def) {
    const Value* v = o.find(key);
    if (!v) return def;
    if (v->kind == Value::Num) return (int)v->num;
    if (v->kind == Value::Bool) return v->b ? 1 : 0;
    return def;
}

static double getNum(const Value& o, const std::string& key, double def) {
    const Value* v = o.find(key);
    if (v && v->kind == Value::Num) return v->num;
    return def;
}

static std::string getStr(const Value& o, const std::string& key, const std::string& def = "") {
    const Value* v = o.find(key);
    if (v && v->kind == Value::Str) return v->str;
    return def;
}

static std::vector<std::vector<int>> getIntArr2D(const Value& o, const std::string& key) {
    std::vector<std::vector<int>> out;
    const Value* v = o.find(key);
    if (!v || v->kind != Value::Arr) return out;
    for (const auto& row : v->arr) {
        std::vector<int> r;
        if (row.kind == Value::Arr)
            for (const auto& e : row.arr)
                r.push_back(e.kind == Value::Num ? (int)e.num : 0);
        out.push_back(r);
    }
    return out;
}

static std::vector<int> getIntArr(const Value& o, const std::string& key) {
    std::vector<int> out;
    const Value* v = o.find(key);
    if (!v || v->kind != Value::Arr) return out;
    for (const auto& e : v->arr)
        out.push_back(e.kind == Value::Num ? (int)e.num : 0);
    return out;
}

static std::vector<double> getNumArr(const Value& o, const std::string& key) {
    std::vector<double> out;
    const Value* v = o.find(key);
    if (!v || v->kind != Value::Arr) return out;
    for (const auto& e : v->arr)
        out.push_back(e.kind == Value::Num ? e.num : 0.0);
    return out;
}

static double arrAt(const jmini::Value& o, size_t i, double def) {
    const Value* v = o.child(i);
    if (v && v->kind == Value::Num) return v->num;
    return def;
}

}  // namespace jmini

// ===========================================================
// engine input 載入 (對齊 bridge.py serialize_state 產出的 schema)
// ===========================================================
static void fillCard(SupportCard& c, const jmini::Value& o) {
    c.type = jmini::getInt(o, "type", c.type);
    c.cardType = jmini::getInt(o, "cardType", c.cardType);
    auto bonus = jmini::getNumArr(o, "cardBonus");
    for (size_t i = 0; i < bonus.size() && i < NUM_STATS; ++i) c.cardBonus[i] = (int)bonus[i];
    std::array<int, NUM_STATS> tmp{0,0,0,0,0};
    c.skillPtBonus = jmini::getInt(o, "skillPtBonus", 0);
    auto initStats = jmini::getNumArr(o, "initStats");
    for (size_t i = 0; i < initStats.size() && i < NUM_STATS; ++i) tmp[i] = (int)initStats[i];
    c.initStats = tmp;
    c.initSkillPt = jmini::getInt(o, "initSkillPt", 0);
    c.initialBond = jmini::getInt(o, "initialBond", 0);
    c.friendPct = jmini::getNum(o, "friendPct", 0);
    c.moodPct = jmini::getNum(o, "moodPct", 0);
    c.trainPct = jmini::getNum(o, "trainPct", 0);
    c.specialtyRate = jmini::getNum(o, "specialtyRate", 0);
    c.saiHou = jmini::getNum(o, "saiHou", 0);
    c.hintProb = jmini::getNum(o, "hintProb", 0);
    c.failRateDrop = jmini::getNum(o, "failRateDrop", 0);
    c.vitalCostDrop = jmini::getNum(o, "vitalCostDrop", 0);
    c.wizVitalBonus = jmini::getInt(o, "wizVitalBonus", 0);
    c.hintLevel = jmini::getInt(o, "hintLevel", 0);
    c.uniqueEffectType = jmini::getInt(o, "uniqueEffectType", 0);
    c.uniqueEffectParam = jmini::getNumArr(o, "uniqueEffectParam");
}

static GameState loadState(const jmini::Value& root) {
    GameState s;
    s.turn = jmini::getInt(root, "turn", 1);
    s.stamina = jmini::getInt(root, "stamina", 100);
    s.mood = jmini::getInt(root, "mood", 3);
    s.fans = jmini::getInt(root, "fans", 0);
    s.skillPt = jmini::getNum(root, "skillPt", 0);
    s.shiningCount = jmini::getInt(root, "shiningCount", 0);
    s.umaStars = jmini::getInt(root, "umaStars", 3);
    s.skillScore = jmini::getInt(root, "skillScore", 0);
    s.maxVital = jmini::getInt(root, "maxVital", 100);
    s.failureRateBias = jmini::getInt(root, "failureRateBias", 0);
    s.isPositiveThinking = jmini::getInt(root, "isPositiveThinking", 0) != 0;
    s.isRefreshMind = jmini::getInt(root, "isRefreshMind", 0) != 0;
    s.friendshipNoncardYayoi = jmini::getInt(root, "friendshipNoncardYayoi", 0);
    s.friendshipNoncardReporter = jmini::getInt(root, "friendshipNoncardReporter", 0);
    s.saiHou = jmini::getNum(root, "saiHou", 0);

    auto stats = jmini::getNumArr(root, "stats");
    for (size_t i = 0; i < stats.size() && i < NUM_STATS; ++i) s.stats[i] = stats[i];
    auto tc = jmini::getIntArr(root, "trainCount");
    for (size_t i = 0; i < tc.size() && i < NUM_TRAININGS; ++i) s.trainCount[i] = tc[i];
    auto cb = jmini::getIntArr(root, "cardBond");
    for (size_t i = 0; i < cb.size() && i < NUM_CARDS; ++i) s.cardBond[i] = cb[i];
    auto cb80 = jmini::getIntArr(root, "cardBond80Turn");
    for (size_t i = 0; i < cb80.size() && i < NUM_CARDS; ++i) s.cardBond80Turn[i] = cb80[i];

    auto fss = jmini::getIntArr(root, "fiveStatusBonus");
    for (size_t i = 0; i < fss.size() && i < NUM_STATS; ++i) s.fiveStatusBonus[i] = fss[i];
    auto fsl = jmini::getIntArr(root, "fiveStatusLimit");
    for (size_t i = 0; i < fsl.size() && i < NUM_STATS; ++i) s.fiveStatusLimit[i] = fsl[i];

    auto zbc = jmini::getIntArr(root, "zhongMaBlueCount");
    for (size_t i = 0; i < zbc.size() && i < NUM_STATS; ++i) s.zhongMaBlueCount[i] = zbc[i];
    auto zbe = jmini::getIntArr(root, "zhongMaExtraBonus");
    for (size_t i = 0; i < zbe.size() && i < 6; ++i) s.zhongMaExtraBonus[i] = zbe[i];

    s.raceTurns = jmini::getIntArr(root, "raceTurns");
    auto hn = jmini::getIntArr(root, "hintNow");
    for (size_t i = 0; i < hn.size() && i < NUM_CARDS; ++i) s.hintNow[i] = hn[i];

    if (const jmini::Value* pd = root.find("personDist")) {
        for (size_t t = 0; t < pd->size() && t < NUM_TRAININGS; ++t) {
            const jmini::Value* row = pd->child(t);
            if (row)
                for (size_t h = 0; h < row->size() && h < NUM_TRAININGS; ++h)
                    s.personDist[t][h] = (int)jmini::arrAt(*row, h, -1);
        }
    }
    auto its = jmini::getIntArr(root, "isTrainShining");
    for (size_t i = 0; i < its.size() && i < NUM_TRAININGS; ++i) s.isTrainShining[i] = its[i];

    if (const jmini::Value* tv = root.find("trainValue")) {
        for (size_t t = 0; t < tv->size() && t < NUM_TRAININGS; ++t) {
            const jmini::Value* row = tv->child(t);
            if (row)
                for (size_t i = 0; i < row->size() && i < 6; ++i)
                    s.trainValue[t][i] = jmini::arrAt(*row, i, 0.0);
        }
    }
    auto tvc = jmini::getIntArr(root, "trainVitalChange");
    for (size_t i = 0; i < tvc.size() && i < NUM_TRAININGS; ++i) s.trainVitalChange[i] = tvc[i];
    auto fr = jmini::getIntArr(root, "failRate");
    for (size_t i = 0; i < fr.size() && i < NUM_TRAININGS; ++i) s.failRate[i] = fr[i];
    auto tcl = jmini::getIntArr(root, "trainClicked");
    for (size_t i = 0; i < tcl.size() && i < NUM_CARDS; ++i) s.trainClicked[i] = tcl[i];

    if (const jmini::Value* st = root.find("strategy")) {
        auto w = jmini::getNumArr(*st, "weight");
        for (size_t i = 0; i < w.size() && i < NUM_STATS; ++i) s.stratWeight[i] = w[i];
        s.stratSkill = jmini::getNum(*st, "skill", 1.0);
    }

    auto sw = jmini::getNumArr(root, "statWeights");   // 目標育成屬性權重 (缺省=全1)
    for (size_t i = 0; i < sw.size() && i < NUM_STATS; ++i) {
        if (sw[i] >= 0 && sw[i] <= 3) s.statWeights[i] = sw[i];
    }

    auto st = jmini::getNumArr(root, "statTargets"); // 目標育成數值 (0=未設)
    for (size_t i = 0; i < st.size() && i < NUM_STATS; ++i) {
        if (st[i] > 0 && st[i] <= 1400) s.statTargets[i] = st[i];
    }

    if (const jmini::Value* dk = root.find("deck")) {
        for (size_t i = 0; i < dk->size() && i < NUM_CARDS; ++i) {
            const jmini::Value* c = dk->child(i);
            if (c) fillCard(s.deck[i], *c);
        }
    }

    // ---- アオハル盃 (aoharu) ----
    {
        std::string scenario = jmini::getStr(root, "scenario");
        s.isAoharu = (scenario == "aoharu");
        s.aoharuTeamRank = jmini::getInt(root, "aoharuTeamRank", 30);
        s.aoharuBurstCount = jmini::getInt(root, "aoharuBurstCount", 0);

        auto act = jmini::getIntArr(root, "aoharuMemberActive");
        auto bond = jmini::getIntArr(root, "aoharuMemberBond");
        auto gauge = jmini::getIntArr(root, "aoharuMemberGauge");
        auto burst = jmini::getIntArr(root, "aoharuMemberBurst");
        auto polar = jmini::getIntArr(root, "aoharuMemberPolar");
        auto arrow = jmini::getIntArr(root, "aoharuMemberArrow");
        auto stat2 = jmini::getIntArr2D(root, "aoharuMemberStat");
        size_t nMem = act.size();
        s.aoharuMemberActive.assign(nMem, 0);
        s.aoharuMemberBond.assign(nMem, 0);
        s.aoharuMemberGauge.assign(nMem, 0);
        s.aoharuMemberBurst.assign(nMem, 0);
        s.aoharuMemberPolar.assign(nMem, 0);
        s.aoharuMemberArrow.assign(nMem, -1);
        s.aoharuMemberStat.assign(nMem, {30,30,30,30,30});
        for (size_t i = 0; i < nMem; ++i) {
            s.aoharuMemberActive[i] = (i < act.size())  ? act[i]  : 0;
            if (i < bond.size())  s.aoharuMemberBond[i] = bond[i];
            if (i < gauge.size()) s.aoharuMemberGauge[i] = gauge[i];
            if (i < burst.size()) s.aoharuMemberBurst[i] = burst[i];
            if (i < polar.size()) s.aoharuMemberPolar[i] = polar[i];
            if (i < arrow.size()) s.aoharuMemberArrow[i] = arrow[i];
            if (i < stat2.size())
                for (size_t k = 0; k < stat2[i].size() && k < NUM_STATS; ++k)
                    s.aoharuMemberStat[i][k] = stat2[i][k];
        }

        auto cg = jmini::getIntArr(root, "aoharuCardGauge");
        for (size_t i = 0; i < cg.size() && i < NUM_CARDS; ++i) s.aoharuCardGauge[i] = cg[i];
        auto cbA = jmini::getIntArr(root, "aoharuCardBurst");
        for (size_t i = 0; i < cbA.size() && i < NUM_CARDS; ++i) s.aoharuCardBurst[i] = cbA[i];

        auto soul2 = jmini::getIntArr2D(root, "aoharuSoulDict");
        for (size_t t = 0; t < soul2.size() && t < NUM_TRAININGS; ++t)
            s.aoharuSoulDict[t] = soul2[t];
        auto sp2 = jmini::getIntArr2D(root, "aoharuSPDict");
        for (size_t t = 0; t < sp2.size() && t < NUM_TRAININGS; ++t)
            s.aoharuSPDict[t] = sp2[t];
    }
    return s;
}

// ===========================================================
// JSON 輸出
// ===========================================================
static std::string jsonNum(double v) {
    std::ostringstream os;
    os << std::fixed << std::setprecision(6) << v;
    return os.str();
}

static void writeFile(const std::string& path, const std::string& text) {
    if (path.empty()) {
        std::cout << text << "\n";
        return;
    }
    std::ofstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot write output: " + path);
    f << text;
}

static std::string readFile(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open input: " + path);
    std::ostringstream os;
    os << f.rdbuf();
    return os.str();
}

// ===========================================================
// 指令: recommend (K 棵樹聚合, 對齊 bridge.py 邏輯)
// ===========================================================
static int cmdRecommend(const std::string& inputPath, const std::string& outputPath,
                        int seeds, int perRun, long long seedBase) {
    GameState state = loadState(jmini::Parser(readFile(inputPath)).parse());

    std::array<int, COUNT> visits{};
    std::array<double, COUNT> aggVal{};   // avg*visits 加權累積
    std::array<int, COUNT> votes{};
    int rootVisits = 0;
    int bestAction = Action::Rest;
    int bestVisits = 0;

    for (int i = 0; i < seeds; ++i) {
        std::mt19937 rng((unsigned)((seedBase + i) & 0xFFFFFFFFu));
        MCTS mc(1.4, perRun, rng);
        std::vector<MCTS::Stat> st;
        int treeBest = mc.searchWithStats(state, st);
        votes[treeBest] += 1;
        for (const auto& it : st) {
            int a = it.action;
            if (a < 0 || a >= COUNT) continue;
            aggVal[a] += it.avg * it.visits;
            visits[a] += it.visits;
            rootVisits += it.visits;
        }
    }

    for (int a = 0; a < COUNT; ++a)
        if (visits[a] > bestVisits) { bestVisits = visits[a]; bestAction = a; }

    std::ostringstream os;
    os << "{\"best\":" << bestAction
       << ",\"root_visits\":" << rootVisits
       << ",\"stats\":[";
    bool first = true;
    for (int a = 0; a < COUNT; ++a) {
        if (visits[a] <= 0) continue;
        double avg = aggVal[a] / visits[a];
        if (!first) os << ",";
        first = false;
        os << "{\"action\":" << a
           << ",\"visits\":" << visits[a]
           << ",\"avg\":" << jsonNum(avg)
           << ",\"votes\":" << votes[a] << "}";
    }
    os << "]}";

    writeFile(outputPath, os.str());
    return 0;
}

// ===========================================================
// 指令: parity (固定首行動 rollout N 次, 輸出平均/分位)
// ===========================================================
static int cmdParity(const std::string& inputPath, const std::string& outputPath,
                     int action, int n, long long seedBase) {
    GameState state = loadState(jmini::Parser(readFile(inputPath)).parse());

    std::vector<double> scores;
    scores.reserve(n);
    for (int i = 0; i < n; ++i) {
        std::mt19937 rng((unsigned)((seedBase + i) & 0xFFFFFFFFu));
        GameState next = applyAction(state, action, rng);
        GameState finalState = rolloutToEnd(next, rng);
        scores.push_back(finalScoreRank(finalState));
    }

    double sum = 0;
    double mn = scores[0], mx = scores[0];
    for (double x : scores) { sum += x; mn = std::min(mn, x); mx = std::max(mx, x); }
    std::vector<double> srt = scores;
    std::sort(srt.begin(), srt.end());
    double p50 = srt[n / 2];
    double p10 = srt[(int)(0.10 * (n - 1))];
    double p90 = srt[(int)(0.90 * (n - 1))];

    std::ostringstream os;
    os << "{\"action\":" << action
       << ",\"n\":" << n
       << ",\"avg\":" << jsonNum(sum / n)
       << ",\"min\":" << jsonNum(mn)
       << ",\"max\":" << jsonNum(mx)
       << ",\"p10\":" << jsonNum(p10)
       << ",\"p50\":" << jsonNum(p50)
       << ",\"p90\":" << jsonNum(p90)
       << "}";
    writeFile(outputPath, os.str());
    return 0;
}

// ===========================================================
// 指令: board (立即值 actionValues, 無隨機; 規則平行對照用)
// ===========================================================
static int cmdBoard(const std::string& inputPath, const std::string& outputPath) {
    GameState state = loadState(jmini::Parser(readFile(inputPath)).parse());
    std::array<double, COUNT> v = actionValues(state);
    std::ostringstream os;
    os << "{\"stats\":[";
    bool first = true;
    for (int a = 0; a < COUNT; ++a) {
        if (!first) os << ",";
        first = false;
        os << "{\"action\":" << a << ",\"value\":" << jsonNum(v[a]) << "}";
    }
    os << "]}";
    writeFile(outputPath, os.str());
    return 0;
}

// ===========================================================
// 指令: run (整場 URA 模擬: 每回合 C++ MCTS 決定行動 → 模擬到底)
// ===========================================================
static int cmdRun(const std::string& inputPath, const std::string& outputPath,
                  int runs, int iterations, long long seedBase, bool logTurns) {
    GameState base = loadState(jmini::Parser(readFile(inputPath)).parse());

    std::vector<double> scores;
    std::vector<std::array<int, NUM_STATS>> finalStats;
    std::vector<int> finalsFans;
    std::vector<int> finalsSkillPt;

    for (int r = 0; r < runs; ++r) {
        GameState s = base;
        std::mt19937 rng((unsigned)((seedBase + r) & 0xFFFFFFFFu));
        while (!s.isTerminal()) {
            int a;
            if (s.isCurrRacing()) a = Action::Race;   // 強制出賽週
            else {
                // 每回合獨立 MCTS RNG seed ((runIdx*1003)+turn)，與 Python _mcts_games 對照
                std::mt19937 mrng((unsigned)(((seedBase + r) * 1003 + s.turn) & 0xFFFFFFFFu));
                MCTS mc(1.4, iterations, mrng);
                a = mc.search(s);
            }
            if (logTurns) {
                std::cout << "run " << (r + 1) << "/" << runs
                          << " turn=" << s.turn << " vit=" << s.stamina
                          << " mood=" << (int)s.mood
                          << " stats=[";
                for (int i = 0; i < NUM_STATS; ++i)
                    std::cout << (i ? "," : "") << (int)s.stats[i];
                std::cout << "] -> " << actionName(a) << "\n";
            }
            s = applyAction(s, (Action)a, rng);
        }
        scores.push_back(finalScoreRank(s));
        std::array<int, NUM_STATS> st{};
        for (int i = 0; i < NUM_STATS; ++i) st[i] = (int)s.stats[i];
        finalStats.push_back(st);
        finalsFans.push_back(s.fans);
        finalsSkillPt.push_back((int)s.skillPt);
    }

    std::vector<double> srt = scores;
    std::sort(srt.begin(), srt.end());
    double mean = 0;
    for (double x : scores) mean += x;
    mean /= runs;

    std::array<double, NUM_STATS> avgStats{};
    double avgFans = 0, avgSkillPt = 0;
    for (int r = 0; r < runs; ++r) {
        for (int i = 0; i < NUM_STATS; ++i) avgStats[i] += finalStats[r][i];
        avgFans += finalsFans[r];
        avgSkillPt += finalsSkillPt[r];
    }

    std::ostringstream os;
    os << "{\"runs\":[";
    for (int r = 0; r < runs; ++r) {
        if (r) os << ",";
        os << "{\"score\":" << jsonNum(scores[r]) << ",\"stats\":[";
        for (int i = 0; i < NUM_STATS; ++i)
            os << (i ? "," : "") << finalStats[r][i];
        os << "],\"fans\":" << finalsFans[r]
           << ",\"skillPt\":" << finalsSkillPt[r] << "}";
    }
    os << "],\"mean\":" << jsonNum(mean)
       << ",\"p10\":" << jsonNum(srt[(int)(0.10 * (runs - 1))])
       << ",\"p50\":" << jsonNum(srt[runs / 2])
       << ",\"p90\":" << jsonNum(srt[(int)(0.90 * (runs - 1))])
       << ",\"min\":" << jsonNum(srt[0])
       << ",\"max\":" << jsonNum(srt[runs - 1])
       << ",\"avg_stats\":[";
    for (int i = 0; i < NUM_STATS; ++i)
        os << (i ? "," : "") << jsonNum(avgStats[i] / runs);
    os << "],\"avg_fans\":" << jsonNum(avgFans / runs)
       << ",\"avg_skillPt\":" << jsonNum(avgSkillPt / runs)
       << "}";
    writeFile(outputPath, os.str());
    return 0;
}

static void printUsage() {
    std::cout
        << "uma_ai.exe <cmd> [options]\n"
        << "  recommend  K 棵樹 MCTS 聚合建議\n"
        << "      --input <state.json>  引擎輸入 (bridge serialize_state 產出)\n"
        << "      --output <out.json>    輸出檔 (省略則印 stdout)\n"
        << "      --seeds <K>            樹數量 (預設 5)\n"
        << "      --per-run <N>          每棵樹迭代次數 (預設 100)\n"
        << "      --seed <S>             主 seed (預設 0; 每棵樹 seed+i)\n"
        << "  parity     固定首行動 rollout N 次統計 (平行對照用)\n"
        << "      --input <state.json>\n"
        << "      --output <out.json>\n"
        << "      --action <A>           首行動 0..7\n"
        << "      --n <N>                rollout 次數 (預設 1200)\n"
        << "      --seed <S>             RNG 種子 (每局 seed+i)\n"
        << "  board       輸出各行動立即值 actionValues (無隨機，規則對照用)\n"
        << "      --input <state.json>\n"
        << "      --output <out.json>\n"
        << "  run         整場 URA 模擬 (每回合 MCTS 決定行動, 跑 N 場統計)\n"
        << "      --input <state.json>  初始局面 (bridge serialize_state 產出)\n"
        << "      --output <out.json>\n"
        << "      --runs <N>            場數 (預設 10)\n"
        << "      --iterations <I>      每回合 MCTS 迭代數 (預設 40)\n"
        << "      --seed <S>            主 seed (第 r 場用 S+r)\n"
        << "      --log                 逐回合輸出決策\n";
}

int main(int argc, char* argv[]) {
    setupConsole();
    if (argc < 2) { printUsage(); return 1; }

    std::string cmd = argv[1];
    std::string inputPath, outputPath;
    int seeds = 5, perRun = 100, action = -1, n = 1200;
    int runs_ = 10, iterations_ = 40;
    bool logTurns = false;
    long long seedBase = 0;

    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) throw std::runtime_error("missing arg for " + arg);
            return argv[++i];
        };
        if (arg == "--input") inputPath = next();
        else if (arg == "--output") outputPath = next();
        else if (arg == "--seeds") seeds = std::stoi(next());
        else if (arg == "--per-run") perRun = std::stoi(next());
        else if (arg == "--n") n = std::stoi(next());
        else if (arg == "--action") action = std::stoi(next());
        else if (arg == "--seed") seedBase = std::stoll(next());
        else if (arg == "--runs") runs_ = std::stoi(next());
        else if (arg == "--iterations") iterations_ = std::stoi(next());
        else if (arg == "--log") logTurns = true;
        else { printUsage(); return 1; }
    }

    try {
        if (cmd == "recommend") {
            if (inputPath.empty() || seeds <= 0 || perRun <= 0) { printUsage(); return 1; }
            return cmdRecommend(inputPath, outputPath, seeds, perRun, seedBase);
        }
        if (cmd == "parity") {
            if (inputPath.empty() || action < 0 || action >= COUNT || n <= 0) { printUsage(); return 1; }
            return cmdParity(inputPath, outputPath, action, n, seedBase);
        }
        if (cmd == "board") {
            if (inputPath.empty()) { printUsage(); return 1; }
            return cmdBoard(inputPath, outputPath);
        }
        if (cmd == "run") {
            if (inputPath.empty() || runs_ <= 0 || iterations_ <= 0) { printUsage(); return 1; }
            return cmdRun(inputPath, outputPath, runs_, iterations_, seedBase, logTurns);
        }
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << "\n";
        return 2;
    }
    printUsage();
    return 1;
}