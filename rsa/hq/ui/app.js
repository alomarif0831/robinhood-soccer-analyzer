/* Robinhood Soccer HQ - single-page UI. Talks to the local API in rsa/hq/server.py. */
(function () {
  "use strict";
  const $ = (sel, el) => (el || document).querySelector(sel);
  const state = {
    view: "dashboard", source: "live", info: null, report: null, picks: null, matches: null, job: null,
    updates: null, selected: null, filter: { league: "", q: "", result: "" }, settingsDraft: null, activityOpen: false,
    loading: {},
  };
  const TABS = [["dashboard", "Dashboard"], ["picks", "Picks"], ["backtest", "Backtest"], ["matches", "Matches"], ["settings", "Settings"]];

  // ---------------------------------------------------------------- utils
  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || (r.status + " " + r.statusText));
    return data;
  }
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const fmtPct = (v, d = 1, sign = false) => (isNum(v) ? ((sign && v > 0 ? "+" : "") + (v * 100).toFixed(d) + "%") : "–");
  const fmtNum = (v, d = 3) => (isNum(v) ? v.toFixed(d) : "–");
  const fmtMoney = (v) => (isNum(v) ? "$" + v.toFixed(2) : "–");
  const fmtInt = (v) => (isNum(v) ? String(Math.round(v)) : "–");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function timeAgo(ts) {
    if (!ts) return "never";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  const fmtKick = (iso) => {
    if (!iso) return "–";
    const d = new Date(iso);
    return isNaN(d) ? esc(iso) : d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const cls = (v) => (isNum(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "");
  const badge = (tier) => `<span class="badge ${esc(tier || "neutral")}">${esc(tier || "–")}</span>`;
  const scorebar = (v) => `<span class="scorebar" title="${fmtNum(v, 1)}"><i style="width:${Math.max(0, Math.min(100, v || 0))}%"></i></span> <span class="num small">${fmtNum(v, 0)}</span>`;
  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }
  function table(cols, rows, opts) {
    opts = opts || {};
    if (!rows || !rows.length) return `<div class="muted small mb">${esc(opts.empty || "No data.")}</div>`;
    const head = cols.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
    const body = rows.map((r, i) => `<tr class="${opts.onRow ? "click" : ""}" data-i="${i}">` +
      cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join("") + "</tr>").join("");
    return `<div class="tablewrap"><table class="hq"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }
  const pct = (key, sign) => ({ key, label: key.replace(/_/g, " "), num: true, render: (r) => `<span class="${sign ? cls(r[key]) : ""}">${fmtPct(r[key], 1, sign)}</span>` });
  const num = (key, d, label) => ({ key, label: label || key.replace(/_/g, " "), num: true, render: (r) => fmtNum(r[key], d == null ? 3 : d) });
  const txt = (key, label) => ({ key, label: label || key.replace(/_/g, " ") });

  // ---------------------------------------------------------------- charts (inline SVG)
  function svgWrap(inner, w, h) { return `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">${inner}</svg>`; }
  function reliabilityChart(cal) {
    if (!cal || !cal.length) return "";
    const w = 520, h = 260, pad = { l: 40, r: 10, t: 10, b: 30 }, W = w - pad.l - pad.r, H = h - pad.t - pad.b;
    const x = (v) => pad.l + v * W, y = (v) => pad.t + (1 - v) * H;
    let s = `<line class="axis" x1="${pad.l}" y1="${y(0)}" x2="${x(1)}" y2="${y(0)}"/><line class="axis" x1="${pad.l}" y1="${y(0)}" x2="${pad.l}" y2="${y(1)}"/>`;
    s += `<line class="diag" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/>`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) s += `<text x="${x(t)}" y="${h - 8}" text-anchor="middle">${t}</text><text x="${pad.l - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`;
    for (const b of cal) {
      if (!isNum(b.mean_price) || !isNum(b.hit_rate)) continue;
      const r = 4 + Math.min(10, Math.sqrt(b.n || 1));
      const se = isNum(b.se) ? b.se : 0;
      s += `<line class="ci" x1="${x(b.mean_price)}" y1="${y(Math.min(1, b.hit_rate + 1.96 * se))}" x2="${x(b.mean_price)}" y2="${y(Math.max(0, b.hit_rate - 1.96 * se))}"/>`;
      s += `<circle cx="${x(b.mean_price)}" cy="${y(b.hit_rate)}" r="${r}" class="bar ${b.diff > 0 ? "pos" : "neg"}" opacity=".85"><title>${esc(b.bin)}: paid ${fmtNum(b.mean_price)}, won ${fmtNum(b.hit_rate)} (n=${b.n})</title></circle>`;
    }
    s += `<text x="${x(0.5)}" y="${h - 20}" text-anchor="middle">price paid</text><text transform="translate(12 ${y(0.5)}) rotate(-90)" text-anchor="middle">hit rate</text>`;
    return svgWrap(s, w, h);
  }
  function barChart(items, opts) {
    // items: [{label, value, lo, hi, n}]; value in fraction (ROI) unless opts.raw
    opts = opts || {};
    if (!items || !items.length) return "";
    const w = 520, h = 240, pad = { l: 44, r: 10, t: 10, b: 40 }, W = w - pad.l - pad.r, H = h - pad.t - pad.b;
    const vals = items.flatMap((i) => [i.value, isNum(i.lo) ? i.lo : i.value, isNum(i.hi) ? i.hi : i.value]).filter(isNum);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    if (hi - lo < 1e-9) hi = lo + 1;
    lo -= (hi - lo) * 0.05; hi += (hi - lo) * 0.05;
    const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * H;
    const bw = W / items.length;
    let s = `<line class="axis" x1="${pad.l}" y1="${y(0)}" x2="${w - pad.r}" y2="${y(0)}"/>`;
    for (const t of [lo, 0, hi]) s += `<text x="${pad.l - 6}" y="${y(t) + 4}" text-anchor="end">${opts.raw ? t.toFixed(2) : (t * 100).toFixed(0) + "%"}</text>`;
    items.forEach((it, i) => {
      if (!isNum(it.value)) return;
      const x0 = pad.l + i * bw + bw * 0.15, bwid = bw * 0.7;
      const y0 = Math.min(y(0), y(it.value)), hgt = Math.abs(y(0) - y(it.value));
      s += `<rect class="bar ${it.value >= 0 ? "pos" : "neg"}" x="${x0}" y="${y0}" width="${bwid}" height="${Math.max(1, hgt)}"><title>${esc(it.label)}: ${opts.raw ? it.value.toFixed(3) : fmtPct(it.value, 1, true)}${it.n ? " (n=" + it.n + ")" : ""}</title></rect>`;
      if (isNum(it.lo) && isNum(it.hi)) s += `<line class="ci" x1="${x0 + bwid / 2}" y1="${y(it.hi)}" x2="${x0 + bwid / 2}" y2="${y(it.lo)}"/>`;
      s += `<text x="${x0 + bwid / 2}" y="${h - 12}" text-anchor="middle">${esc(it.label)}</text>`;
    });
    return svgWrap(s, w, h);
  }
  function lineChart(series, opts) {
    // series: [{name, points:[{x,y}], alt}] ; y as fraction
    opts = opts || {};
    const pts = series.flatMap((s) => s.points).filter((p) => isNum(p.x) && isNum(p.y));
    if (!pts.length) return "";
    const w = 520, h = 220, pad = { l: 44, r: 10, t: 10, b: 30 }, W = w - pad.l - pad.r, H = h - pad.t - pad.b;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const xlo = Math.min(...xs), xhi = Math.max(...xs); let ylo = Math.min(0, ...ys), yhi = Math.max(0, ...ys);
    if (yhi - ylo < 1e-9) yhi = ylo + 0.1;
    const x = (v) => pad.l + ((v - xlo) / ((xhi - xlo) || 1)) * W, y = (v) => pad.t + (1 - (v - ylo) / (yhi - ylo)) * H;
    let s = `<line class="axis" x1="${pad.l}" y1="${y(0)}" x2="${w - pad.r}" y2="${y(0)}"/>`;
    for (const t of [ylo, 0, yhi]) s += `<text x="${pad.l - 6}" y="${y(t) + 4}" text-anchor="end">${(t * 100).toFixed(0)}%</text>`;
    for (const p of xs.filter((v, i, a) => a.indexOf(v) === i)) s += `<text x="${x(p)}" y="${h - 10}" text-anchor="middle">${p}</text>`;
    series.forEach((sr) => {
      const d = sr.points.filter((p) => isNum(p.y)).map((p, i) => (i ? "L" : "M") + x(p.x) + " " + y(p.y)).join(" ");
      s += `<path class="line ${sr.alt ? "alt" : ""}" d="${d}"><title>${esc(sr.name)}</title></path>`;
    });
    const leg = series.map((sr, i) => `<text x="${pad.l + 8 + i * 90}" y="${pad.t + 10}" style="fill:${sr.alt ? "var(--up)" : "var(--accent)"}">■ ${esc(sr.name)}</text>`).join("");
    return svgWrap(s + leg, w, h);
  }

  // ---------------------------------------------------------------- data loading
  async function loadInfo() {
    state.info = await api("/api/info");
    applyTheme(state.info.settings.theme);
    const src = state.info.sources;
    if (!src.live.has_data && src.demo.has_data && state.source === "live" && !state.userPickedSource) state.source = "demo";
    return state.info;
  }
  async function loadView(view) {
    const q = "?source=" + state.source;
    try {
      state.loading[view] = true; render();
      if (view === "dashboard" || view === "backtest") state.report = await api("/api/report" + q);
      if (view === "dashboard" || view === "picks") state.picks = await api("/api/picks" + q);
      if (view === "matches") state.matches = await api("/api/matches" + q);
    } catch (e) { toast(e.message, "error"); }
    finally { state.loading[view] = false; render(); }
  }
  function applyTheme(theme) {
    const dark = theme === "dark" || (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }
  async function runJob(name, body) {
    try {
      state.job = await api("/api/jobs/" + name, { method: "POST", body: JSON.stringify(Object.assign({ source: state.source }, body || {})) });
      state.activityOpen = true;
      toast(name + " started");
      render();
      pollJobs();
    } catch (e) { toast(e.message, "error"); }
  }
  let pollTimer = null;
  async function pollJobs() {
    clearTimeout(pollTimer);
    try {
      const st = await api("/api/jobs");
      const prev = state.job;
      state.job = st.current;
      renderStatus(); renderActivity();
      if (state.job && state.job.status === "running") { pollTimer = setTimeout(pollJobs, 1500); return; }
      if (prev && prev.status === "running" && state.job && state.job.status !== "running") {
        toast(state.job.name + (state.job.status === "done" ? " finished" : " failed: " + state.job.error), state.job.status === "done" ? "ok" : "error");
        if (state.job.name === "demo" && state.job.status === "done") { state.source = "demo"; }
        await loadInfo(); await loadView(state.view); if (state.view !== "dashboard") state.report = await api("/api/report?source=" + state.source).catch(() => state.report);
        render();
      }
    } catch (e) { /* server going away */ }
    pollTimer = setTimeout(pollJobs, 8000);
  }
  setInterval(() => fetch("/api/heartbeat").catch(() => {}), 5000);

  // ---------------------------------------------------------------- rendering
  function render() { renderTabs(); renderStatus(); renderActions(); renderView(); renderActivity(); renderDrawer(); }
  function renderTabs() {
    const n = state.picks && state.picks.picks ? state.picks.picks.length : 0;
    $("#tabs").innerHTML = TABS.map(([id, label]) => `<button class="tab ${state.view === id ? "active" : ""}" data-view="${id}">${label}${id === "picks" && n ? `<span class="tab-badge">${n}</span>` : ""}</button>`).join("");
    $("#tabs").querySelectorAll(".tab").forEach((b) => b.onclick = () => { state.view = b.dataset.view; state.selected = null; loadView(state.view); render(); });
  }
  function renderStatus() {
    const j = state.job;
    let html = "";
    if (j && j.status === "running") html = `<span class="spinner"></span><span class="step">${esc(j.name)}: ${esc((j.log[j.log.length - 1] || "").replace(/^\S+ \w+ /, ""))}</span>`;
    else if (state.info) {
      const s = state.info.sources[state.source];
      html = `<span class="step">${state.source === "demo" ? "Synthetic demo data" : "Live data"} · fetched ${timeAgo(s.fetched_at)} · backtest ${timeAgo(s.backtest_at)} · picks ${timeAgo(s.picks_at)}</span>`;
    }
    $("#status").innerHTML = html;
  }
  function renderActions() {
    const busy = state.job && state.job.status === "running";
    $("#actions").innerHTML = `
      <button class="btn sm" id="b-fetch" ${busy ? "disabled" : ""} title="Download results, odds and venue prices for the settings' window">Fetch</button>
      <button class="btn sm" id="b-backtest" ${busy ? "disabled" : ""} title="Analyze what was fetched">Backtest</button>
      <button class="btn sm primary" id="b-picks" ${busy ? "disabled" : ""} title="Rank upcoming contracts">Picks</button>
      <button class="btn sm ghost" id="b-activity" title="Show job log">Activity</button>
      <button class="btn sm ghost" id="b-theme" title="Toggle light/dark">◐</button>
      <button class="btn sm ghost danger" id="b-quit" title="Quit Robinhood Soccer HQ">Quit</button>`;
    $("#b-fetch").onclick = () => runJob(state.source === "demo" ? "demo" : "run", { refresh: false });
    $("#b-backtest").onclick = () => runJob("backtest");
    $("#b-picks").onclick = () => runJob("picks");
    $("#b-activity").onclick = () => { state.activityOpen = !state.activityOpen; renderActivity(); };
    $("#b-theme").onclick = async () => {
      const cur = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try { state.info.settings = await api("/api/settings", { method: "POST", body: JSON.stringify({ theme: cur }) }); applyTheme(cur); } catch (e) { toast(e.message, "error"); }
    };
    $("#b-quit").onclick = async () => { if (confirm("Quit Robinhood Soccer HQ?")) { await api("/api/quit", { method: "POST" }).catch(() => {}); document.body.innerHTML = '<div class="empty"><h2>Robinhood Soccer HQ closed</h2><p>You can close this window.</p></div>'; } };
  }
  function renderActivity() {
    const a = $("#activity");
    a.hidden = !state.activityOpen;
    $("#activity-close").onclick = () => { state.activityOpen = false; renderActivity(); };
    const j = state.job;
    $("#activity-log").textContent = j ? j.log.join("\n") : "No job has run yet.";
    $("#activity-log").scrollTop = 1e9;
  }
  function sourceStrip() {
    const src = state.info ? state.info.sources : {};
    const chip = (id, label) => `<span class="chip click ${state.source === id ? "on" : ""}" data-src="${id}"><b>${label}</b>${src[id] && src[id].has_data ? "" : " · no data"}</span>`;
    return `<div class="strip" id="srcstrip">${chip("live", "Live")}${chip("demo", "Demo")}<span class="muted small">${state.info ? "Data folder: " + esc(state.info.app_dir) : ""}</span></div>`;
  }
  function bindSourceStrip() {
    document.querySelectorAll("#srcstrip .chip").forEach((c) => c.onclick = () => { state.source = c.dataset.src; state.userPickedSource = true; loadView(state.view); render(); });
  }
  function renderView() {
    const v = $("#view");
    const fn = { dashboard: viewDashboard, picks: viewPicks, backtest: viewBacktest, matches: viewMatches, settings: viewSettings }[state.view];
    v.innerHTML = fn ? fn() : "";
    bindSourceStrip();
    if (state.view === "settings") bindSettings();
    if (state.view === "matches") bindMatches();
    if (state.view === "picks") bindPicks();
    if (state.view === "dashboard") bindDashboard();
  }
  function emptyState() {
    return `<div class="card empty"><h2>Welcome to Robinhood Soccer HQ</h2>
      <p>Backtest Robinhood/Kalshi soccer match contracts against real results, then rank upcoming bets by confidence.</p>
      <p class="row" style="justify-content:center;gap:10px"><button class="btn primary" id="e-demo">Run the demo (no internet, ~40 s)</button><button class="btn" id="e-fetch">Fetch live data</button></p>
      <p class="muted small">Live fetch pulls results (ESPN), odds (football-data.co.uk) and prices (Kalshi) for the leagues and dates in Settings.</p></div>`;
  }

  // ---------------------------------------------------------------- views
  function viewDashboard() {
    const info = state.info; if (!info) return "";
    const src = info.sources[state.source];
    let html = sourceStrip();
    if (!src.has_data) return html + emptyState();
    const rep = (state.report && state.report.summary) || {};
    const pro = (rep.pro && rep.pro.summary) || {};
    const acc = rep.accuracy_vs_book || {};
    const picks = (state.picks && state.picks.picks) || [];
    const meta = rep.meta || {};
    html += `<div class="grid summary">
      <div class="card stat"><div class="label">Fixtures in window</div><div class="value num">${fmtInt(meta.n_matches_window)}</div><div class="sub">${fmtInt(rep.n_matches)} priced &amp; settled · ${fmtInt(meta.n_snapshots)} contract snapshots</div></div>
      <div class="card stat"><div class="label">Venue vs closing line (Brier gap)</div><div class="value num ${isNum(acc.mean_diff) ? (acc.mean_diff > 0 ? "neg" : "pos") : ""}">${isNum(acc.mean_diff) ? (acc.mean_diff > 0 ? "+" : "") + acc.mean_diff.toFixed(3) : "–"}</div><div class="sub">${isNum(acc.t) ? "t = " + acc.t.toFixed(1) + " · positive = venue less accurate" : "no closing line in sample"}</div></div>
      <div class="card stat"><div class="label">Professional rules, after fees</div><div class="value num ${cls(pro.flat_roi)}">${fmtPct(pro.flat_roi, 1, true)}</div><div class="sub">${fmtInt(pro.n)} bets · 95% CI ${fmtPct(pro.flat_roi_ci_low, 0, true)} to ${fmtPct(pro.flat_roi_ci_high, 0, true)} · CLV ${isNum(pro.clv_close_mean) ? (pro.clv_close_mean * 100).toFixed(1) + " pts" : "–"}</div></div>
      <div class="card stat"><div class="label">Picks ready</div><div class="value num">${picks.length}</div><div class="sub">${picks.length ? esc(picks[0].home + " v " + picks[0].away + " · " + picks[0].side.toUpperCase() + " " + picks[0].outcome + " · " + picks[0].tier) : "run Picks for upcoming fixtures"}</div></div>
    </div>`;
    html += `<div class="grid two"><div class="card"><h3>Verdict</h3>${rep.verdicts && rep.verdicts.length ? `<ul class="verdicts">${rep.verdicts.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>` : '<div class="muted">Run a backtest to get a verdict.</div>'}</div>
      <div class="card"><h3>Data sources</h3>${table([txt("league"), num("espn_matches", 0, "ESPN fixtures"), num("fdcouk_matches", 0, "odds rows"), num("kalshi_markets", 0, "Kalshi markets"), num("kalshi_snapshots", 0, "snapshots")],
        Object.entries((meta.leagues) || {}).map(([k, v]) => Object.assign({ league: k }, v)), { empty: "No per-league details." })}
      <div class="row wrap"><button class="btn sm" id="d-fetch">${state.source === "demo" ? "Regenerate demo" : "Fetch + backtest"}</button><button class="btn sm" id="d-backtest">Backtest again</button><button class="btn sm primary" id="d-picks">Update picks</button></div></div></div>`;
    if (rep.pro && rep.pro.pool_weights) {
      const pw = rep.pro.pool_weights;
      html += `<div class="strip">${Object.entries(pw).map(([k, v]) => `<span class="chip"><b>${esc(k)}</b> ${Object.entries(v.weights).map(([s, w]) => s + " " + w.toFixed(2)).join(" · ")} · n=${v.n_train}</span>`).join("")}<span class="muted small">pooling weights (what the fair value trusts)</span></div>`;
    }
    return html;
  }
  function bindDashboard() {
    const b = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
    b("#e-demo", () => runJob("demo")); b("#e-fetch", () => runJob("run"));
    b("#d-fetch", () => runJob(state.source === "demo" ? "demo" : "run")); b("#d-backtest", () => runJob("backtest")); b("#d-picks", () => runJob("picks"));
  }

  function viewPicks() {
    let html = sourceStrip();
    const p = state.picks;
    if (!p || (!p.picks.length && !p.candidates.length)) return html + `<div class="card empty"><h2>No picks yet</h2><p>Picks rank the venue's open contracts for the next days by confidence.</p><p><button class="btn primary" id="p-run">Generate picks</button></p></div>`;
    const rulesLine = (p.markdown.match(/^Rules: (.*)$/m) || [])[1] || "";
    html += `<div class="row wrap mb"><span class="muted small">Generated ${timeAgo(p.generated)} · ${p.upcoming.length} upcoming fixtures with open markets · ${esc(rulesLine)}</span><span class="spacer"></span><button class="btn sm primary" id="p-run">Refresh picks</button></div>`;
    html += `<div class="card mb"><h3>${p.picks.length} pick${p.picks.length === 1 ? "" : "s"} that pass every rule</h3>` + table([
      { key: "kickoff", label: "Kickoff", render: (r) => fmtKick(r.kickoff) }, txt("league"), { key: "home", label: "Match", render: (r) => esc(r.home + " v " + r.away) },
      { key: "side", label: "Bet", render: (r) => `<b>${esc(r.side.toUpperCase())} ${esc(r.outcome)}</b>` }, num("price", 2), num("fee", 3), num("fair", 3),
      { key: "edge", label: "Edge", num: true, render: (r) => `<span class="${cls(r.edge)}">${fmtPct(r.edge, 1, true)}</span>` },
      { key: "confidence", label: "Confidence", render: (r) => scorebar(r.confidence) }, { key: "tier", label: "Tier", render: (r) => badge(r.tier) },
      { key: "stake", label: "Stake", num: true, render: (r) => fmtMoney(r.stake) }, num("contracts", 0),
      { key: "agreement", label: "Why", render: (r) => esc(why(r)) },
    ], p.picks, { empty: "Nothing meets the confidence and edge thresholds right now. That is the normal outcome most days." }) + `</div>`;
    const near = p.candidates.filter((c) => c.edge > 0 && !p.picks.some((k) => k.match_id === c.match_id && k.outcome === c.outcome && k.side === c.side)).slice(0, 15);
    html += `<div class="card"><h3>Positive-edge contracts that did not qualify</h3>` + table([
      { key: "kickoff", label: "Kickoff", render: (r) => fmtKick(r.kickoff) }, txt("league"), { key: "home", label: "Match", render: (r) => esc(r.home + " v " + r.away) },
      { key: "side", label: "Bet", render: (r) => `${esc(r.side.toUpperCase())} ${esc(r.outcome)}` }, num("price", 2), num("fair", 3), num("fair_sd", 3),
      { key: "edge", label: "Edge", num: true, render: (r) => fmtPct(r.edge, 1, true) }, num("edge_z", 2, "z"), { key: "confidence", label: "Confidence", render: (r) => scorebar(r.confidence) },
      { key: "tier", label: "Tier", render: (r) => badge(r.tier) }, { key: "reason", label: "Blocked by", render: (r) => esc(blockedBy(r)) },
    ], near) + `</div>`;
    html += `<details class="mb"><summary>Read before betting</summary><pre class="md">${esc((p.markdown.split("## Read before betting")[1] || "").trim())}</pre></details>`;
    return html;
  }
  function why(r) {
    const parts = [];
    if (isNum(r.agreement)) parts.push("sources agree " + Math.round(r.agreement * 100) + "%");
    if (isNum(r.spread)) parts.push("spread " + r.spread.toFixed(2));
    if (isNum(r.stale_hours)) parts.push("last trade " + Math.round(r.stale_hours) + "h ago");
    if (isNum(r.edge_z)) parts.push("z=" + r.edge_z.toFixed(1));
    if (isNum(r.book_edge)) parts.push("book edge " + fmtPct(r.book_edge, 1, true));
    return parts.join("; ");
  }
  function blockedBy(r) {
    const s = state.info ? state.info.settings : {};
    const out = [];
    if (isNum(r.confidence) && r.confidence < (s.min_confidence || 60)) out.push("confidence");
    if (isNum(r.edge) && r.edge < (s.min_edge || 0.03)) out.push("edge");
    if (isNum(r.edge_q20) && r.edge_q20 < 0) out.push("edge q20 < 0");
    if (isNum(r.book_edge) && r.book_edge < 0) out.push("book line disagrees");
    if (isNum(r.spread) && r.spread > 0.06) out.push("spread");
    if (r.quotes_ok === false) out.push("quotes inconsistent");
    if (isNum(r.price) && (r.price < 0.1 || r.price > 0.9)) out.push("price band");
    return out.join(", ") || "one bet per match";
  }
  function bindPicks() { const b = $("#p-run"); if (b) b.onclick = () => runJob("picks"); }

  function viewBacktest() {
    let html = sourceStrip();
    const rep = state.report && state.report.summary;
    if (!rep || !rep.scores) return html + `<div class="card empty"><h2>No backtest yet</h2><p><button class="btn primary" id="bt-run">Run backtest</button></p></div>`;
    const pro = rep.pro || {}; const ps = pro.summary || {};
    html += `<div class="row wrap mb"><span class="muted small">Window ${esc(rep.meta.start)} → ${esc(rep.meta.end)} · fees ${esc(rep.meta.fee_model)} · fills at ${esc(rep.meta.fill)} · generated ${timeAgo(state.report.generated)}</span><span class="spacer"></span><button class="btn sm" id="bt-run">Run backtest</button></div>`;
    html += `<div class="card mb"><h3>Verdict</h3><ul class="verdicts">${(rep.verdicts || []).map((v) => `<li>${esc(v)}</li>`).join("")}</ul></div>`;
    html += `<div class="grid summary">
      <div class="card stat"><div class="label">Pro bets</div><div class="value num">${fmtInt(ps.n)}</div><div class="sub">avg confidence ${fmtNum(ps.avg_confidence, 0)} · avg edge ${fmtPct(ps.avg_edge, 1)}</div></div>
      <div class="card stat"><div class="label">Flat ROI</div><div class="value num ${cls(ps.flat_roi)}">${fmtPct(ps.flat_roi, 1, true)}</div><div class="sub">95% CI ${fmtPct(ps.flat_roi_ci_low, 0, true)} to ${fmtPct(ps.flat_roi_ci_high, 0, true)} · win ${fmtPct(ps.win_rate, 0)}</div></div>
      <div class="card stat"><div class="label">Kelly ROI</div><div class="value num ${cls(ps.kelly_roi)}">${fmtPct(ps.kelly_roi, 1, true)}</div><div class="sub">staked ${fmtMoney(ps.kelly_staked)} · profit ${fmtMoney(ps.kelly_profit)} · max DD ${fmtPct(ps.max_drawdown, 1)}</div></div>
      <div class="card stat"><div class="label">Closing line value</div><div class="value num ${cls(ps.clv_close_mean)}">${isNum(ps.clv_close_mean) ? (ps.clv_close_mean * 100).toFixed(1) + " pts" : "–"}</div><div class="sub">${fmtPct(ps.clv_close_positive, 0)} of bets beat the venue close · vs book ${isNum(ps.clv_book_mean) ? (ps.clv_book_mean * 100).toFixed(1) + " pts" : "–"}</div></div>
    </div>`;
    const sweeps = rep.sweeps || {};
    const series = ["pro", "book"].filter((k) => sweeps[k]).map((k, i) => ({ name: k, alt: i === 1, points: sweeps[k].map((r) => ({ x: r.min_edge, y: r.roi })) }));
    html += `<div class="grid two">
      <div class="card"><h3>Calibration of venue prices</h3>${reliabilityChart(rep.calibration)}<div class="muted small">Dots above the diagonal paid out more often than their price implied (cheap). Bars are ±2 s.e.</div></div>
      <div class="card"><h3>ROI by minimum edge, after fees</h3>${lineChart(series)}<div class="muted small">Higher thresholds trade volume for quality; a flat or falling curve means the edge is not real.</div></div>
      <div class="card"><h3>Realized ROI by confidence tier (all candidates)</h3>${barChart((rep.pro_tiers || []).map((t) => ({ label: t.tier + " (n=" + t.n + ")", value: t.roi, lo: t.roi_ci_low, hi: t.roi_ci_high, n: t.n })))}<div class="muted small">Does the confidence score rank bets correctly? A should beat B should beat C.</div></div>
      <div class="card"><h3>Realized ROI by predicted-edge decile</h3>${barChart((rep.pro_deciles || []).map((d) => ({ label: "D" + d.decile, value: d.roi, lo: d.roi_ci_low, hi: d.roi_ci_high, n: d.n })))}<div class="muted small">Spearman rho ${isNum(pro.decile_rho) ? pro.decile_rho.toFixed(2) : "–"}: profits should rise with predicted edge.</div></div>
    </div>`;
    html += `<div class="card mb"><h3>Accuracy (lower is better)</h3>${table([txt("source"), num("n", 0), num("brier", 3), num("logloss", 3)], rep.scores)}
      ${table([txt("source"), num("n", 0), num("mse_vs_closing_line", 4), num("mean_abs_diff_pts", 2)], rep.closing_distance, { empty: "No closing line in the sample." })}</div>`;
    html += `<div class="card mb"><h3>Systematic bias</h3>${table([txt("outcome"), num("n", 0), num("mean_price"), num("hit_rate"), { key: "diff", label: "diff", num: true, render: (r) => `<span class="${cls(r.diff)}">${fmtNum(r.diff)}</span>` }, num("z", 1)], rep.bias_by_outcome)}
      ${table([txt("outcome"), num("n", 0), { key: "mean_diff", label: "venue − closing line", num: true, render: (r) => `<span class="${cls(-r.mean_diff)}">${isNum(r.mean_diff) ? (r.mean_diff * 100).toFixed(2) + " pts" : "–"}</span>` }, num("t", 1)], rep.market_vs_book, { empty: "" })}
      ${table([txt("league"), num("n", 0), num("overround"), num("draw_price"), num("draw_rate"), num("home_price"), num("home_rate"), num("brier_mktn"), num("brier_book")], rep.bias_by_league)}</div>`;
    html += `<div class="card mb"><h3>Strategies, after fees</h3>${table([txt("rule"), num("n", 0), num("risked", 2), num("profit", 2), pct("roi", true), pct("roi_ci_low", true), pct("roi_ci_high", true), pct("win_rate")], rep.naive)}
      ${table([txt("reference"), num("n", 0), num("risked", 2), num("profit", 2), pct("roi", true), pct("roi_ci_low", true), pct("roi_ci_high", true), pct("win_rate"), num("avg_price", 2), num("avg_edge", 3)],
        Object.entries(rep.strategies || {}).map(([k, v]) => Object.assign({ reference: k }, v)))}</div>`;
    const port = state.report.pro_portfolio || [];
    html += `<div class="card mb"><h3>Bets the professional rules would have placed</h3>${table([
      { key: "kickoff", label: "Kickoff", render: (r) => fmtKick(r.kickoff) }, txt("league"), { key: "home", label: "Match", render: (r) => esc(r.home + " v " + r.away) },
      { key: "side", label: "Bet", render: (r) => `${esc(String(r.side).toUpperCase())} ${esc(r.outcome)}` }, num("price", 2), num("fair", 3), { key: "edge", label: "Edge", num: true, render: (r) => fmtPct(r.edge, 1, true) },
      { key: "confidence", label: "Confidence", render: (r) => scorebar(r.confidence) }, { key: "tier", label: "Tier", render: (r) => badge(r.tier) }, num("contracts", 0),
      { key: "clv_close", label: "CLV", num: true, render: (r) => `<span class="${cls(r.clv_close)}">${isNum(r.clv_close) ? (r.clv_close * 100).toFixed(1) : "–"}</span>` },
      { key: "won", label: "Result", render: (r) => r.won == null ? "–" : `<span class="badge ${r.won ? "up" : "down"}">${r.won ? "won" : "lost"}</span>` },
      { key: "profit", label: "P&L", num: true, render: (r) => `<span class="${cls(r.profit)}">${isNum(r.profit) ? (r.profit * (r.contracts || 1)).toFixed(2) : "–"}</span>` },
    ], port.slice(0, 60))}</div>`;
    html += `<details><summary>Full report (markdown)</summary><pre class="md">${esc(state.report.markdown)}</pre></details>`;
    return html;
  }

  function viewMatches() {
    let html = sourceStrip();
    const all = (state.matches && state.matches.matches) || [];
    if (!all.length) return html + `<div class="card empty"><h2>No matches</h2><p>Run a backtest first.</p></div>`;
    const leagues = [...new Set(all.map((m) => m.league))].sort();
    const f = state.filter;
    const rows = all.filter((m) => (!f.league || m.league === f.league) && (!f.result || m.result === f.result) && (!f.q || (m.home + " " + m.away).toLowerCase().includes(f.q.toLowerCase())));
    html += `<div class="row wrap mb"><select id="m-league"><option value="">All leagues</option>${leagues.map((l) => `<option ${f.league === l ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <select id="m-result"><option value="">Any result</option>${["home", "draw", "away"].map((r) => `<option ${f.result === r ? "selected" : ""}>${r}</option>`).join("")}</select>
      <input id="m-q" placeholder="Search team" value="${esc(f.q)}"><span class="muted small">${rows.length} of ${all.length} matches · click a row for every source and quote</span></div>`;
    const best = (m) => bestEdge(m);
    html += table([
      { key: "kickoff", label: "Kickoff", render: (r) => fmtKick(r.kickoff) }, txt("league"),
      { key: "home", label: "Match", render: (r) => `${esc(r.home)} <span class="muted">v</span> ${esc(r.away)}` },
      { key: "result", label: "Score", render: (r) => r.result ? `<b>${fmtInt(r.home_goals)}–${fmtInt(r.away_goals)}</b> <span class="muted small">${esc(r.result)}</span>` : '<span class="muted">upcoming</span>' },
      { key: "mkt_home", label: "Venue H / D / A", render: (r) => `<span class="num">${fmtNum(r.mkt_home, 2)} / ${fmtNum(r.mkt_draw, 2)} / ${fmtNum(r.mkt_away, 2)}</span>` },
      { key: "pro_home", label: "Fair H / D / A", render: (r) => `<span class="num">${fmtNum(r.pro_home, 2)} / ${fmtNum(r.pro_draw, 2)} / ${fmtNum(r.pro_away, 2)}</span>` },
      { key: "book_home", label: "Book H / D / A", render: (r) => `<span class="num">${fmtNum(r.book_home, 2)} / ${fmtNum(r.book_draw, 2)} / ${fmtNum(r.book_away, 2)}</span> <span class="muted small">${esc(r.book_source || "")}</span>` },
      { key: "edge", label: "Best gross edge", render: (r) => { const b = best(r); return b ? `<span class="${cls(b.edge)}">${fmtPct(b.edge, 1, true)}</span> <span class="muted small">${b.label}</span>` : "–"; } },
    ], rows.slice(0, 400), { onRow: true });
    return html;
  }
  function bestEdge(m) {
    let best = null;
    for (const o of ["home", "draw", "away"]) {
      const fair = m["pro_" + o]; if (!isNum(fair)) continue;
      const ask = isNum(m["ask_" + o]) ? m["ask_" + o] : m["mkt_" + o]; const bid = isNum(m["bid_" + o]) ? m["bid_" + o] : m["mkt_" + o];
      if (isNum(ask)) { const e = fair - ask; if (!best || e > best.edge) best = { edge: e, label: "YES " + o }; }
      if (isNum(bid)) { const e = (1 - fair) - (1 - bid); if (!best || e > best.edge) best = { edge: e, label: "NO " + o }; }
    }
    return best;
  }
  function bindMatches() {
    const rerender = () => { renderView(); };
    const l = $("#m-league"), r = $("#m-result"), q = $("#m-q");
    if (l) l.onchange = () => { state.filter.league = l.value; rerender(); };
    if (r) r.onchange = () => { state.filter.result = r.value; rerender(); };
    if (q) q.oninput = () => { state.filter.q = q.value; rerender(); const el = $("#m-q"); el.focus(); el.setSelectionRange(el.value.length, el.value.length); };
    const all = (state.matches && state.matches.matches) || [];
    const f = state.filter;
    const rows = all.filter((m) => (!f.league || m.league === f.league) && (!f.result || m.result === f.result) && (!f.q || (m.home + " " + m.away).toLowerCase().includes(f.q.toLowerCase())));
    document.querySelectorAll("table.hq tbody tr.click").forEach((tr) => tr.onclick = () => { state.selected = rows[+tr.dataset.i]; renderDrawer(); });
  }
  function renderDrawer() {
    const d = $("#drawer");
    const m = state.selected;
    if (!m || state.view !== "matches") { d.hidden = true; return; }
    d.hidden = false;
    const line = (label, h, dr, a, extra) => `<tr><td>${label}</td><td class="num">${fmtNum(h, 3)}</td><td class="num">${fmtNum(dr, 3)}</td><td class="num">${fmtNum(a, 3)}</td><td class="muted small">${extra || ""}</td></tr>`;
    d.innerHTML = `<div class="row"><h2 style="margin:0">${esc(m.home)} v ${esc(m.away)}</h2><span class="spacer"></span><button class="btn sm ghost" id="dr-close">✕</button></div>
      <div class="muted small mb">${esc(m.league)} · ${fmtKick(m.kickoff)} · ${m.result ? "final " + fmtInt(m.home_goals) + "–" + fmtInt(m.away_goals) : "not played yet"}</div>
      <div class="tablewrap"><table class="hq"><thead><tr><th>Source</th><th class="num">Home</th><th class="num">Draw</th><th class="num">Away</th><th></th></tr></thead><tbody>
      ${line("Venue last", m.mkt_home, m.mkt_draw, m.mkt_away, "overround " + fmtPct(m.mkt_overround, 1))}
      ${line("Venue ask", m.ask_home, m.ask_draw, m.ask_away, "buy YES here")}
      ${line("Venue bid", m.bid_home, m.bid_draw, m.bid_away, "NO costs 1 − bid")}
      ${line("Venue close", m.close_home, m.close_draw, m.close_away, "last trade at kickoff")}
      ${line("Fair (pooled)", m.pro_home, m.pro_draw, m.pro_away, "± " + fmtNum(m.prosd_home, 3) + " · n_train " + fmtInt(m.pro_n_train))}
      ${line("Book (decision time)", m.book_home, m.book_draw, m.book_away, m.book_source || "")}
      ${line("Book (closing)", m.bookc_home, m.bookc_draw, m.bookc_away, "for CLV")}
      ${line("Poisson", m.poisson_home, m.poisson_draw, m.poisson_away, "")}
      ${line("Elo", m.elo_home, m.elo_draw, m.elo_away, "")}
      </tbody></table></div>
      <div class="kv"><b>Volume</b><span>${fmtInt(m.vol_home)} / ${fmtInt(m.vol_draw)} / ${fmtInt(m.vol_away)} contracts</span><b>Games played (min of both)</b><span>${fmtInt(m.team_games)}</span><b>Rest days</b><span>${fmtNum(m.rest_home, 0)} / ${fmtNum(m.rest_away, 0)}</span><b>Event</b><span class="mono small">${esc(m.event_id || "")}</span></div>`;
    $("#dr-close").onclick = () => { state.selected = null; renderDrawer(); };
  }

  function viewSettings() {
    const s = state.settingsDraft || Object.assign({}, state.info.settings);
    state.settingsDraft = s;
    const leagues = ["epl", "laliga", "bundesliga", "seriea", "ligue1", "mls", "ucl", "uel", "uecl", "leaguescup", "ligamx"];
    const field = (key, label, type, extra) => `<div class="field"><label>${esc(label)}</label><input id="s-${key}" type="${type || "text"}" value="${esc(s[key] == null ? "" : s[key])}" ${extra || ""}></div>`;
    const select = (key, label, opts) => `<div class="field"><label>${esc(label)}</label><select id="s-${key}">${opts.map((o) => `<option value="${o}" ${s[key] === o ? "selected" : ""}>${o}</option>`).join("")}</select></div>`;
    return `<div class="card mb"><h3>Data</h3>
      <div class="field mb"><label>Leagues</label><div class="checks">${leagues.map((l) => `<label><input type="checkbox" data-league="${l}" ${(s.leagues || []).includes(l) ? "checked" : ""}>${l}</label>`).join("")}</div></div>
      <div class="form">${field("start", "First kickoff date (post-World-Cup default)", "date")}${field("end", "Last kickoff date (blank = today)", "date")}${field("warmup_days", "Warm-up days for models (leagues without odds files)", "number")}${field("minutes_before", "Snapshot minutes before kickoff (0 = at kickoff; 360 to measure CLV)", "number")}${field("days_ahead", "Picks: days ahead", "number")}</div></div>
      <div class="card mb"><h3>Analysis and staking</h3><div class="form">${select("fees", "Fee model", ["robinhood", "robinhood_gold", "robinhood_flat", "kalshi", "none"])}${select("fill", "Fill", ["ask", "last"])}${field("min_edge", "Minimum edge after fees", "number", 'step="0.005"')}${field("bankroll", "Bankroll ($)", "number", 'step="50"')}${field("kelly", "Fraction of Kelly", "number", 'step="0.05"')}${field("max_bet", "Max fraction per bet", "number", 'step="0.005"')}${field("max_day", "Max fraction per day", "number", 'step="0.01"')}${field("max_bets_per_day", "Max bets per day", "number")}${field("min_confidence", "Minimum confidence (0–100)", "number")}</div></div>
      <div class="card mb"><h3>App</h3><div class="form">${select("theme", "Theme", ["system", "light", "dark"])}${field("kalshi_key_id", "Kalshi API key id (optional)")}${field("kalshi_private_key", "Kalshi private key path (optional; needs the Python install)")}${field("github_repo", "GitHub repo for update checks")}</div>
      <div class="row mb" style="margin-top:12px"><button class="btn primary" id="s-save">Save settings</button><span class="muted small" id="s-msg"></span></div></div>
      <div class="card"><h3>About</h3><div class="kv"><b>Version</b><span>${esc(state.info.version)}</span><b>Data folder</b><span class="mono small">${esc(state.info.app_dir)}</span><b>Updates</b><span><button class="btn sm" id="s-upd">Check for updates</button> <span id="s-upd-msg" class="small">${state.updates ? esc(updatesText(state.updates)) : ""}</span></span></div>
      <p class="muted small">Robinhood Soccer HQ backtests Robinhood/Kalshi soccer contracts against real results and ranks upcoming bets by confidence. Nothing here is financial advice; the numbers are only as good as the sample size.</p></div>`;
  }
  function updatesText(u) { return u.error ? "Could not check: " + u.error : u.newer ? "Version " + u.latest + " is available: " + (u.url || "") : "You are on the latest version (" + u.current + ")."; }
  function bindSettings() {
    const s = state.settingsDraft;
    document.querySelectorAll("#view input, #view select").forEach((el) => el.onchange = () => {
      if (el.dataset.league) { s.leagues = [...document.querySelectorAll("input[data-league]:checked")].map((c) => c.dataset.league); return; }
      const key = el.id.replace(/^s-/, ""); if (key in s || key === "end") s[key] = el.type === "number" ? Number(el.value) : el.value;
    });
    $("#s-save").onclick = async () => {
      try { state.info.settings = await api("/api/settings", { method: "POST", body: JSON.stringify(s) }); applyTheme(state.info.settings.theme); $("#s-msg").textContent = "Saved."; toast("Settings saved", "ok"); }
      catch (e) { $("#s-msg").textContent = e.message; toast(e.message, "error"); }
    };
    $("#s-upd").onclick = async () => { $("#s-upd-msg").textContent = "Checking…"; state.updates = await api("/api/updates"); $("#s-upd-msg").textContent = updatesText(state.updates); };
  }

  // ---------------------------------------------------------------- boot
  (async function boot() {
    try { await loadInfo(); } catch (e) { $("#view").innerHTML = `<div class="card empty"><h2>Cannot reach the HQ server</h2><p>${esc(e.message)}</p></div>`; return; }
    render();
    await loadView("dashboard");
    pollJobs();
  })();
})();
