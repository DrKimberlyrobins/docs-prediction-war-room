"use strict";
const el = id => document.getElementById(id);
const esc = value => String(value ?? "—").replace(/[&<>"']/g, ch => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
})[ch]);
const central = (value, options) => new Intl.DateTimeFormat("en-US", {
  timeZone:"America/Chicago", ...options
}).format(new Date(value));
const stamp = value => central(value, {month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"});
const dayName = value => central(value+"T12:00:00-06:00", {weekday:"long",month:"long",day:"numeric",year:"numeric"});
const nowDate = () => new Intl.DateTimeFormat("en-CA", {timeZone:"America/Chicago",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const pts = n => Number(n).toFixed(1);
const signed = n => (n > 0 ? "+" : "") + n;
const matchup = g => `${g.away.name} at ${g.home.name}`;
const tag = (name, value) => `<div><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`;
async function read(name) {
  const response = await fetch(`data/${name}.json`, {cache:"no-cache"});
  if (!response.ok) throw new Error(`${name} returned HTTP ${response.status}`);
  return response.json();
}
function detail(g) {
  const f = g.forecast;
  const p = f?.projection;
  const pick = f?.pick;
  let view = `<div class="eyebrow">${esc(matchup(g))}</div>`;
  if (p) {
    const margin = p.home - p.away;
    const h = p.inputs.home;
    const a = p.inputs.away;
    const lead = margin >= 0 ? g.home.name : g.away.name;
    const first = f.first_half;
    view += `<h2 class="pick">${esc(pick?.name ?? (margin === 0 ? "Even projected margin" : lead + " by " + pts(Math.abs(margin))))}</h2>
      <p>${pick ? esc(pick.provider + " via ESPN") + " · " + esc(pick.odds == null ? "price unavailable" : signed(pick.odds)) : "Independent score projection. No positive disagreement against a verified eligible line."}</p>
      <div class="numbers">${tag("Projected score (away–home)", pts(p.away)+"–"+pts(p.home))}
      ${tag("Projected margin", lead+" "+pts(Math.abs(margin)))}
      ${tag("Projected total",pts(p.home+p.away))}
      ${tag("Model disagreement",pick ? pts(pick.edge)+" pts" : "Unavailable")}</div>
      <h3>Why the model lands here</h3>
      <p>${esc(g.home.name)} has a ${pts(h.offense)}-point adjusted offense residual across ${h.games} games. 
      ${esc(g.away.name)} has a ${pts(a.offense)}-point adjusted offense residual across ${a.games} games.
      On defense, their adjusted points-allowed residuals are ${pts(h.defense)} and ${pts(a.defense)}, respectively. Lower is better.
      The scoring baseline is ${pts(p.inputs.league_mean)} points per team, with ${p.inputs.home_court_per_team} points added to the home team and subtracted from the away team.</p>
      ${pick ? `<p>The projection clears ${esc(pick.name)} by ${pts(pick.edge)} points. ${pick.validation.n ? `Rolling-origin RMSE for this market is ${pts(pick.validation.rmse)} points over ${pick.validation.n} games.` : ""} Cover probability unavailable.</p>` : ""}
      <h3>First half</h3><p>${first ? `${esc(g.away.name)} ${pts(first.away)} · ${esc(g.home.name)} ${pts(first.home)}. Trained on actual first-half scores.` : "Insufficient verified first-half samples."}</p>
      ${f.injuries ? `<h3>Official NBA availability</h3><p>Report ${esc(stamp(f.injuries.as_of))}. <a href="${esc(f.injuries.url)}" target="_blank" rel="noopener">Read the full NBA report</a>.</p>
      <ul>${f.injuries.entries.map(row=>`<li>${esc(row.team)} · ${esc(row.player ? row.player + " — " + row.status + (row.reason ? " · " + row.reason : "") : row.status)}</li>`).join("")}</ul>` : ""}
      <h3>Evidence coverage</h3><ul>${f.coverage.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>
      <details><summary>Model inputs</summary><pre>${esc(JSON.stringify(p.inputs,null,2))}</pre></details>
      <p class="muted">Saved ${esc(stamp(f.captured))} · Model ${esc(f.version)}</p>`;
  } else {
    view += `<h2 class="pick">Forecast unavailable</h2><p>${g.status === "STATUS_SCHEDULED" ? "A verified tip time and at least four completed games per team are needed." : "No pregame snapshot was saved for this matchup."}</p>`;
  }
  view += `<p class="source"><a href="${esc(g.source)}" target="_blank" rel="noopener">ESPN game and market data</a>${g.league === "nba" ? '<a href="https://www.nba.com/players/injury-report" target="_blank" rel="noopener">Official NBA injury report</a>' : ""}</p>`;
  el("analysis").innerHTML = view;
  el("detail").showModal();
}
async function slate() {
  const board = await read("board");
  let filter = "";
  const dates = [...new Set([board.today, ...board.games.map(g => g.day)])].sort();
  el("day").innerHTML = dates.map(d=>`<option value="${d}">${esc(dayName(d))}</option>`).join("");
  function draw() {
    const day = el("day").value;
    const games = board.games.filter(g=>g.day===day);
    const ranked = games.filter(g=>g.forecast?.pick?.rank != null)
      .sort((a,b)=>b.forecast.pick.rank-a.forecast.pick.rank).slice(0,10);
    const projected = games.filter(g=>g.forecast).length;
    const misses = board.failures.filter(x=>x.day===day).map(x=>board.leagues[x.league]);
    el("date").textContent = dayName(day);
    const stale = nowDate() > board.today;
    el("status").innerHTML = `<strong>${games.length} scheduled · ${projected} projected</strong><span>Data verified ${esc(stamp(board.generated))}</span>${stale ? "<strong>Archived slate · current update unavailable</strong>" : ""}${misses.length ? "<span>Schedule unavailable: "+esc(misses.join(", "))+"</span>" : ""}`;
    el("top").innerHTML = ranked.length ? `<button class="lead" data-game="${esc(ranked[0].id)}">${esc(ranked[0].forecast.pick.name)}</button><div>${esc(matchup(ranked[0]))} · ${pts(ranked[0].forecast.pick.edge)} pts model disagreement</div>` : "<p>No ranked forecasts for this slate.</p>";
    el("ranked").innerHTML = ranked.map(g=>`<li><button data-game="${esc(g.id)}">${esc(g.forecast.pick.name)} · ${esc(matchup(g))}</button></li>`).join("");
    el("filters").innerHTML = [["","All Games"],...Object.entries(board.leagues)].map(([key,name])=>`<button data-league="${esc(key)}" aria-pressed="${filter===key}">${esc(name)}</button>`).join("");
    const visible = games.filter(g=>!filter || g.league===filter);
    el("games").innerHTML = visible.map(g=>`<button class="card" data-game="${esc(g.id)}">
      <small>${esc(board.leagues[g.league])} · ${g.time_valid ? esc(central(g.tip,{hour:"numeric",minute:"2-digit",timeZoneName:"short"})) : "Time TBD"}${g.neutral?" · Neutral":""}</small>
      <span class="teams"><span>${esc(g.away.name)}</span><span>${g.neutral?"vs.":"at"} ${esc(g.home.name)}</span></span>
      <span class="${g.forecast?"ready":"muted"}">${g.forecast?.pick ? "Market forecast ready" : g.forecast ? "Score projection ready" : "Forecast unavailable"}</span></button>`).join("") || "<p>No matchups in this view.</p>";
  }

  const receiptButton = document.createElement("button");
  receiptButton.type = "button";
  receiptButton.textContent = "Print All Predictions";
  receiptButton.style.cssText = "margin:8px 0;padding:10px 16px;background:#102A4C;color:white;border:0;border-radius:6px;cursor:pointer;font-weight:700";
  el("filters").before(receiptButton);
  receiptButton.addEventListener("click", () => {
    const day = el("day").value;
    const games = board.games.filter(g=>g.day===day).sort((a,b)=>Number(b.time_valid)-Number(a.time_valid)||String(a.tip).localeCompare(String(b.tip)));
    const rows = games.map((g,i)=>{
      const f=g.forecast, p=f?.projection, pick=f?.pick, h=f?.first_half;
      return '<tr><td>'+ (i+1) +'</td><td>'+esc(g.time_valid?central(g.tip,{hour:"numeric",minute:"2-digit",timeZoneName:"short"}):"TBD")+'</td><td>'+esc(matchup(g))+'<small>'+esc(board.leagues[g.league])+'</small></td><td>'+esc(pick?.name ?? (p?"Score projection only":"Forecast unavailable"))+'</td><td>'+esc(h?pts(h.away)+"–"+pts(h.home):"—")+'</td><td>'+esc(h && h.away != null && h.home != null?pts(Number(h.away)+Number(h.home)):"—")+'</td><td>'+esc(p?pts(p.away)+"–"+pts(p.home):"—")+'</td><td>'+esc(p?pts(p.away+p.home):"—")+'</td><td>'+esc(f?.captured?stamp(f.captured):"—")+'</td></tr>';
    }).join("");
    const w=window.open("","_blank");
    if(!w){alert("Allow pop-ups to open the prediction receipt.");return;}
    w.opener=null;
    w.document.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Daily prediction receipt</title><style>body{font:11px Arial,sans-serif;color:#111;background:white;margin:16px}h1{font-size:22px;margin-bottom:5px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:4px;text-align:left;vertical-align:top}th{background:#eee}small{display:block;color:#555}tr{break-inside:avoid}thead{display:table-header-group}@page{size:landscape;margin:10mm}@media print{button{display:none}body{margin:0}}</style></head><body><button onclick="window.print()">Print / Save PDF</button><h1>DOC’S PREDICTION WAR ROOM — Daily Receipt</h1><p>'+esc(dayName(day))+' · '+games.length+' games · Board updated '+esc(stamp(board.generated))+' · Receipt created '+esc(stamp(new Date()))+'</p><p>Existing forecasts only. Scores are away–home. For research and grading, not a combined wager. Missing forecasts are shown explicitly.</p><table><thead><tr><th>#</th><th>Tip</th><th>Matchup</th><th>Existing prediction</th><th>1H score</th><th>1H total</th><th>Full score</th><th>Total</th><th>Forecast saved</th></tr></thead><tbody>'+rows+'</tbody></table></body></html>');
    w.document.close();
  });
  el("day").addEventListener("change",draw);
  document.addEventListener("click", e=>{
    const button = e.target.closest("button");
    if (!button) return;
    if ("league" in button.dataset) {
      filter=button.dataset.league;
      draw();
      [...el("filters").children].find(item=>item.dataset.league===filter)?.focus();
    }
    if (button.dataset.game) detail(board.games.find(g=>g.id===button.dataset.game));
  });
  el("close").addEventListener("click",()=>el("detail").close());
  el("formula").textContent = `Version ${board.version}. ${board.formula}`;
  el("validation").textContent = Object.entries(board.validation).map(([league,v])=>{
    const m=v.score_margin;
    return `${board.leagues[league]}: ${m ? pts(m.mae)+" pts margin MAE across "+m.n+" games" : "insufficient evaluation data"}.`;
  }).join(" ");
  draw();
}
async function results() {
  const data = await read("results");
  el("records").innerHTML = Object.keys(data.records).length ? `<div class="table-wrap"><table>
  <thead><tr><th>Scope</th><th>Wins</th><th>Losses</th><th>Pushes</th><th>Win %</th><th>Margin MAE</th></tr></thead><tbody>${
    Object.entries(data.records).map(([k,v])=>`<tr><th>${esc(k)}</th><td>${v.wins}</td><td>${v.losses}</td><td>${v.pushes}</td><td>${esc(v.win_pct)}</td><td>${esc(v.margin_mae)}</td></tr>`).join("")
  }</tbody></table></div>` : "<p>No settled first forecasts yet.</p>";
  el("receipts").innerHTML = data.receipts.map(r=>`<tr><th>${esc(r.away)} at ${esc(r.home)}</th><td><a href="${esc(r.receipt)}">${esc(stamp(r.captured))}</a>${r.first_market ? " · First market quote" : r.first ? "" : " · Revision"}</td><td>${esc(r.pick?.name ?? "Score projection")}</td><td>${r.final ? `${r.final.away}–${r.final.home}` : "Pending"}</td><td>${esc(r.grade ?? "—")}</td></tr>`).join("");
}
(el("results") ? results() : slate()).catch(() => {
  (el("records") || el("date")).textContent = "Published data could not be loaded.";
});
