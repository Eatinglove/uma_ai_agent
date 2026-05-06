'''
import random
from card import card_random 

def next_round(uma,cards):
    card_random(cards)
    x = random.randint(1,100)
    #x%發生事件
    #if x < 30:
        #event(uma)

def event(uma,cards):
    x = random.randint(1,100)
    #if x < 30: 
        #uma_event(uma)
    #else : 
        #card_event(cards)

        
def uma_event(uma,type):
    x = random.randint(1,100)
    if type == 0:#一般
        y = random.randint(1,100)
    elif type == 1:#外出
        candidates = [i for i, v in enumerate(uma.event3) if v != 1]
        if not candidates:
            print("所有位置都已經是 1，無法再選。")
            return
        chosen = random.choice(candidates)
        uma.event3[chosen] = 1

        if chosen == 0:
            while True:
                selection = input("選擇1 +10stamina 選擇2 +10 will\n")
                if selection == "1":
                    uma.add_stats("stamina",10)
                    break
                elif selection == "2":
                    uma.add_stats("will",10)
                    break
                else:
                    print("請重新輸入")

        if chosen == 1:
            while True:
                selection = input("選擇1 +10speed 選擇2 +10 power\n")
                if selection == "1":
                    uma.add_stats("speed",10)
                    break
                elif selection == "2":
                    uma.add_stats("power",10)
                    break
                else:
                    print("請重新輸入")
        if chosen == 2:
            while True:
                selection = input("選擇1 +10stamina 選擇2 +10 power 選擇3 +10will\n")
                if selection == "1":
                    uma.add_stats("stamina",10)
                    break
                elif selection == "2":
                    uma.add_stats("power",10)
                    break
                elif selection == "3":
                    uma.add_stats("will",10)
                    break
                else:
                    print("請重新輸入")
        if chosen == 3:
            while True:
                selection = input("選擇1 +10knowledge 選擇2 +10 will\n")
                if selection == "1":
                    uma.add_stats("knowledge",10)
                    break
                elif selection == "2":
                    uma.add_stats("will",10)
                    break
                else:
                    print("請重新輸入")
                
        if chosen == 4:
            while True:
                selection = input("選擇1 +10power 選擇2 +10 speed\n")
                if selection == "1":
                    uma.add_stats("power",10)
                    break
                elif selection == "2":
                    uma.add_stats("speed",10)
                    break
                else:
                    print("請重新輸入")
                
        





def card_event(cards):





        x=0
        
        
'''