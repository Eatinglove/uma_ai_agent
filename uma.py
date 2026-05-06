import random
#from round import uma_event
class Uma:
    def __init__(self, init_stats, init_bonus):
        self.speed = init_stats[0]
        self.stamina = init_stats[1]
        self.power = init_stats[2]
        self.will = init_stats[3]
        self.knowledge = init_stats[4]
    
        self.speed_bonus = init_bonus[0]
        self.stamina_bonus = init_bonus[1]
        self.power_bonus = init_bonus[2]
        self.will_bonus = init_bonus[3]
        self.knowledge_bonus = init_bonus[4]
        self.mood = 3
        self.hp = 100
        self.maxhp=100
        self.love=0
        self.fat=0
        #fat,smart,sleepy,good_train,bad_train,headache,lazy

        self.event1=[0,0,0]#決勝服事件
        self.event2=[0,0,0]#有選項的事件
        self.event3=[0,0,0,0,0]#外出事件

    #增加某屬性
    def add_stats(self, kind, stats):
        if hasattr(self, kind):
            setattr(self, kind, getattr(self, kind) + stats)

    #休息
    def rest(self):
        x = random.randint(1, 100)
        if x<15:
            self.add_hp(30)
        elif x>85:
            self.add_hp(70)
        else:
            self.add_hp(50)

    #回復體力或扣除體力
    def add_hp(self,hp):
        self.hp+=hp
        if self.hp>self.maxhp:
            self.hp=self.maxhp
        if self.hp<0:
            self.hp=0

    #設定情誼
    def set_mood(self,mood):
        self.mood+=mood
        if self.mood>5:
            self.mood=5
        if self.mood<1:
            self.mood=1

    #外出
    def go_out(self):
        x = random.randint(1,100)
        if x<35:
            self.set_mood(2)
        elif x>70:
            self.set_mood(1)
            self.add_hp(10)
        else:
            self.set_mood(1)
            y=random.randint(1,105)
            if y<15:
                self.add_hp(30)
            elif y>55:
                self.add_hp(10)
            else:
                self.add_hp(20)
        #uma_event(self,1)

    def show_stats(self):
        print(f"speed: {self.speed}, stamina: {self.stamina}, power: {self.power}, will: {self.will}, knowledge: {self.knowledge}, hp: {self.hp}, mood: {self.mood}")
            