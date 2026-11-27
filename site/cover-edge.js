"use strict";
const el = id => document.getElementById("edge-" + id);
const central = new Intl.DateTimeFormat("sv-SE", {timeZone:"America/Chicago",year:"numeric",month:"2-digit",day:"2-digit"});
const clock = new Intl.DateTimeFormat("en-US", {timeZone:"America/Chicago",hour:"numeric",minute:"2-digit"});
const leagueNames = {nba:"NBA","mens-college-basketball":"Men’s College","womens-college-basketball":"Women’s College"};
const percent = value => value == null ? "—" : (100 * value).toFixed(1) + "%";
const signed = value => value == null ? "—" : (value > 0 ? "+" : "") + value;
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[ch]);
let board, results, archived = new Map();
function dateAt(offset) {
  const date = new Date(central.format(new Date()) + "T18:00Z");
  date.setUTCDate(date.getUTCDate() + offset);
  return central.format(date);
}
function normal(value) {
  const a = Math.abs(value);
  const t = 1 / (1 + 0.2316419 * a);
  const tail = Math.exp(-a*a/2) / Math.sqrt(2*Math.PI) * t *
    (0.319381530 + t*(-0.356563782 + t*(1.781477937 + t*(-1.821255978 + t*1.330274429))));
  return value >= 0 ? 1-tail : tail;
}
function evaluate(quote, projection, validation, final) {
  const {side,line,odds} = quote;
  const other = side === "home" ? "away" : "home";
  let cover = null, push = null, needed = null, grade = null;
  if (Number.isFinite(line) && validation?.n >= 30 && validation.rmse > 0 &&
      Number.isFinite(projection?.[side]) && Number.isFinite(projection?.[other])) {
    const margin = projection[side] - projection[other];
    const threshold = -line;
    const cdf = x => normal((x-margin)/validation.rmse);
    cover = 1-cdf(Math.floor(threshold)+0.5);
    push = Number.isInteger(threshold) ? cdf(threshold+0.5)-cdf(threshold-0.5) : 0;
  }
  if (Number.isFinite(odds) && Math.abs(odds) >= 100) {
    const price = odds < 0 ? -odds/(100-odds) : 100/(100+odds);
    needed = price*(1-(push ?? 0));
  }
  if (Number.isFinite(line) && Number.isFinite(final?.[side]) && Number.isFinite(final?.[other])) {
    const settled = final[side] - final[other] + line;
    grade = settled > 0 ? "Cover" : settled < 0 ? "Loss" : "Push";
  }
  return {...quote,cover,push,needed,grade,edge:cover == null || needed == null ? null : cover-needed};
}
function receiptQuotes(receipt) {
  return receipt?.cover_market ?? (receipt?.pick?.type === "spread" ? [receipt.pick] : []);
}
function matchup(game, receipt, period, isArchive) {
  const half = period === "half_spread";
  const key = half ? "half_margin" : "score_margin";
  const projection = half ? receipt?.first_half : receipt?.projection;
  const validation = receipt?.cover_validation?.[key] ?? (!half ? receipt?.pick?.validation : null) ?? (!isArchive ? board.validation?.[game.league]?.[key] : null);
  const quotes = isArchive ? receiptQuotes(receipt) : game.market ?? [];
  const final = half ? receipt?.halftime : receipt?.final;
  const sides = quotes.filter(q => q.type === period && ["away","home"].includes(q.side))
    .map(q => evaluate(q, projection, validation, final));
  return {game,receipt,projection,validation,final,sides,edge:Math.max(-Infinity,...sides.map(q => q.edge ?? -Infinity))};
}
function card(row) {
  const {game,receipt,projection,validation,final,sides} = row;
  const team = side => game[side]?.name ?? game[side];
  const name = escapeHtml(team("away")) + " at " + escapeHtml(team("home"));
  const heading = "<small>"+leagueNames[game.league]+" · "+clock.format(new Date(game.tip))+" CT</small><h2>"+name+"</h2>";
  const score = projection ? "<p>Projected score <strong>"+projection.away.toFixed(1)+"–"+projection.home.toFixed(1)+"</strong></p>" : "";
  const actual = Number.isFinite(final?.away) && Number.isFinite(final?.home) ? "<p>Actual score <strong>"+final.away+"–"+final.home+"</strong></p>" : "";
  const rows = sides.map(q => {
    const css = q.edge > 0 ? "edge-positive" : q.edge < 0 ? "edge-negative" : "";
    const edge = q.edge == null ? "—" : signed(Number((100*q.edge).toFixed(1)))+" pp";
    return "<tr><td>"+escapeHtml(team(q.side))+"<br><small>"+escapeHtml(q.provider)+"</small></td><td>"+signed(q.line)+"<br><small>"+signed(q.odds)+"</small></td><td>"+percent(q.cover)+"</td><td>"+percent(q.needed)+"</td><td class='"+css+"'>"+edge+"</td>"+(actual?"<td>"+(q.grade??"—")+"</td>":"")+"</tr>";
  }).join("");
  const table = rows ? "<table><thead><tr><th>Side</th><th>Spread</th><th>Cover</th><th>Needed</th><th>Edge</th>"+(actual?"<th>Grade</th>":"")+"</tr></thead><tbody>"+rows+"</tbody></table>" : "<p class='edge-foot'>Spread price unavailable for this period.</p>";
  const details = receipt ? "<details><summary>Forecast details</summary><p>Pregame forecast "+clock.format(new Date(receipt.captured))+" CT"+(validation?.rmse?" · Margin RMSE "+validation.rmse+" across "+validation.n+" backtest games":"")+".</p></details>" : "";
  return "<article class='edge-card'>"+heading+score+actual+table+details+"</article>";
}
function render() {
  if (!board) return;
  const date = el("date").value;
  const past = date < dateAt(0), league = el("league").value, period = el("period").value;
  const games = past ? [...archived.values()].filter(r => central.format(new Date(r.tip)) === date) :
    board.games.filter(g => g.day === date);
  const rows = games.filter(g => !league || g.league === league)
    .map(g => {
      const isArchive = past || g.status !== "STATUS_SCHEDULED";
      const receipt = past ? g : archived.get(g.id) ?? g.forecast;
      return matchup(g, receipt, period, isArchive);
    });
  rows.sort((a,b) => (el("sort").value === "edge" ? b.edge-a.edge : 0) || a.game.tip.localeCompare(b.game.tip));
  el("status").textContent = rows.length+" matchups · "+rows.filter(r=>r.sides.some(s=>s.edge!=null)).length+" with calculated cover edges"+(past?" · Archived pregame receipts":" · Board updated "+clock.format(new Date(board.generated))+" CT");
  el("games").innerHTML = rows.length ? rows.map(card).join("") : "<p>No published matchups for this date and league.</p>";
}
function setDate(value) {
  el("date").value = value;
  document.querySelectorAll("[data-offset]").forEach(button => button.setAttribute("aria-pressed",dateAt(+button.dataset.offset) === value));
  render();
}
async function refresh() {
  try {
    const response = await fetch("data/board.json",{cache:"no-cache"});
    if (!response.ok) throw Error("Board unavailable");
    board = await response.json();
    const archive = await fetch("data/results.json",{cache:"no-cache"});
    if (archive.ok) {
      results = await archive.json();
      archived = new Map();
      for (const r of results.receipts) if (!archived.has(r.game_id)) archived.set(r.game_id,r);
    }
    render();
  } catch {
    el("status").textContent = "Could not refresh the published board.";
  }
}
document.querySelectorAll("[data-offset]").forEach(button => button.onclick = () => setDate(dateAt(+button.dataset.offset)));
el("date").onchange = () => setDate(el("date").value);
for (const id of ["league","period","sort"]) el(id).onchange = render;
setDate(dateAt(0));
refresh();
setInterval(() => { if (!document.hidden) refresh(); },180000);
