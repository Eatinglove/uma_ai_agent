import torch
import torch.nn as nn
import torch.optim as optim
import random
import numpy as np
from collections import deque

class QNetwork(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(QNetwork, self).__init__()
        self.fc = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )
    def forward(self, x): return self.fc(x)

class DDQNAgent:
    def __init__(self, state_dim, action_dim):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.q_eval = QNetwork(state_dim, action_dim).to(self.device)
        self.q_target = QNetwork(state_dim, action_dim).to(self.device)
        self.q_target.load_state_dict(self.q_eval.state_dict())
        
        self.optimizer = optim.Adam(self.q_eval.parameters(), lr=0.0003)
        self.memory = deque(maxlen=20000)
        self.batch_size = 64
        self.gamma = 0.99
        self.epsilon = 1.0  
        self.eps_dec = 0.99995
        self.eps_min = 0.05
        self.action_dim = action_dim
        self.learn_step_counter = 0

    def store_transition(self, s, a, r, s_, done):
        self.memory.append((s, a, r, s_, done))

    def choose_action(self, state):
        if np.random.random() > self.epsilon:
            state_t = torch.tensor(state, dtype=torch.float32).to(self.device).unsqueeze(0)
            actions = self.q_eval(state_t)
            return torch.argmax(actions).item()
        return np.random.randint(self.action_dim)

    def learn(self):
        if len(self.memory) < self.batch_size: return

        if self.learn_step_counter % 500 == 0:
            self.q_target.load_state_dict(self.q_eval.state_dict())

        batch = random.sample(self.memory, self.batch_size)
        s, a, r, s_, done = zip(*batch)

        s = torch.tensor(np.array(s)).to(self.device)
        a = torch.tensor(a).unsqueeze(1).to(self.device)
        r = torch.tensor(r, dtype=torch.float32).unsqueeze(1).to(self.device)
        s_ = torch.tensor(np.array(s_)).to(self.device)
        done = torch.tensor(done, dtype=torch.float32).unsqueeze(1).to(self.device)

        q_eval = self.q_eval(s).gather(1, a)
        next_actions = torch.argmax(self.q_eval(s_), dim=1, keepdim=True)
        q_next = self.q_target(s_).gather(1, next_actions)
        q_target = r + self.gamma * q_next * (1 - done)

        loss = nn.MSELoss()(q_eval, q_target.detach())
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        self.epsilon = max(self.eps_min, self.epsilon * self.eps_dec)
        self.learn_step_counter += 1