import torch
import os
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from env import UmaEnv
from model import DDQNAgent
from eval import total_eval

def save_stats_to_file(episode, uma, score, rainbows, fails, filename):
    rb_names = ["速彩", "耐彩", "力彩", "根彩", "智彩"]
    rb_str = ", ".join([f"{n}:{rainbows[i]}" for i, n in enumerate(rb_names)])
    
    with open(filename, "a", encoding="utf-8") as f:
        log = (
            f"場次: {episode:04d} | "
            f"屬性: [速:{uma.speed:4d}, 耐:{uma.stamina:4d}, 力:{uma.power:4d}, 根:{uma.will:4d}, 智:{uma.knowledge:4d}] | "
            f"彩圈: [{rb_str}] | 失敗: {fails:2d} | 評分: {score:5d}\n"
        )
        f.write(log)

def generate_final_plots(history, timestamp, visual_dir, total_episodes):
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
    plt.rcParams['axes.unicode_minus'] = False
    
    step = max(1, total_episodes // 10)
    sample_indices = range(step - 1, len(history['score']), step)
    epochs = [i + 1 for i in sample_indices]

    plt.figure(figsize=(10, 6))
    plt.plot(epochs, [history['r_score'][i] for i in sample_indices], label='分數獎勵', color='b')
    plt.plot(epochs, [history['r_love'][i] for i in sample_indices], label='情誼獎勵', color='orange')
    plt.xlabel("Epoch")
    plt.ylabel("Reward Value")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(visual_dir, f"plot1_rewards_{timestamp}.png"))
    plt.close()

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()
    ax1.plot(epochs, [history['score'][i] for i in sample_indices], label='總評分', color='blue', alpha=0.6)
    ax2.plot(epochs, [sum(history['rainbows'][i]) for i in sample_indices], label='彩圈總數', color='green', marker='s', markersize=3)
    ax2.plot(epochs, [history['fail'][i] for i in sample_indices], label='失敗次數', color='red', marker='x', markersize=3)
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("評分")
    ax2.set_ylabel("次數")
    ax1.legend(loc='upper left'); ax2.legend(loc='upper right')
    plt.grid(True)
    plt.savefig(os.path.join(visual_dir, f"plot2_combined_{timestamp}.png"))
    plt.close()

    plt.figure(figsize=(10, 6))
    names = ["速彩", "耐彩", "力彩", "根彩", "智彩"]
    for idx, name in enumerate(names):
        plt.plot(epochs, [history['rainbows'][i][idx] for i in sample_indices], label=name)
    plt.xlabel("Epoch")
    plt.ylabel("次數")
    plt.legend(); plt.grid(True)
    plt.savefig(os.path.join(visual_dir, f"plot3_rainbow_detail_{timestamp}.png"))
    plt.close()

def main():
    print("有在開始訓練了")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir, model_dir, visual_dir = "train_log", "model", "visual"
    for d in [log_dir, model_dir, visual_dir]: os.makedirs(d, exist_ok=True)

    log_file = os.path.join(log_dir, f"train_log_{timestamp}.txt")
    model_file = os.path.join(model_dir, f"uma_ddqn_{timestamp}.pth")
    debug_file = os.path.join("train_log", f"last_episode_debug_{timestamp}.txt") 

    env = UmaEnv()
    agent = DDQNAgent(state_dim=25, action_dim=7)
    
    print(f"確認訓練設備: {agent.device}") 

    history = {'score': [], 'fail': [], 'rainbows': [], 'r_score': [], 'r_love': []}
    total_episodes = 1000 

    for i in range(1, total_episodes + 1):
        state = env.reset()
        done = False
        ep_score_r, ep_love_r = 0, 0
        
        is_target_ep = (i == 1000)
        debug_logs = []
        if is_target_ep:
            debug_logs.append(f"=== 第 {i} 場詳細養成日誌 ===\n")

        step_count = 1

        while not done:
            # 獲取動作前的狀態與 Q 值紀錄
            if is_target_ep:
                # 紀錄舊數值以計算變化量
                old_u = {
                    'speed': env.uma.speed, 'stamina': env.uma.stamina, 
                    'power': env.uma.power, 'will': env.uma.will, 
                    'knowledge': env.uma.knowledge, 'hp': env.uma.hp
                }
                old_card_loves = [c.love for c in env.cards]

                state_t = torch.FloatTensor(state).to(agent.device).unsqueeze(0)
                with torch.no_grad():
                    q_values = agent.q_eval(state_t).cpu().numpy()[0]
                
                u = env.uma
                pos_names = ["無", "速度", "耐力", "力量", "根性", "智慧"]
                action_names = ["速", "耐", "力", "根", "智", "休", "外"]
                full_action_names = ["速度訓練", "耐力訓練", "力量訓練", "意志訓練", "智慧訓練", "休息", "外出"]
                
                stats_str = f"速:{u.speed} 耐:{u.stamina} 力:{u.power} 根:{u.will} 智:{u.knowledge}"
                card_info_pre = [f"卡{idx+1}:{pos_names[c.now]}(情誼:{c.love})" for idx, c in enumerate(env.cards)]
                pos_counts = {k: 0 for k in range(6)}
                for c in env.cards:
                    pos_counts[c.now] += 1
                dist_str = ", ".join([f"{pos_names[k]}:{pos_counts[k]}人" for k in range(1, 6)])
                q_vals_str = " | ".join([f"{name}:{val:8.2f}" for name, val in zip(action_names, q_values)])
                
                log_entry_pre = (
                    f"回合 {step_count:02d} | 體力:{u.hp:3.1f} | 心情:{u.mood} | {stats_str}\n"
                    f"   分布情況: {dist_str}\n"
                    f"   各動作Q值: {q_vals_str}\n"
                    f"   支援卡位置: {', '.join(card_info_pre)}\n"
                    f"   AI 選擇動作: {full_action_names[agent.choose_action(state)]} (Eps: {agent.epsilon:.3f})\n"
                )

            action = agent.choose_action(state)
            next_state, reward, done, info = env.step(action)
            agent.store_transition(state, action, reward, next_state, done)
            agent.learn()

            if is_target_ep:
                # 計算數值變化
                u_new = env.uma
                diffs = {
                    '速': u_new.speed - old_u['speed'],
                    '耐': u_new.stamina - old_u['stamina'],
                    '力': u_new.power - old_u['power'],
                    '根': u_new.will - old_u['will'],
                    '智': u_new.knowledge - old_u['knowledge'],
                    '體': u_new.hp - old_u['hp']
                }
                diff_str = " ".join([f"{k}({v:+.0f})" for k, v in diffs.items() if v != 0])
                
                # 計算支援卡情誼變化
                love_diffs = []
                for idx, c in enumerate(env.cards):
                    l_diff = c.love - old_card_loves[idx]
                    if l_diff != 0:
                        love_diffs.append(f"卡{idx+1}({l_diff:+.0f})")
                love_diff_str = ", ".join(love_diffs) if love_diffs else "無變化"

                log_entry_post = (
                    f"   數值變化: {diff_str}\n"
                    f"   情誼變化: {love_diff_str}\n"
                    f"   單回獎勵 (Reward): {reward:+.2f}\n"
                    f"{'-'*60}\n"
                )
                debug_logs.append(log_entry_pre + log_entry_post)

            ep_score_r += info['r_score']
            ep_love_r += info['r_love']
            state = next_state
            step_count += 1

        if is_target_ep:
            with open(debug_file, "w", encoding="utf-8") as f:
                f.writelines(debug_logs)
                f.write(f"\n最終評分: {total_eval(env.uma)}\n")
            print(f"已輸出第 {i} 場詳細數據至: {debug_file}")

        final_score = total_eval(env.uma)
        history['score'].append(final_score)
        history['fail'].append(env.fail_count)
        history['rainbows'].append(env.rainbow_counts.copy())
        history['r_score'].append(ep_score_r)
        history['r_love'].append(ep_love_r)
        
        save_stats_to_file(i, env.uma, final_score, env.rainbow_counts, env.fail_count, log_file)
        
        if i % 10 == 0:
            print(f"場次 {i}/{total_episodes} | 評分: {final_score} | 失敗: {env.fail_count} | Eps: {agent.epsilon:.3f}")

        if i % 500 == 0:
            torch.save(agent.q_eval.state_dict(), model_file)

    generate_final_plots(history, timestamp, visual_dir, total_episodes)
    torch.save(agent.q_eval.state_dict(), model_file)

if __name__ == "__main__":
    main()