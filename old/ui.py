from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QSizePolicy
)
from PyQt5.QtCore import Qt
from train import TRAIN_PREVIEWS, TRAIN_APPLIES
from card import card_random
from eval import total_eval

MAX_ROUND = 60


def stat_score(value):
    table = [
        (100, 66), (200, 181), (300, 352), (400, 577),
        (500, 847), (600, 1143), (700, 1463), (800, 1808),
        (900, 2209), (1000, 2635), (1100, 3171), (1200, 3841)
    ]
    score = 0
    for limit, val in table:
        if value >= limit:
            score = val
        else:
            break
    return score


class UmaUI(QWidget):
    def __init__(self, uma, cards, step_function=None):
        super().__init__()
        self.uma = uma
        self.cards = cards
        self.step_function = step_function

        self.round = 1

        self.setWindowTitle("賽馬娘訓練 UI")
        self.setGeometry(50, 50, 900, 650)

        self.lvl_tracker = {i: 1 for i in range(1, 6)}
        self.click_tracker = {i: 0 for i in range(1, 6)}

        main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()

        stats_layout = QVBoxLayout()
        self.stats_box = QTextEdit()
        self.stats_box.setReadOnly(True)
        self.stats_box.setFixedHeight(280)
        stats_layout.addWidget(QLabel("馬娘狀態"))
        stats_layout.addWidget(self.stats_box)
        top_layout.addLayout(stats_layout)

        cards_layout = QVBoxLayout()
        self.cards_box = QTextEdit()
        self.cards_box.setReadOnly(True)
        self.cards_box.setFixedHeight(280)
        cards_layout.addWidget(QLabel("卡片資訊"))
        cards_layout.addWidget(self.cards_box)
        top_layout.addLayout(cards_layout)

        main_layout.addLayout(top_layout)

        bottom_layout = QVBoxLayout()

        self.round_label = QLabel()
        self.round_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.round_label)

        self.score_label = QLabel()
        self.score_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.score_label)

        self.preview_boxes = {}
        self.buttons = {}

        action_names = {1: "速度", 2: "耐力", 3: "力量", 4: "意志", 5: "智慧"}

        for action_id in range(1, 6):
            h_layout = QHBoxLayout()

            btn = QPushButton(action_names[action_id])
            btn.setFixedWidth(100)
            btn.setFixedHeight(35)
            btn.clicked.connect(lambda _, a=action_id: self.apply_action(a))
            h_layout.addWidget(btn)
            self.buttons[action_id] = btn

            preview_box = QTextEdit()
            preview_box.setReadOnly(True)
            preview_box.setFixedHeight(90)
            h_layout.addWidget(preview_box)
            self.preview_boxes[action_id] = preview_box

            bottom_layout.addLayout(h_layout)

        h_layout2 = QHBoxLayout()
        for action_id, name in zip([6, 7, 8], ["休息", "外出", "離開"]):
            btn = QPushButton(name)
            btn.setFixedHeight(35)
            btn.clicked.connect(lambda _, a=action_id: self.apply_action(a))
            h_layout2.addWidget(btn)
            self.buttons[action_id] = btn
        bottom_layout.addLayout(h_layout2)

        event_layout = QHBoxLayout()
        self.event_buttons = []
        for _ in range(3):
            btn = QPushButton("")
            btn.setEnabled(False)
            btn.setFixedHeight(35)
            event_layout.addWidget(btn)
            self.event_buttons.append(btn)

        bottom_layout.addLayout(event_layout)

        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

        self.update_view()
        self.update_all_previews()
        self.show()

    def update_view(self):
        self.round_label.setText(f"Round {self.round} / {MAX_ROUND}")

        total_score = total_eval(self.uma)

        self.score_label.setText(f"目前評分總和：{total_score}")

        s = (
            f"speed: {self.uma.speed}\n"
            f"stamina: {self.uma.stamina}\n"
            f"power: {self.uma.power}\n"
            f"will: {self.uma.will}\n"
            f"knowledge: {self.uma.knowledge}\n"
            f"hp: {self.uma.hp}\n"
            f"mood: {self.uma.mood}\n\n"
        )

        s += "訓練設施等級:\n"
        for tid, lvl in self.lvl_tracker.items():
            name = {1: "速度", 2: "耐力", 3: "力量", 4: "意志", 5: "智慧"}[tid]
            s += f"{name}: {lvl}\n"

        self.stats_box.setText(s)

        text = ""
        position_name = {0: "無", 1: "速度", 2: "耐力", 3: "力量", 4: "意志", 5: "智慧"}
        for i, card in enumerate(self.cards, start=1):
            text += f"Card {i}: 在 {position_name[card.now]} | 情誼 {card.love}\n"
        self.cards_box.setText(text)

    def show_preview(self, action_id):
        if action_id not in TRAIN_PREVIEWS:
            return

        lvl = min(self.lvl_tracker[action_id], 5)
        delta = TRAIN_PREVIEWS[action_id](self.uma, self.cards, lvl)

        text = ""
        for k, v in delta.items():
            if k != "details":
                cur = getattr(self.uma, k)
                text += f"{k}: {cur} → {cur + v} (+{v})\n"

        self.preview_boxes[action_id].setText(text)

    def apply_action(self, action_id):
        if self.round >= MAX_ROUND:
            return

        if action_id in TRAIN_APPLIES:
            success = TRAIN_APPLIES[action_id](self.uma, self.cards, self.lvl_tracker[action_id])
            if success:
                self.click_tracker[action_id] += 1
                if self.click_tracker[action_id] >= 4:
                    self.lvl_tracker[action_id] = min(5, self.lvl_tracker[action_id] + 1)
                    self.click_tracker[action_id] = 0
        elif action_id == 6:
            self.uma.rest()
        elif action_id == 7:
            self.uma.go_out()
        elif action_id == 8:
            self.close()
            return

        card_random(self.cards)
        self.round += 1

        if self.round >= MAX_ROUND:
            for btn in self.buttons.values():
                btn.setEnabled(False)

        self.update_view()
        self.update_all_previews()

    def update_all_previews(self):
        for action_id in range(1, 6):
            self.show_preview(action_id)
