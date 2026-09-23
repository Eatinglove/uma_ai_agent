#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <vector>

#include "simulator.hpp"

// ===========================================================
// MCTS (對齊 python_app/mcts.py, UCB1)
// - 未探訪的子節點無條件優先
// - 回傳訪問次數最多的子節點之行動
// - 候選過多時依立即值 (actionValues 同源) 裁到前 4 個集中採樣
// - simulate 從 node 自身狀態 rollout 到尾 (與 Python _simulate 一致)
// ===========================================================
class MCTS {
public:
    struct Stat {
        int action = 0;
        int visits = 0;
        double avg = 0.0;
    };

    static constexpr int MAX_CANDIDATES = 4;

    MCTS(double explorationConst, int iterations, std::mt19937& rng)
        : C_(explorationConst), iterations_(iterations), rng_(rng) {}

    int search(const GameState& rootState) {
        std::vector<Stat> st;
        return searchWithStats(rootState, st);
    }

    // 回傳 (最佳行動); 候選統計寫入 out [{action, visits, avg}]
    int searchWithStats(const GameState& rootState, std::vector<Stat>& out) {
        out.clear();
        root_ = std::make_unique<Node>(rootState, Action::Rest, nullptr);

        for (int i = 0; i < iterations_; ++i) {
            Node* node = select(root_.get());
            if (!node->isTerminal() && !node->isFullyExpanded())
                node = expand(node);
            double score = simulate(node);
            backpropagate(node, score);
        }

        Node* best = nullptr;
        for (auto& c : root_->children) {
            Stat s;
            s.action = c->actionFromParent;
            s.visits = c->visitCount;
            s.avg = c->averageScore();
            out.push_back(s);
            if (!best || c->visitCount > best->visitCount)
                best = c.get();
        }
        return best ? best->actionFromParent : Action::Rest;
    }

private:
    struct Node {
        GameState state;
        Action actionFromParent{};
        Node* parent = nullptr;
        std::vector<std::unique_ptr<Node>> children;
        std::vector<int> untriedActions;
        int visitCount = 0;
        double totalScore = 0.0;

        Node(GameState s, Action fromAction, Node* p)
            : state(std::move(s)), actionFromParent(fromAction), parent(p) {
            if (!state.isTerminal()) {
                untriedActions = legalActions(state);
                if ((int)untriedActions.size() > MAX_CANDIDATES && !state.isCurrRacing()) {
                    std::array<double, COUNT> vals = actionValues(state);
                    std::sort(untriedActions.begin(), untriedActions.end(),
                              [&](int a, int b) { return vals[a] > vals[b]; });
                    untriedActions.resize(MAX_CANDIDATES);
                }
            }
        }

        bool isFullyExpanded() const { return untriedActions.empty(); }
        bool isTerminal() const { return state.isTerminal(); }
        double averageScore() const { return visitCount == 0 ? 0.0 : totalScore / visitCount; }
    };

    double C_;
    int iterations_;
    std::mt19937& rng_;
    std::unique_ptr<Node> root_;

    Node* select(Node* node) {
        while (!node->isTerminal() && node->isFullyExpanded() && !node->children.empty())
            node = bestUCB(node);
        return node;
    }

    Node* bestUCB(Node* node) {
        double lnN = std::log(static_cast<double>(std::max(1, node->visitCount)));
        Node* best = nullptr;
        double bestValue = -std::numeric_limits<double>::infinity();
        for (auto& child : node->children) {
            if (child->visitCount == 0) return child.get();
            double ucb = child->averageScore() + C_ * std::sqrt(lnN / child->visitCount);
            if (ucb > bestValue) {
                bestValue = ucb;
                best = child.get();
            }
        }
        return best;
    }

    Node* expand(Node* node) {
        if (node->untriedActions.empty()) return node;
        int a = node->untriedActions.back();
        node->untriedActions.pop_back();
        GameState nextState = applyAction(node->state, (Action)a, rng_);
        node->children.push_back(
            std::make_unique<Node>(std::move(nextState), (Action)a, node));
        return node->children.back().get();
    }

    double simulate(Node* node) {
        GameState finalState = rolloutToEnd(node->state, rng_);
        return finalScoreRank(finalState);
    }

    void backpropagate(Node* node, double score) {
        while (node != nullptr) {
            node->visitCount += 1;
            node->totalScore += score;
            node = node->parent;
        }
    }
};