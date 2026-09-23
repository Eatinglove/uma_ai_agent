# main.py
import sys
from PyQt5.QtWidgets import QApplication
from train import speed, stamina, power, will, knowledge
from uma import Uma
from card import Card, card_random, check_love, event
from ui import UmaUI
import numpy as np
#326,272,328,244,275
uma = Uma([326,272,328,244,275], [10, 0, 10, 10, 0])
#友情 情誼 幹勁 訓練 擅長
cards = [
    Card([1, 0, 1, 0, 0], [0, 0, 0, 0, 0], [25, 40, 40, 15, 100], 1), #愛如往昔速卡 love>=80 speed+1
    Card([0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [25, 35, 20, 15, 120], 1), #大鳴大放速卡 love>=80 other[0]+10, other[2]+15
    Card([0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [35, 30, 30, 15, 80], 2), #空中神宮耐卡 love>=80 card_bonus[1]+2
    Card([0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [40, 35, 30, 10, 80], 3), #目白阿爾丹力卡 love>=80 card_bonus[1],[2]+1
    Card([0, 0, 1, 0, 0], [20, 0, 0, 30, 0], [30, 25, 50, 10, 65], 4), #美妙姿勢根卡 
    Card([1, 0, 0, 0, 1], [30, 0, 0, 0, 0], [35, 25, 20, 15, 80], 5) #成田大進智卡 love>=80 card_bonus[4]+2
]

for c in cards:
    uma.add_stats("speed", c.init_stats[0])
    uma.add_stats("stamina", c.init_stats[1])
    uma.add_stats("power", c.init_stats[2])
    uma.add_stats("will", c.init_stats[3])
    uma.add_stats("knowledge", c.init_stats[4])

card_random(cards)

lvl_tracker = {1:1, 2:1, 3:1, 4:1, 5:1}
click_tracker = {1:0, 2:0, 3:0, 4:0, 5:0}
flags = [0,0,0,0,0,0]
card_events_status = np.zeros((6, 3), dtype=int)
def step(action_id):

    round+1

    lvl = lvl_tracker.get(action_id, 1)

    if action_id == 1:
        speed(uma, cards, lvl)
    elif action_id == 2:
        stamina(uma, cards, lvl)
    elif action_id == 3:
        power(uma, cards, lvl)
    elif action_id == 4:
        will(uma, cards, lvl)
    elif action_id == 5:
        knowledge(uma, cards, lvl)
    elif action_id == 6:
        uma.rest()
    elif action_id == 7:
        uma.go_out()
    elif action_id == 8:
        return False

    check_love(cards,flags)
    event(cards,card_events_status)

    #計算一種訓練被點擊幾次
    if action_id in [1,2,3,4,5]:
        click_tracker[action_id] += 1
        if click_tracker[action_id] >= 4:
            lvl_tracker[action_id] += 1
            click_tracker[action_id] = 0 
            if lvl_tracker[action_id] > 5:
                lvl_tracker[action_id] = 5

    card_random(cards)

    return True

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = UmaUI(uma, cards, step)
    ui.show()
    sys.exit(app.exec_())
