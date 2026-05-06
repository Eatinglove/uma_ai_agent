import random

def check_training_fail(uma, base_fail=0):
    fail_rate = base_fail
    if uma.hp < 50:
        fail_rate += (50 - uma.hp) * 2
    roll = random.randint(1,100)
    return roll <= fail_rate

def fail(uma, attr_name):
    #print(f"訓練失敗！{attr_name} -5，心情 -1")
    uma.add_stats(attr_name, -5)
    uma.set_mood(-1)

speed_cost_table = [21,23,24,26,27]
stamina_cost_table = [19,21,22,24,25]
power_cost_table = [20,22,23,25,26]
will_cost_table = [22,24,25,27,28]
knowledge_cost_table = [5,5,5,5,5]  

MOOD_BONUS_MAP = {1:-0.2, 2:-0.1, 3:0, 4:0.1, 5:0.2}

def speed_preview(uma, cards, lvl):
    basic_main_table = [11,12,13,14,15]
    basic_main = basic_main_table[lvl-1]
    basic_side_table = [6,6,7,7,8]
    basic_side = basic_side_table[lvl-1]
    uma_bonus = 1 + uma.speed_bonus/100
    mood_bonus = 0
    train_bonus = 0
    people_bonus = 0
    friend_bonus = 1
    for card in cards:
        if card.now == 1:
            basic_main += card.card_bonus[0]
            basic_side += card.card_bonus[2]
            mood_bonus += card.mood
            train_bonus += card.train
            people_bonus += 0.05
            if card.type == 1 and card.love >= 80:
                friend_bonus *= (1 + card.friend/100)
    Y = MOOD_BONUS_MAP.get(uma.mood, 0)
    main_value = int(basic_main * uma_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value = int(basic_side * uma_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    details = {
        "basic_main": basic_main,
        "uma_bonus": uma_bonus,
        "friend_bonus": friend_bonus,
        "mood_bonus": mood_bonus,
        "train_bonus": train_bonus,
        "people_bonus": people_bonus
    }
    return {"speed": main_value, "power": side_value, "details": details}

def speed(uma, cards, lvl):
    if check_training_fail(uma):
        fail(uma, "speed")
        return False
    delta = speed_preview(uma, cards, lvl)
    for k,v in delta.items():
        if k != "details":
            uma.add_stats(k,v)
    cost = speed_cost_table[lvl-1] if lvl <=5 else speed_cost_table[-1]
    uma.add_hp(-cost)
    for card in cards:
        if card.now == 1:
            card.add_love(5 + uma.love)
    return True

def stamina_preview(uma, cards, lvl):
    basic_main_table = [10,11,12,13,14]
    basic_main = basic_main_table[lvl-1]
    basic_side_table = [6,6,7,7,8]
    basic_side = basic_side_table[lvl-1]
    uma_bonus = 1 + uma.stamina_bonus/100
    uma_side_bonus = 1 + uma.will_bonus/100
    mood_bonus = 0
    train_bonus = 0
    people_bonus = 0
    friend_bonus = 1
    for card in cards:
        if card.now == 2:
            basic_main += card.card_bonus[1]
            basic_side += card.card_bonus[3]
            mood_bonus += card.mood
            train_bonus += card.train
            people_bonus += 0.05
            if card.type == 2 and card.love >= 80:
                friend_bonus *= (1 + card.friend/100)
    Y = MOOD_BONUS_MAP.get(uma.mood, 0)
    main_value = int(basic_main * uma_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value = int(basic_side * uma_side_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    details = {
        "basic_main": basic_main,
        "uma_bonus": uma_bonus,
        "uma_side_bonus": uma_side_bonus,
        "friend_bonus": friend_bonus,
        "mood_bonus": mood_bonus,
        "train_bonus": train_bonus,
        "people_bonus": people_bonus
    }
    return {"stamina": main_value, "will": side_value, "details": details}

def stamina(uma, cards, lvl):
    if check_training_fail(uma):
        fail(uma, "stamina")
        return False
    delta = stamina_preview(uma, cards, lvl)
    for k,v in delta.items():
        if k != "details":
            uma.add_stats(k,v)
    cost = stamina_cost_table[lvl-1] if lvl<=5 else stamina_cost_table[-1]
    uma.add_hp(-cost)
    for card in cards:
        if card.now == 2:
            card.add_love(5 + uma.love)
    return True

def power_preview(uma, cards, lvl):
    basic_main_table = [9,10,11,12,13]
    basic_main = basic_main_table[lvl-1]
    basic_side_table = [6,6,7,7,8]
    basic_side = basic_side_table[lvl-1]
    uma_bonus = 1 + uma.power_bonus/100
    uma_side_bonus = 1 + uma.stamina_bonus/100
    mood_bonus = 0
    train_bonus = 0
    people_bonus = 0
    friend_bonus = 1
    for card in cards:
        if card.now == 3:
            basic_main += card.card_bonus[2]
            basic_side += card.card_bonus[1]
            mood_bonus += card.mood
            train_bonus += card.train
            people_bonus += 0.05
            if card.type == 3 and card.love >= 80:
                friend_bonus *= (1 + card.friend/100)
    Y = MOOD_BONUS_MAP.get(uma.mood, 0)
    main_value = int(basic_main * uma_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value = int(basic_side * uma_side_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    details = {
        "basic_main": basic_main,
        "uma_bonus": uma_bonus,
        "uma_side_bonus": uma_side_bonus,
        "friend_bonus": friend_bonus,
        "mood_bonus": mood_bonus,
        "train_bonus": train_bonus,
        "people_bonus": people_bonus
    }
    return {"power": main_value, "stamina": side_value, "details": details}

def power(uma, cards, lvl):
    if check_training_fail(uma):
        fail(uma, "power")
        return False
    delta = power_preview(uma, cards, lvl)
    for k,v in delta.items():
        if k != "details":
            uma.add_stats(k,v)
    cost = power_cost_table[lvl-1] if lvl<=5 else power_cost_table[-1]
    uma.add_hp(-cost)
    for card in cards:
        if card.now == 3:
            card.add_love(5 + uma.love)
    return True

def will_preview(uma, cards, lvl):
    basic_main_table = [8,9,10,11,13]
    basic_main = basic_main_table[lvl-1]
    basic_side_table = [5,5,5,5,6]
    basic_side = basic_side_table[lvl-1]
    basic_side_table2 = [5,5,5,5,5]
    basic_side2 = basic_side_table2[lvl-1]
    uma_main_bonus = 1 + uma.will_bonus/100
    uma_side_bonus = 1 + uma.speed_bonus/100
    uma_side_bonus2 = 1 + uma.power_bonus/100
    mood_bonus = 0
    train_bonus = 0
    people_bonus = 0
    friend_bonus = 1
    for card in cards:
        if card.now == 4:
            basic_main += card.card_bonus[2]
            basic_side += card.card_bonus[0]
            basic_side2 += card.card_bonus[3]
            mood_bonus += card.mood
            train_bonus += card.train
            people_bonus += 0.05
            if card.type == 4 and card.love >= 80:
                friend_bonus *= (1 + card.friend/100)
    Y = MOOD_BONUS_MAP.get(uma.mood, 0)
    main_value = int(basic_main * uma_main_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value = int(basic_side * uma_side_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value2 = int(basic_side2 * uma_side_bonus2 * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    details = {
        "basic_main": basic_main,
        "uma_main_bonus": uma_main_bonus,
        "uma_side_bonus": uma_side_bonus,
        "uma_side_bonus2": uma_side_bonus2,
        "friend_bonus": friend_bonus,
        "mood_bonus": mood_bonus,
        "train_bonus": train_bonus,
        "people_bonus": people_bonus
    }
    return {"will": main_value, "speed": side_value, "power": side_value2, "details": details}

def will(uma, cards, lvl):
    if check_training_fail(uma):
        fail(uma, "will")
        return False
    delta = will_preview(uma, cards, lvl)
    for k,v in delta.items():
        if k != "details":
            uma.add_stats(k,v)
    cost = will_cost_table[lvl-1] if lvl<=5 else will_cost_table[-1]
    uma.add_hp(-cost)
    for card in cards:
        if card.now == 4:
            card.add_love(5 + uma.love)
    return True

def knowledge_preview(uma, cards, lvl):
    basic_main_table = [10,11,12,13,14]
    basic_main = basic_main_table[lvl-1]
    basic_side_table = [2,2,3,3,4]
    basic_side = basic_side_table[lvl-1]
    uma_bonus = 1 + uma.knowledge_bonus/100
    uma_side_bonus = 1 + uma.speed_bonus/100
    mood_bonus = 0
    train_bonus = 0
    people_bonus = 0
    friend_bonus = 1
    for card in cards:
        if card.now == 5:
            basic_main += card.card_bonus[4]
            basic_side += card.card_bonus[0]
            mood_bonus += card.mood
            train_bonus += card.train
            people_bonus += 0.05
            if card.type == 5 and card.love >= 80:
                friend_bonus *= (1 + card.friend/100)
    Y = MOOD_BONUS_MAP.get(uma.mood, 0)
    main_value = int(basic_main * uma_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    side_value = int(basic_side * uma_side_bonus * friend_bonus * (1 + Y*mood_bonus/100) * (1+train_bonus/100) * (1+people_bonus))
    details = {
        "basic_main": basic_main,
        "uma_bonus": uma_bonus,
        "uma_side_bonus": uma_side_bonus,
        "friend_bonus": friend_bonus,
        "mood_bonus": mood_bonus,
        "train_bonus": train_bonus,
        "people_bonus": people_bonus
    }
    return {"knowledge": main_value, "speed": side_value, "details": details}

def knowledge(uma, cards, lvl):
    if check_training_fail(uma):
        fail(uma, "knowledge")
        return False
    delta = knowledge_preview(uma, cards, lvl)
    for k,v in delta.items():
        if k != "details":
            uma.add_stats(k,v)
    cost = knowledge_cost_table[lvl-1] if lvl<=5 else knowledge_cost_table[-1]
    uma.add_hp(cost+5)
    for card in cards:
        if card.now == 5:
            card.add_love(5 + uma.love)
    return True
    

TRAIN_PREVIEWS = {
    1: speed_preview,
    2: stamina_preview,
    3: power_preview,
    4: will_preview,
    5: knowledge_preview
}

TRAIN_APPLIES = {
    1: speed,
    2: stamina,
    3: power,
    4: will,
    5: knowledge
}
