let ready = false;
let lastTurn = null;
let busy = false;
let pendingRecommend = false;
const $ = id => document.getElementById(id);

function pollState() {
  fetch("/api/state")
    .then(r => r.json())
    .then(d => {
      $("dot").className = d.ready ? "dot on" : "dot";
      ready = d.ready;
      $("runBtn").disabled = !ready || busy;
      if (!d.ready) {
        $("stateContent").innerHTML = '<div class="loading">' + (d.msg || "等待遊戲連線…") + '</div>';
        $("turnLabel").textContent = "—";
        return;
      }
      renderState(d);
      const scn = d.scenario ? "  [" + d.scenario + "]" : "";
      $("turnLabel").textContent = "Turn " + (d.turn || "—") + scn + "  " + (d.uma_name || "") + "  " + (d.motivation || "");
      if (d.turn != null && d.turn !== lastTurn) {
        lastTurn = d.turn;
        requestRecommend();
      }
    })
    .catch(() => {});
}

function renderState(d) {
  let h = "";
  const vitalPct = d.vital != null && d.max_vital ? Math.round(d.vital / d.max_vital * 100) : 0;
  const vitalCls = vitalPct > 50 ? "good" : vitalPct > 25 ? "warn" : "bad";

  // Stats
  h += '<div class="stat-grid">';
  const stats = d.status || {};
  for (const [k, label] of [["speed","Speed"],["stamina","Stamina"],["power","Power"],["guts","Guts"],["wiz","Wiz"]]) {
    const v = stats[k] || 0;
    const cls = v >= 800 ? "good" : v >= 500 ? "" : "warn";
    h += '<div class="stat-row"><span class="label">' + label + '</span><span class="value ' + cls + '">' + v + '</span></div>';
  }
  h += '<div class="stat-row"><span class="label">Vital</span><span class="value ' + vitalCls + '">' + (d.vital||0) + '/' + (d.max_vital||0) + '</span></div>';
  h += '<div class="stat-row"><span class="label">Skill Pt</span><span class="value">' + (d.skill_point||0) + '</span></div>';
  h += '</div>';

  // Vital bar
  h += '<div style="margin-top:12px"><div style="color:var(--muted);font-size:.85em;margin-bottom:4px">Vital</div>';
  h += '<div class="status-bar"><div class="fill" style="width:' + vitalPct + '%;background:' + (vitalPct>50?"var(--ok)":vitalPct>25?"var(--warn)":"var(--bad)") + '"></div></div></div>';

  // Bonds
  h += '<div style="margin-top:16px"><div style="color:var(--muted);font-size:.85em;margin-bottom:6px">Bond</div>';
  h += '<div class="bond-grid">';
  const sc = d.support_cards || [];
  const bonds = d.bonds || {};
  for (let i = 1; i <= 6; i++) {
    const b = bonds[String(i)] || 0;
    const card = (d.deck || [])[i - 1];
    const name = card ? card.name.substring(0, 4) : "Card" + i;
    const cls = b >= 100 ? "bnum good" : b >= 80 ? "bnum" : "bnum warn";
    h += '<div class="bond-card' + (b >= 100 ? ' max' : '') + '"><div class="' + cls + '">' + b + '</div><div class="bname">' + name + '</div></div>';
  }
  h += '</div></div>';

  // Panel (commands)
  if (d.panel && d.panel.length) {
    h += '<div style="margin-top:16px"><div style="color:var(--muted);font-size:.85em;margin-bottom:6px">Commands</div>';
    h += '<div class="cmd-list">';
    for (const cmd of d.panel) {
      if (cmd.command_type !== 1) continue; // only show training
      const fail = cmd.failure_rate || 0;
      const failCls = fail < 10 ? "good" : fail < 20 ? "warn" : "bad";
      const enabled = cmd.is_enable !== false;
      const partners = (cmd.partners || []).length;
      h += '<div class="cmd-item' + (enabled ? '' : ' disabled') + '">';
      h += '<span class="name">' + cmd.action_name + '</span>';
      h += '<span class="detail">Lv' + (cmd.level||'?') + '  +' + partners + '人</span>';
      h += '<span class="fail ' + failCls + '">' + fail + '%</span>';
      h += '</div>';
    }
    h += '</div></div>';
  }

  $("stateContent").innerHTML = h;
}

function applyPreset() {
  const PRESETS = {
    balance: [1.0, 1.0, 1.0, 1.0, 1.0],
    speed: [1.8, 0.8, 1.0, 0.8, 1.0],
    speedstamina: [1.5, 1.5, 0.8, 0.8, 1.0],
    power: [1.2, 1.0, 1.6, 1.0, 1.0],
    wiz: [1.2, 0.9, 0.9, 0.9, 1.5],
  };
  const v = PRESETS[$("presetSel").value] || PRESETS.balance;
  ["Speed", "Stamina", "Power", "Guts", "Wiz"].forEach((k, i) => { $("w" + k).value = v[i]; });
}

function readStrategy() {
  return {
    weight: [
      parseFloat($("wSpeed").value) || 1.0,
      parseFloat($("wStamina").value) || 1.0,
      parseFloat($("wPower").value) || 1.0,
      parseFloat($("wGuts").value) || 1.0,
      parseFloat($("wWiz").value) || 1.0,
    ],
    skill: parseFloat($("wSkill").value) || 1.0,
  };
}

function requestRecommend() {
  if (busy) { pendingRecommend = true; return; }
  runRecommend();
}

function runRecommend() {
  if (busy) { pendingRecommend = true; return; }
  busy = true;
  pendingRecommend = false;
  $("runBtn").disabled = true;
  $("mctsContent").innerHTML = '<div class="loading">MCTS 計算中…</div>';

  const body = {
    iterations: parseInt($("iterInput").value) || 5000,
    exploration: parseFloat($("cInput").value) || 1.4,
    strategy: readStrategy(),
  };
  const seed = $("seedInput").value.trim();
  if (seed) body.seed = parseInt(seed);

  fetch("/api/recommend", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})
    .then(r => r.json())
    .then(d => {
      if (!d.ready) {
        $("mctsContent").innerHTML = '<div class="loading">' + (d.msg || "等待遊戲連線…") + '</div>';
        return;
      }
      renderRecommend(d);
    })
    .catch(e => {
      $("mctsContent").innerHTML = '<div class="note">Error: ' + e + '</div>';
    })
    .finally(() => {
      busy = false;
      $("runBtn").disabled = !ready;
      if (pendingRecommend) requestRecommend();
    });
}

document.addEventListener("keydown", e => {
  if (e.ctrlKey && e.shiftKey && (e.key === "R" || e.key === "r")) {
    e.preventDefault();
    requestRecommend();
  }
});

function renderRecommend(d) {
  let h = "";
  if (d.best_name) {
    h += '<div style="font-size:1.3em">建議: <strong style="color:var(--ok)">' + d.best_name + '</strong></div>';
  } else {
    h += '<div class="loading">無候選</div>';
  }
  $("mctsContent").innerHTML = h;
}

setInterval(pollState, 1000);
pollState();