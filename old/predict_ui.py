import sys
import torch
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox
from model import QNetwork 

class MyUmaUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("預測工具")
        self.setGeometry(100, 100, 1200, 900) 

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = QNetwork(state_dim=25, action_dim=7).to(self.device)
        try:
            self.model.load_state_dict(torch.load("model/uma_ddqn_20260506_103418.pth", map_location=self.device))
            self.model.eval()
        except Exception as e:
            print(f"模型載入失敗: {e}")

        self.layout = QVBoxLayout()

        self.intro = QLabel("請輸入各項數值", self)
        self.intro.move(550,50)
        self.intro.resize(200, 50)
        self.predict = QPushButton("預測", self)
        self.predict.move(550,800)
        self.predict.clicked.connect(self.predictMove)

        self.error_label = QLabel("", self)
        self.error_label.move(500, 850)
        self.error_label.resize(400, 30)
        self.error_label.setStyleSheet("color: red; font-weight: bold;")

        self.inputs = {}
    
        self.base_stats_names = ["速度", "耐力", "力量", "根性", "智慧", "體力HP", "心情", "目前回合"]
        self.levels_names = ["速等級", "耐等級", "力等級", "根等級", "智等級"]
        self.card_pos_names = [f"卡片{i+1}位置" for i in range(6)]
        self.card_love_names = [f"卡片{i+1}情誼" for i in range(6)]

        self.create_group(self.base_stats_names, 150, 200)
        self.create_group(self.levels_names, 400, 200)
        self.create_group(self.card_pos_names, 650, 200, is_combo=True)
        self.create_group(self.card_love_names, 900, 200)

        self.btn_default = QPushButton("填入預設值", self)
        self.btn_default.move(700, 800) 
        self.btn_default.resize(100, 40)
        self.btn_default.clicked.connect(self.set_default_values) 

    def create_group(self, name_list, start_x, start_y, is_combo=False):
        for i, name in enumerate(name_list):
            lbl = QLabel(name + ":", self)
            lbl.move(start_x, start_y + i * 40)
            
            if is_combo:
                box = QComboBox(self)
                box.addItems(["未出現", "速度", "耐力", "力量", "意志力", "智力"])
                box.move(start_x + 80, start_y + i * 40)
                box.setFixedWidth(100)
                self.inputs[name] = box
            else:
                edit = QLineEdit(self)
                edit.setPlaceholderText(name)
                edit.move(start_x + 80, start_y + i * 40)
                edit.setFixedWidth(100)
                self.inputs[name] = edit

    def predictMove(self):
        self.error_label.setText("") 
        self.error_label.setStyleSheet("color: red; font-weight: bold;")
        
        try:
            speed = float(self.inputs["速度"].text())
            stamina = float(self.inputs["耐力"].text())
            power = float(self.inputs["力量"].text())
            will = float(self.inputs["根性"].text())
            knowledge = float(self.inputs["智慧"].text())
            
            hp = float(self.inputs["體力HP"].text())
            if not (0 <= hp <= 120):
                self.error_label.setText("錯誤：體力必須在 0 到 120 之間！")
                return

            mood = float(self.inputs["心情"].text())
            if not (1 <= mood <= 5): 
                self.error_label.setText("錯誤：心情必須在 1 到 5 之間！")
                return

            round_num = float(self.inputs["目前回合"].text())
            if not (1 <= round_num <= 75):
                self.error_label.setText("錯誤：回合數必須在 1 到 75 之間！")
                return

            lvls = []
            for n in self.levels_names:
                val = float(self.inputs[n].text())
                if not (1 <= val <= 5): 
                    self.error_label.setText(f"錯誤：{n} 必須在 1 到 5 之間！")
                    return
                lvls.append(val / 5)

            loves = []
            for n in self.card_love_names:
                val = float(self.inputs[n].text())
                if not (0 <= val <= 100): 
                    self.error_label.setText(f"錯誤：{n} 必須在 0 到 100 之間！")
                    return
                loves.append(val / 100)

            obs = [
                speed / 1200, stamina / 1200, power / 1200, 
                will / 1200, knowledge / 1200,
                hp / 100, mood / 5, round_num / 60
            ]
            obs += lvls
            
            pos_map = {"未出現": 0, "速度": 1, "耐力": 2, "力量": 3, "意志力": 4, "智力": 5}
            for n in self.card_pos_names:
                txt = self.inputs[n].currentText()
                obs.append(pos_map[txt] / 5)
            
            obs += loves

            state_t = torch.tensor(obs, dtype=torch.float32).to(self.device).unsqueeze(0)
            with torch.no_grad():
                actions = self.model(state_t)
                action_id = torch.argmax(actions).item()

            action_names = ["速度訓練", "耐力訓練", "力量訓練", "意志訓練", "智慧訓練", "休息", "外出"]
            self.error_label.setStyleSheet("color: blue; font-weight: bold;")
            self.error_label.setText(f"AI 建議動作：{action_names[action_id]}")

        except ValueError:
            self.error_label.setText("錯誤：請填寫所有欄位且必須為有效數字！")
        except Exception as e:
            self.error_label.setText(f"發生錯誤: {str(e)}")
        
    def set_default_values(self):
        for name, widget in self.inputs.items():
            if isinstance(widget, QLineEdit):
                if "等級" in name or name == "目前回合" or name == "心情":
                    widget.setText("1")
                else:
                    widget.setText("100") 
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
        
        self.error_label.setText("已填入預設數值")
        self.error_label.setStyleSheet("color: green; font-weight: bold;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyUmaUI()
    window.show()
    sys.exit(app.exec_())