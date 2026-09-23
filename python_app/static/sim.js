/* アオハル盃・模擬沙盒 UI */
const $ = id => document.getElementById(id);
const STAT_KEYS = ["速", "耐", "力", "根", "智"];
let busy = false;
let HIST = [];
let LAST = null;

function gaugeBar(g, cap) {
  const n = Math.max(0, Math.min(cap, Math.round(g)));
  return "▮".repeat(n) + "▯".repeat(cap - n) + " " + g + "/" + cap;
}

function fmtNum(x) {
  return Math.floor(x);
}

function marksHtml(marks) {
  if (!marks) return "（無）";
  let h = "";
  for (let col = 0; col < 5; col++) {
    const g = (marks.guide && marks.guide[String(col)]) || [];
    const s = (marks.soul && marks.soul[String(col)]) || [];
    const sp = (marks.sp && marks.sp[String(col)]) || [];
    h += '<div><b style="color:var(--muted)">欄' + col + '</b>　' +
         '箭頭[' + g.map(i => "M" + i).join(",") + ']　' +
         '<span class="soul-txt">魂[' + s.map(i => "M" + i).join(",") + ']</span>　' +
         '<span class="burst">極[' + sp.map(i => "M" + i).join(",") + ']</span></div>';
  }
  return h || "（本回合無標記）";
}

function card(lbl, val, cls) {
  return '<div class="card"><div class="lbl">' + lbl + '</div><div class="val ' + (cls || "") + '">' + val + '</div></div>';
}

function escapeHtml(x) {
  return String(x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render(d) {
  LAST = d;
  $("modeLabel").textContent = d.mode === "live"
    ? "實戰繼承模式 (seed=" + d.seed + ")"
    : "全新模擬 (seed=" + d.seed + ")";

  const vitalPct = Math.round(d.stamina / d.maxVital * 100);
  $("statusRow").innerHTML =
    card("ターン", d.turn + (d.terminal ? " (終盤)" : ""), d.terminal ? "bad-txt" : "") +
    card("体力", fmtNum(d.stamina) + "/" + d.maxVital,
         vitalPct > 50 ? "ok-txt" : vitalPct > 25 ? "warn-txt" : "bad-txt") +
    card("調子", d.moodName + " (" + d.mood + "/6)", "") +
    card("スキルPt", fmtNum(d.skillPt), "") +
    card("チームランク", d.teamRank, "") +
    card("累計爆発", d.burstCount, d.burstCount >= 10 ? "ok-txt" : "") +
    '<div class="card"><div class="lbl">体力グラフ</div><div class="bar"><div class="fill" style="width:' +
      Math.min(100, vitalPct) +
      '%;background:' + (vitalPct > 50 ? "var(--ok)" : vitalPct > 25 ? "var(--warn)" : "var(--bad)") +
      '"></div></div><div style="font-size:.75em;color:var(--muted);margin-top:4px">育成馬 ' +
      STAT_KEYS.map((k, i) => k + fmtNum(d.stats[i])).join("/") + "</div></div>";

  const legal = new Set(d.legal || []);
  $("colGrid").innerHTML = d.columns.map(col => {
    const t = +col.t;
    const clickable = legal.has(t) && !d.terminal;
    const failCls = col.fail < 10 ? "ok-txt" : col.fail < 20 ? "warn-txt" : "bad-txt";
    let h = '<div class="col ' + (clickable ? "clickable" : "disabled") + '" data-t="' + t + '">';
    h += '<div class="chead"><span class="tname">' + col.name + '訓練</span><span class="tlv">Lv' + col.level + '</span></div>';
    h += '<div class="cfail">失敗率 <span class="f ' + failCls + '">' + col.fail +
         '%</span>　体力 <span class="' + (col.cost > 0 ? "ok-txt" : "bad-txt") + '">' +
         (col.cost > 0 ? "+" : "") + col.cost + "</span></div>";
    const gain = (col.gain || []).map(v => Math.max(0, Math.floor(v)));
    const gparts = [];
    STAT_KEYS.forEach((k, i) => { if (gain[i]) gparts.push(k + "+" + gain[i]); });
    if (col.skillPt) gparts.push("SP+" + Math.max(0, Math.floor(col.skillPt)));
    if (col.cost) gparts.push("体" + (col.cost > 0 ? "+" : "") + col.cost);
    h += '<div class="cprev">成功時　' + (gparts.length ? gparts.join("　") : "―") + "</div>";
    if (col.attending.length) h += '<div class="mat">出席: ' + col.attending.join("、") + "</div>";
    const chips = [];
    for (const a of col.arrows) {
      chips.push('<span class="chip ' + (a.arrow ? "arrow" : "") + '">' +
                 (a.arrow ? "→" : "") + "M" + a.idx + " " + a.name + " " + gaugeBar(a.gauge, a.gaugeMax) +
                 '<br><span style="color:var(--muted)">' + a.stage + "</span></span>");
    }
    for (const i of col.soul) chips.push('<span class="chip soul">●魂爆 M' + i + "</span>");
    for (const i of col.sp) chips.push('<span class="chip sp">★極爆 M' + i + "</span>");
    if (chips.length) h += '<div class="chips">' + chips.join("") + "</div>";
    h += "</div>";
    return h;
  }).join("");

  $("actRow").innerHTML = [5, 6, 7].map(a => {
    const on = legal.has(a) && !d.terminal;
    return '<button class="btn act ' + (a === 5 ? "gray" : a === 7 ? "ok" : "") +
           '" data-a="' + a + '" ' + (on ? "" : "disabled") + ">" +
           ({5: "休息", 6: "外出", 7: "比賽→"}[a]) + "</button>";
  }).join("");

  $("memberTable").innerHTML = d.members.length
    ? '<table><tr><th></th><th>名前</th><th>屬</th><th>渦</th><th>狀態</th><th>情誼</th><th>能力</th></tr>' +
      d.members.map(m => {
        const st = m.stage;
        const mark = st === "極爆済" ? '<span class="burst">極爆済</span>' :
                     st === "魂爆済" ? '<span class="soul-txt">魂爆済</span>' :
                     '<span style="color:var(--muted)">未爆</span>';
        const bond = m.isNpc ? '<span style="color:var(--muted)">—</span>' : (m.bond || 0);
        return "<tr><td>M" + m.idx + "</td><td>" + m.name + "</td><td>" + STAT_KEYS[m.type] +
               '</td><td style="font-size:.78em">' + gaugeBar(m.gauge, m.gaugeMax) +
               "</td><td>" + mark + "</td><td>" + bond + "</td><td>" +
               STAT_KEYS.map((k, i) => k + fmtNum(m.stat[i])).join(" ") + "</td></tr>";
      }).join("") + "</table>"
    : "（無部活成員）";

  $("cardTable").innerHTML = (d.cards || []).length
    ? '<table><tr><th></th><th>支援カード</th><th>型</th><th>情誼</th><th>渦</th><th>狀態</th><th>彩圈</th></tr>' +
      d.cards.map(c => {
        const ready = c.shining;
        const mark = c.stage === "魂爆済"
          ? '<span class="soul-txt">魂爆済</span>'
          : '<span style="color:var(--muted)">未爆</span>';
        const col = '<span class="chip ' + (ready ? "sp" : "") + '">' +
                    (ready ? "◎ " + c.type + "欄" : "‑") + "</span>";
        return "<tr><td>カード" + c.idx + "</td><td>" + escapeHtml(c.name) +
               "</td><td>" + c.type + "</td><td>" + (c.bond || 0) + "</td><td>" +
               gaugeBar(c.gauge, 5) + "</td><td>" + mark + "</td><td>" + col + "</td></tr>";
      }).join("") + "</table>"
    : "（無支援卡）";

  $("simMarks").innerHTML = marksHtml(d.marks);
  const lv = d.live;
  $("liveMarks").innerHTML = lv
    ? '<div class="live-chip">実戦 turn=' + lv.turn + '</div>' + marksHtml(lv)
    : "（無 watcher 實戰資料）";

  if (d.terminal) {
    $("noteBox").innerHTML = '<div class="note">育成終盤。最終五圍 ' +
      STAT_KEYS.map((k, i) => k + fmtNum(d.stats[i])).join("/") +
      "　スキルPt " + fmtNum(d.skillPt) + "　累計爆発 " + d.burstCount + "</div>";
  }
}

function showHistory() {
  $("history").innerHTML = HIST.map(h =>
    '<div class="hist-line"><span class="t">T' + h.turn + " " + h.name + "</span><br>" +
    h.lines.map(l => l.indexOf("爆発") >= 0
      ? '<span class="burst">' + escapeHtml(l) + "</span>"
      : escapeHtml(l)).join("<br>") + "</div>"
  ).join("") || "（尚無行動）";
}

function post(body) {
  if (busy) return;
  busy = true;
  document.querySelectorAll(".btn").forEach(b => b.disabled = true);
  fetch("/api/sim/action", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})
    .then(r => r.json())
    .then(d => {
      if (d.state) {
        render(d.state);
        if (body.action != null) {
          HIST.unshift(d.outcome);
          HIST = HIST.slice(0, 40);
        } else {
          HIST = [];
        }
        showHistory();
      }
      if (d.ok === false) {
        $("noteBox").innerHTML = '<div class="note">' + (d.msg || "錯誤") + "</div>";
      } else {
        $("noteBox").innerHTML = "";
      }
    })
    .catch(e => { $("noteBox").innerHTML = '<div class="note">Error: ' + e + "</div>"; })
    .finally(() => { busy = false; reenable(); });
}

function reenable() {
  if (!LAST) return;
  const legal = new Set(LAST.legal || []);
  document.querySelectorAll("button[data-a]").forEach(b => {
    b.disabled = !legal.has(+b.dataset.a) || LAST.terminal;
  });
  document.querySelectorAll(".col[data-t]").forEach(c => {
    const on = legal.has(+c.dataset.t) && !LAST.terminal;
    c.classList.toggle("clickable", on);
    c.classList.toggle("disabled", !on);
  });
}

function refresh() {
  if (busy) return;
  busy = true;
  fetch("/api/sim/state")
    .then(r => r.json())
    .then(d => { if (d.ok) render(d); })
    .catch(e => { $("noteBox").innerHTML = '<div class="note">Error: ' + e + "</div>"; })
    .finally(() => { busy = false; });
}

function reset(mode) {
  const body = {reset: true, mode: mode};
  if (mode === "fresh") {
    const seedText = $("seedInput").value.trim();
    if (seedText) body.seed = parseInt(seedText);
  }
  post(body);
}

document.addEventListener("click", e => {
  const col = e.target.closest(".col.clickable");
  if (col) post({action: +col.dataset.t});
  const btn = e.target.closest("button[data-a]");
  if (btn && !btn.disabled) post({action: +btn.dataset.a});
});
$("freshBtn").addEventListener("click", () => reset("fresh"));
$("liveBtn").addEventListener("click", () => reset("live"));
$("refreshBtn").addEventListener("click", refresh);

document.addEventListener("keydown", e => {
  const a = parseInt(e.key);
  if (!isNaN(a) && a >= 0 && a <= 7) {
    const col = document.querySelector('.col.clickable[data-t="' + a + '"]');
    const btn = document.querySelector('button[data-a="' + a + '"]');
    const el = (a <= 4 ? col : btn);
    if (el && !el.disabled) el.click();
  }
});

refresh();