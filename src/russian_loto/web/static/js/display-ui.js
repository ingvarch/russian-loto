import * as logic from "./logic.js";

const GRID_ROWS = 11;
const GRID_COLS = 9;

let CARDS = [];
let serverRange = null;

const gridEl = document.getElementById("number-grid");
const counterEl = document.getElementById("counter-called");
const statusEl = document.getElementById("status");

function numberAt(col, row) {
  if (col === 0) return row < 9 ? row + 1 : null;
  if (col === 8) return 80 + row;
  return row < 10 ? col * 10 + row : null;
}

function buildGrid() {
  gridEl.innerHTML = "";
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const cell = document.createElement("div");
      cell.className = "cell";
      const value = numberAt(c, r);
      if (value === null) {
        cell.classList.add("placeholder");
      } else {
        cell.textContent = String(value);
        cell.dataset.num = String(value);
      }
      gridEl.appendChild(cell);
    }
  }
}

function formatAmount(n) { return (n || 0).toLocaleString("ru-RU"); }

function renderPrize(gameState, cards) {
  const section = document.getElementById("prize-section");
  if (!section) return;
  const payouts = logic.computePayouts(gameState, cards);
  if (payouts.status !== "active") {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  const total = (payouts.base1 || 0) + (payouts.base2 || 0) + (payouts.base3 || 0);
  document.getElementById("prize-total").textContent = formatAmount(total);
  document.getElementById("prize-1").textContent = formatAmount(payouts.base1);
  document.getElementById("prize-2").textContent = formatAmount(payouts.base2);
  document.getElementById("prize-3").textContent = formatAmount(payouts.base3);
}

// Display winners via resolveLevel so host-picked tiebreak winners are shown
// (not just first-by-seq from the raw event log).
function renderWinners(gameState, cards) {
  for (const lvl of [1, 2, 3]) {
    const row = document.getElementById(`winner-${lvl}`);
    if (!row) continue;
    const seqEl = row.querySelector(".winner-seq");
    const r = logic.resolveLevel(gameState, cards, lvl);
    if (r.status === "decided" && r.winners.length >= 1) {
      row.classList.add("won");
      // For split=true ties we show the first (lowest seq); callers already
      // sorted. For split=false the resolve result collapses to a single
      // winner once the host picks, so this works uniformly.
      seqEl.textContent = `№ ${r.winners[0].seq}`;
    } else {
      row.classList.remove("won");
      seqEl.textContent = "—";
    }
  }
}

function render(gameState) {
  if (!gameState) return;

  const called = logic.calledSet(gameState.called || []);
  const cards = logic.activeCards(CARDS, gameState.cardRange || serverRange);
  const lastCalled =
    gameState.called && gameState.called.length > 0
      ? gameState.called[gameState.called.length - 1]
      : null;

  counterEl.textContent = String(called.size);

  for (const cell of gridEl.children) {
    const num = Number(cell.dataset.num);
    if (!num) continue;
    cell.classList.toggle("called", called.has(num));
    cell.classList.toggle("last-called", num === lastCalled);
  }

  renderPrize(gameState, cards);

  const closeCounts = logic.closeCountsByLevel(cards, called);
  for (const lvl of [1, 2, 3]) {
    const el = document.getElementById(`close-${lvl}`);
    if (el) el.textContent = String(closeCounts[lvl]);
  }

  renderWinners(gameState, cards);
}

export function setConnected(connected) {
  statusEl.textContent = connected ? "" : "reconnecting…";
  statusEl.classList.toggle("connected", connected);
}

export function init({ cards, range }) {
  CARDS = cards;
  serverRange = range;
  buildGrid();
}

export { render };
