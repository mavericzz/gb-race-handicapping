const state = { card: null, meeting: 0, race: 0 };

const $ = (id) => document.getElementById(id);

function fmtOdds(v) {
  if (v == null) return "—";
  return Number(v).toFixed(2);
}
function pct(v) {
  if (v == null) return "—";
  return `${(Number(v) * 100).toFixed(1)}%`;
}
function money(stakePct) {
  const bank = Number($("bankroll").value || 0);
  if (!stakePct) return "—";
  return `£${((bank * Number(stakePct)) / 100).toFixed(2)}`;
}

function lastLine(runner) {
  const last = runner.last_run || {};
  const bits = [];
  if (last.finish) bits.push(`${last.finish}${last.beaten_lengths != null ? ` beaten ${last.beaten_lengths}L` : ""}`);
  if (last.track) bits.push(last.track);
  if (last.weight_kg) bits.push(`${last.weight_kg}kg last`);
  if (last.going) bits.push(last.going);
  return bits.join(" · ") || "No last-run line";
}

function renderPlays() {
  const plays = state.card.plays || [];
  const el = $("plays-strip");
  if (!plays.length) {
    el.innerHTML = `<div class="play-chip"><b>NO PLAYS YET</b><span>Run a scrape or wait for overlay edges.</span></div>`;
    return;
  }
  el.innerHTML = plays.map((p, i) => `
    <div class="play-chip" data-i="${i}">
      <b>PLAY · ${p.venue || ""} R${p.race_number}</b>
      <span>${p.name}</span>
      <small>${fmtOdds(p.odds)} · edge ${(p.edge * 100).toFixed(0)}% · ${money(p.stake_pct)}</small>
    </div>
  `).join("");
  el.querySelectorAll(".play-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const play = plays[Number(chip.dataset.i)];
      const mi = (state.card.meetings || []).findIndex((m) => m.venue === play.venue);
      if (mi < 0) return;
      state.meeting = mi;
      state.race = (state.card.meetings[mi].races || []).findIndex((r) => r.race_number === play.race_number);
      render();
    });
  });
}

function renderMeetings() {
  const nav = $("meetings");
  nav.innerHTML = (state.card.meetings || []).map((m, i) =>
    `<button class="${i === state.meeting ? "active" : ""}" data-i="${i}">${m.venue}</button>`
  ).join("");
  nav.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.meeting = Number(btn.dataset.i);
      state.race = 0;
      render();
    });
  });
}

function renderRaces() {
  const meeting = (state.card.meetings || [])[state.meeting];
  const box = $("races");
  if (!meeting) { box.innerHTML = ""; return; }
  box.innerHTML = (meeting.races || []).map((r, i) => `
    <button class="${i === state.race ? "active" : ""}" data-i="${i}">
      R${r.race_number} ${r.off_time || ""}
      <small>${r.name || ""}</small>
    </button>
  `).join("");
  box.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.race = Number(btn.dataset.i);
      render();
    });
  });
}

function renderSheet() {
  const meeting = (state.card.meetings || [])[state.meeting];
  const race = meeting && (meeting.races || [])[state.race];
  const sheet = $("sheet");
  if (!race) {
    sheet.innerHTML = `<div class="empty">No race loaded. Click Rescrape for Saturday's GB meetings.</div>`;
    return;
  }
  const rows = (race.runners || []).map((r) => `
    <tr class="${(r.action || "").toLowerCase()}">
      <td class="num">${r.rank || ""}</td>
      <td class="num">${r.number || ""}</td>
      <td>
        <div class="horse">${r.name}</div>
        <details><summary>${lastLine(r)}</summary>
          <div>Figure ${r.figure ?? "—"} · base ${r.base ?? "—"} · sectional ${r.sectional ?? "—"} · draw ${r.draw ?? "—"} · going ${r.going ?? "—"} · wt swing ${r.weight_swing ?? "—"}lb · today ${r.weight_kg ?? "—"}kg</div>
        </details>
      </td>
      <td class="num">${r.barrier ?? "—"}</td>
      <td class="num">${r.weight_kg ?? "—"}</td>
      <td class="num">${r.rating ?? "—"}</td>
      <td class="num">${r.figure ?? "—"}</td>
      <td class="num">${pct(r.p_model)}</td>
      <td class="num">${fmtOdds(r.odds)}</td>
      <td class="num ${r.edge > 0 ? "edge-pos" : ""}">${r.edge == null ? "—" : `${(r.edge * 100).toFixed(0)}%`}</td>
      <td class="num">${money(r.stake_pct)}</td>
      <td class="action">${r.action || ""}</td>
    </tr>
  `).join("");
  sheet.innerHTML = `
    <h2>R${race.race_number} · ${race.name}</h2>
    <div class="meta">${meeting.venue} · ${race.going || ""} · ${race.distance_m || ""}m · win market overlay</div>
    <table>
      <thead>
        <tr>
          <th>#</th><th>No</th><th>Horse / last run</th><th>Dr</th><th>Wgt kg</th>
          <th>Rtg</th><th>Fig</th><th>Model</th><th>Odds</th><th>Edge</th><th>Stake</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function render() {
  const nMeet = (state.card.meetings || []).length;
  const nPlay = (state.card.plays || []).length;
  $("card-meta").textContent = `${state.card.date || ""} · ${nMeet} meetings · ${nPlay} win plays`;
  renderPlays();
  renderMeetings();
  renderRaces();
  renderSheet();
}

async function load() {
  const res = await fetch("/api/card");
  state.card = await res.json();
  state.meeting = 0;
  state.race = 0;
  render();
}

$("bankroll").addEventListener("input", render);
$("rescrape").addEventListener("click", async () => {
  $("card-meta").textContent = "Scraping Punters + Racing & Sports…";
  await fetch("/api/scrape", { method: "POST" });
  const poll = setInterval(async () => {
    const st = await fetch("/api/status").then((r) => r.json());
    if (!st.running) {
      clearInterval(poll);
      await load();
    }
  }, 4000);
});

load().catch((err) => {
  $("card-meta").textContent = `Failed to load card: ${err}`;
});
