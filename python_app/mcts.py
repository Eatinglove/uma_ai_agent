"""Python 移植版 MCTS (對應 cpp_cores/mcts.hpp, UCB1)

- 未探訪的子節點無條件優先
- 回傳訪問次數最多的子節點之行動
- 候選過多時依立即值 (rolloutPolicy 同源) 裁到前 _MAX_CANDIDATES 個集中採樣
"""
import math
import random

from simulator import GameState, legalActions, applyAction, rolloutToEnd, REST, _action_values


class _Node:
    __slots__ = ("state", "actionFromParent", "parent", "children",
                 "untriedActions", "visitCount", "totalScore")

    _MAX_CANDIDATES = 4

    def __init__(self, state, actionFromParent, parent=None):
        self.state = state
        self.actionFromParent = actionFromParent
        self.parent = parent
        self.children = []
        self.untriedActions = legalActions(state) if not state.isTerminal() else []
        if len(self.untriedActions) > _Node._MAX_CANDIDATES and not state.isCurrRacing():
            vals = _action_values(state)
            self.untriedActions = sorted(
                self.untriedActions, key=lambda a: -vals.get(a, -1e9)
            )[:_Node._MAX_CANDIDATES]
        self.visitCount = 0
        self.totalScore = 0.0

    def isTerminal(self):
        return self.state.isTerminal()

    def isFullyExpanded(self):
        return not self.untriedActions

    def averageScore(self):
        return self.totalScore / self.visitCount if self.visitCount else 0.0


class MCTS:
    def __init__(self, explorationConst=1.4, iterations=5000, seed=None):
        self.C = explorationConst
        self.iterations = iterations
        self.rng = random.Random(seed) if seed is not None else random.Random()

    def search(self, rootState):
        best, _ = self.searchWithStats(rootState)
        return best

    # 回傳 (最佳行動, [候選統計])。候選統計 = {action, visits, avg, prec}
    def searchWithStats(self, rootState):
        root = _Node(rootState, None)

        for _ in range(self.iterations):
            node = self._select(root)
            if not node.isTerminal() and not node.isFullyExpanded():
                node = self._expand(node)
            score = self._simulate(node)
            self._backpropagate(node, score)

        best = None
        stats = []
        for c in root.children:
            item = {
                "action": c.actionFromParent,
                "visits": c.visitCount,
                "avg": c.averageScore(),
                "prec": (100.0 * c.visitCount) / max(1, root.visitCount),
            }
            stats.append(item)
            if best is None or c.visitCount > best.visitCount:
                best = c
        return (best.actionFromParent if best else REST), stats

    def _select(self, node):
        while (not node.isTerminal() and node.isFullyExpanded()
               and node.children):
            node = self._bestUCB(node)
        return node

    def _bestUCB(self, node):
        lnN = math.log(max(1, node.visitCount))
        best = None
        bestValue = float("-inf")
        for child in node.children:
            if child.visitCount == 0:
                return child
            ucb = child.averageScore() + self.C * math.sqrt(lnN / child.visitCount)
            if ucb > bestValue:
                bestValue = ucb
                best = child
        return best

    def _expand(self, node):
        if not node.untriedActions:
            return node
        a = node.untriedActions.pop()
        nextState = applyAction(node.state, a, self.rng)
        node.children.append(_Node(nextState, a, node))
        return node.children[-1]

    def _simulate(self, node):
        finalState = rolloutToEnd(node.state.clone(), self.rng)
        return finalState.evaluate()

    def _backpropagate(self, node, score):
        while node is not None:
            node.visitCount += 1
            node.totalScore += score
            node = node.parent