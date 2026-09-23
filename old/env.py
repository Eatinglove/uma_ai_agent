import numpy as np
import gymnasium as gym
from gymnasium import spaces
from uma import Uma
from card import Card, card_random
from train import TRAIN_APPLIES
from eval import total_eval
import random
class UmaEnv(gym.Env):
    def __init__(self):
        super(UmaEnv, self).__init__()
        self.action_space = spaces.Discrete(7)
        self.observation_space = spaces.Box(low=0, high=1, shape=(25,), dtype=np.float32)
        self.max_rounds = 60
        self.fail_count = 0 
        self.rainbow_counts = np.zeros(5, dtype=int)

    def reset(self):
        self.uma = Uma([326,272,328,244,275], [10, 0, 10, 10, 0]) #花嫁東商
        self.cards = [
            Card([1, 0, 1, 0, 0], [0, 0, 0, 0, 0], [25, 40, 40, 15, 100], 1), #愛如往昔速卡 love>=80 speed+1
            Card([0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [25, 35, 20, 15, 120], 1), #大鳴大放速卡 love>=80 other[0]+10, other[2]+15
            Card([0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [35, 30, 30, 15, 80], 2), #空中神宮耐卡 love>=80 card_bonus[1]+2
            Card([0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [40, 35, 30, 10, 80], 3), #目白阿爾丹力卡 love>=80 card_bonus[1],[2]+1
            Card([0, 0, 1, 0, 0], [20, 0, 0, 30, 0], [30, 25, 50, 10, 65], 4), #美妙姿勢根卡 
            Card([1, 0, 0, 0, 1], [30, 0, 0, 0, 0], [35, 25, 20, 15, 80], 5) #成田大進智卡 love>=80 card_bonus[4]+2
        ]
        self.current_round = 1
        self.fail_count = 0
        self.rainbow_counts = np.zeros(5, dtype=int)
        self.lvl_tracker = {i: 1 for i in range(1, 6)}
        self.click_tracker = {i: 0 for i in range(1, 6)}
        card_random(self.cards)
        return self._get_obs()

    def _get_obs(self):
        obs = [
            self.uma.speed/1200, self.uma.stamina/1200, self.uma.power/1200, 
            self.uma.will/1200, self.uma.knowledge/1200,
            self.uma.hp/100, self.uma.mood/5, self.current_round/60
        ]
        obs += [self.lvl_tracker[i]/5 for i in range(1, 6)]
        obs += [c.now/5 for c in self.cards]
        obs += [c.love/100 for c in self.cards]
        return np.array(obs, dtype=np.float32)

    #訓練的主要的邏輯
    def step(self, action): 
        old_score = total_eval(self.uma)
        old_hp, old_mood = self.uma.hp, self.uma.mood
        stats_old = [self.uma.speed, self.uma.stamina, self.uma.power, self.uma.will, self.uma.knowledge]
        old_loves = [c.love for c in self.cards]
        
        action_id = action + 1

        if self.current_round <= 25:
            if old_hp < 50:
                action_id = 6
            else:
                counts = [sum(1 for c in self.cards if c.now == i) for i in range(1, 6)]
                max_count = max(counts)

                best_actions = [i + 1 for i, v in enumerate(counts) if v == max_count]
                action_id = random.choice(best_actions)

        else:
            if old_hp < 50:
                action_id = 6
            else:
                rainbow_score = []
                for i in range(1, 6):
                    r = sum(1 for c in self.cards if c.now == i and c.love >= 80)
                    n = sum(1 for c in self.cards if c.now == i)
                    rainbow_score.append((r, n))

                max_r = max(rainbow_score, key=lambda x: (x[0], x[1]))

                best_actions = [
                    i + 1 for i, v in enumerate(rainbow_score)
                    if v == max_r
                ]

                action_id = random.choice(best_actions)

        #計算彩圈數量
        rainbow_triggered = 0
        if action_id in range(1, 6):

            for card in self.cards:
                if card.type == action_id and card.love >= 80 and card.now == action_id:
                    rainbow_triggered += 1
            if rainbow_triggered > 0:
                self.rainbow_counts[action_id - 1] += 1

        #看有沒有成功
        if action_id in range(1, 6):
            success = TRAIN_APPLIES[action_id](self.uma, self.cards, self.lvl_tracker[action_id])
            if not success: 
                self.fail_count += 1
                panalty = -200
            else:
                panalty = 0
                self.click_tracker[action_id] += 1
                if self.click_tracker[action_id] >= 4:
                    self.lvl_tracker[action_id] = min(5, self.lvl_tracker[action_id] + 1)
                    self.click_tracker[action_id] = 0

        elif action_id == 6: 
            self.uma.rest()
        elif action_id == 7: 
            self.uma.go_out()

        card_random(self.cards)
        self.current_round += 1
        done = self.current_round >= self.max_rounds
        
        targets = [1200, 1200, 1200, 1200, 1200]  
        
        stat_weights = [0.5, 0.5, 0.5, 0.5, 0.5] 
        
        stats_new = [self.uma.speed, self.uma.stamina, self.uma.power, self.uma.will, self.uma.knowledge]
        growth_reward = 0
        reward_score = 0

        love_gain = sum(1 for i, c in enumerate(self.cards) 
                        if old_loves[i] < 80 and c.love > old_loves[i])

        love_reward = love_gain * 120

        if self.current_round < 30:
            love_reward *= 1.5

        cards_under_80 = sum(1 for c in self.cards if c.love < 80)

        select_reward = 0

        if action_id in range(1, 6):
            cards_under_80_at_current = sum(1 for c in self.cards if c.now == action_id and c.love < 80)
            max_love_spot = max([sum(1 for c in self.cards if c.now == i and c.love < 80) for i in range(1, 6)] + [0])

            if cards_under_80_at_current > 0:
                select_reward += 200 * cards_under_80_at_current
            
            if cards_under_80_at_current < max_love_spot:
                select_reward -= 800   

        panalty = 0

        if self.fail_count >= 2:
            panalty -= 200

        if self.fail_count >= 3:
            panalty -= 800

        if self.fail_count > 3:
            panalty -= 1500 * (self.fail_count - 3)

        if action_id in range(1, 6):
            cards_on_this_pos = sum(1 for card in self.cards if card.now == action_id)
            
            if cards_on_this_pos == 0:
                panalty -= 800  

        if action_id == 6 and self.uma.hp > 70:
            panalty -= 300  

        if action_id == 7 and self.uma.mood >= 5:
            panalty -= 300   

        if action_id in range(1, 6) and old_hp < 30:
            panalty -= 300

        reward_util = rainbow_triggered * 25.0

        if action_id == 6:
            hp_gain = self.uma.hp - old_hp
            reward_util += hp_gain * 15  

            if old_hp < 60:
                reward_util += 150
            if old_hp < 40:
                reward_util += 250

        if old_hp < 30:
            reward_util += (400 if action_id == 6 else -400)

        if old_mood <= 2 and action_id == 7:
            reward_util += 1000

        if total_eval(self.uma) < old_score:
            reward_util -= 100

        progress = self.current_round / self.max_rounds
        late_penalty = cards_under_80 * (progress ** 2) * 800

        full_love_bonus = sum(1 for c in self.cards if c.love >= 80) * 80

        early_choice_reward = 0

        if self.current_round <= 24:
            counts = [sum(1 for c in self.cards if c.now == i) for i in range(1, 6)]
            max_count = max(counts)

            if action_id in range(1, 6):
                chosen_count = counts[action_id - 1]

                if old_hp < 40:
                    early_choice_reward -= 300
                else:
                    if chosen_count == max_count:
                        early_choice_reward += 300 * chosen_count
                    else:
                        early_choice_reward -= 400 * (max_count - chosen_count)

            if action_id == 6:
                if old_hp < 40:
                    early_choice_reward += 300
                else:
                    early_choice_reward -= 200

        total_reward = (
            reward_score + 
            love_reward + 
            reward_util + 
            select_reward + 
            panalty +
            full_love_bonus +
            early_choice_reward -
            late_penalty
        )

        if done:
            dist = sum(abs(stats_new[i] - targets[i]) for i in range(5))
            total_reward += (5000 - dist) / 50.0
            
            total_reward -= (cards_under_80 ** 2) * 300

        return self._get_obs(), total_reward, done, {"r_score": reward_score, "r_love": love_reward}
