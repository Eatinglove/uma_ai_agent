import random
class Card:
    def __init__(self,card_bonus,init_stats,other,type):
        self.card_bonus=card_bonus #ex:速度+1,力量+2...
        self.init_stats=init_stats #初始屬性
        self.friend=other[0] #友情
        self.love=other[1] #情誼
        self.mood=other[2] #幹勁
        self.train=other[3] #訓練
        self.confidence=other[4] #擅長率
        self.type=type # 1=speed 2=stamina 3=power 4=will 5=knowledge
        self.now=0
    def add_love(self,love):
        self.love+=love
        if self.love>100:
            self.love=100
            

#decide which training is the card at
#1=speed, 2=stamina, 3=power, 4=will, 5=knowledge
def card_random(cards):
    for card in cards:
        x = random.randint(1,100)
        y = 18 + 0.12 * card.confidence
        z=(90-y)/4
        other_type=[1,2,3,4,5]
        other_type.remove(card.type) #remove the type of the card itself (if speed card then remove speed)
        if x > 90:
            card.now = 0 #not training today
        elif x<90 and x > y+3*z:
            card.now=other_type[0]
        elif x< y+3*z and x>y+2*z:
            card.now=other_type[1]
        elif x<y+2*z and x>y+z:
            card.now=other_type[2]
        elif x<y+z and x>y:
            card.now=other_type[3]
        elif x<y:
            card.now=card.type #on its training

def check_love(cards,flags):
    
    if flags[0] !=1 and cards[0].other[1]>=80:
        flags[0]=1
        cards[0].card_bonus[0]=cards[0].card_bonus[0]+1

    if flags[1] !=1 and cards[1].other[1]>=80:
        flags[1]=1
        cards[1].other[0] =cards[1].other[0]+10
        cards[1].other[2] =cards[1].other[0]+15
    
    if flags[2] !=1 and cards[2].other[1]>=80:
        flags[2]=1
        cards[2].card_bonus[1]=cards[2].card_bonus[1]+2
    
    if flags[3] !=1 and cards[3].other[1]>=80:
        flags[3]=1
        cards[3].card_bonus[1]=cards[3].card_bonus[1]+1
        cards[3].card_bonus[2]=cards[3].card_bonus[2]+1
    
    if flags[5] !=1 and cards[5].other[1]>=80:
        flags[5]=1
        cards[5].card_bonus[4]=cards[5].card_bonus[4]+2

def event(cards, event_matrix):

    if event_matrix.sum() >= 18:
        return event_matrix
    
    if random.randint(1, 100) <= 50:
        available_cards = [i for i in range(6) if sum(event_matrix[i]) < 3]

        chosen_idx = random.choice(available_cards)
        
        current_event_idx = -1
        for idx in range(3):
            if event_matrix[chosen_idx][idx] == 0:
                current_event_idx = idx
                event_matrix[chosen_idx][idx] = 1 
                break
        
        if current_event_idx != -1:
            love_gain = EVENT_LOVE_TABLE[chosen_idx][current_event_idx]
            cards[chosen_idx].add_love(love_gain)

    return event_matrix
    
    
EVENT_LOVE_TABLE = [
    [10, 5, 5], # 卡片 1 (愛如往昔)
    [10, 5, 5], # 卡片 2 (大鳴大放)
    [15, 5, 5],  # 卡片 3 (空中神宮)
    [10, 10, 5], # 卡片 4 (目白阿爾丹)
    [5, 5, 5], # 卡片 5 (美妙姿勢)
    [5, 5, 5]  # 卡片 6 (成田大進)
]