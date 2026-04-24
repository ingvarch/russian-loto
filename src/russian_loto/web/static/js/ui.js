// Admin page UI: DOM rendering and event handlers.
//
// Holds two pieces of mutable module state:
//   CARDS    -- immutable for the session (loaded from bootstrap JSON)
//   current  -- the live game state; mutated in place by state.js mutators
//               and reassigned on "new game" when the whole state is replaced
//
// All business logic lives in logic.js (pure) and state.js (mutators).
// This module only touches the DOM.

import * as logic from "./logic.js";
import * as state from "./state.js";

const LEVEL_LABELS = { 1: "одна линия", 2: "две линии", 3: "ПОЛНОЕ ЛОТО" };

// Loto column ranges: col 0 = 1..9 (9 numbers), cols 1..7 = 10..79 (10 each),
// col 8 = 80..90 (11 numbers). We use a 9x11 grid; short columns have placeholders
// in the bottom rows. Every number stays in its semantically correct column.
const GRID_ROWS = 11;
const GRID_COLS = 9;

let CARDS = [];
let current = null;

function active() { return logic.activeCards(CARDS, current.cardRange); }
function calledSet() { return logic.calledSet(current.called); }
function payouts() { return logic.computePayouts(current, active()); }
function formatAmount(n) { return (n || 0).toLocaleString("ru-RU"); }

// ---- Public entry point --------------------------------------------------

export function init({ cards, initialState }) {
  CARDS = cards;
  current = initialState;

  buildGrid();
  wireUncallModal();
  wireWinContinueModal();
  wireNewGameModal();
  wireWinOverlay();
  wireBottomSheet();

  // Reconcile stored state on load: cardLevel may be stale if CARDS changed
  // (e.g. the server restarted with a different registry). Recompute fresh
  // from the current called set.
  state.recompute(current, active(), state.nowHHMM());
  state.saveState(current);
  render();
}

// ---- Grid ----------------------------------------------------------------

const gridEl = document.getElementById("number-grid");
const logEl = document.getElementById("log");
const counterEl = document.getElementById("counter-called");

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
        cell.addEventListener("click", () => onCellClick(value));
      }
      gridEl.appendChild(cell);
    }
  }
}

function numberAt(col, row) {
  if (col === 0) return row < 9 ? row + 1 : null;    // 1..9, then 2 placeholders
  if (col === 8) return 80 + row;                     // 80..90, all 11 rows used
  return row < 10 ? col * 10 + row : null;            // 10..19, ..., 70..79, placeholder
}

function onCellClick(n) {
  if (current.called.includes(n)) {
    askUncall(n);
  } else {
    const { bingoCard } = state.applyCallNumber(current, n, active());
    state.saveState(current);
    render();
    if (bingoCard) {
      // If level-3 payout is pending (unresolved tiebreak), defer the overlay
      // until the host picks a winner -- resolveTiebreak will call showWin
      // with the correct winner.
      const p = payouts();
      if (p.status !== "active" || p.level3.status !== "pending") {
        showWin(bingoCard);
      }
    }
  }
}

// ---- Render --------------------------------------------------------------

function render() {
  renderCells();
  renderClose();
  renderPayout();
  renderLog();
  maybeShowTiebreak();
}

function renderCells() {
  const called = calledSet();
  for (const cell of gridEl.querySelectorAll(".cell[data-num]")) {
    const n = Number(cell.dataset.num);
    cell.classList.toggle("called", called.has(n));
  }
}

function renderLog() {
  counterEl.textContent = String(current.called.length);
  const activeList = active();
  document.getElementById("card-count").textContent = activeList.length + " карт";
  if (current.events.length === 0) {
    logEl.innerHTML = '<div class="log-empty">Событий пока нет</div>';
    return;
  }
  logEl.innerHTML = "";
  for (const e of current.events) {
    const row = document.createElement("div");
    row.className = "log-entry level-" + e.level;
    row.innerHTML =
      '<span class="ts">' + e.ts + '</span>' +
      '<span class="seq">#' + String(e.seq).padStart(3, "0") + '</span>' +
      '<span class="level">' + LEVEL_LABELS[e.level] + '</span>';
    row.addEventListener("click", () => openSheet(e.cid));
    logEl.appendChild(row);
  }
}

function renderClose() {
  const called = calledSet();
  const close = logic.closeCards(active(), called);
  const section = document.getElementById("close-section");
  const label = document.getElementById("close-label");
  const list = document.getElementById("close-list");
  if (close.length === 0) {
    section.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  section.classList.remove("hidden");
  label.textContent = "4 из 5 в линии (" + close.length + "):";
  close.sort((a, b) => a.seq - b.seq);
  list.innerHTML = "";
  for (const card of close) {
    const chip = document.createElement("span");
    chip.className = "close-chip";
    chip.textContent = "#" + String(card.seq).padStart(3, "0");
    chip.addEventListener("click", () => openSheet(card.cid));
    list.appendChild(chip);
  }
}

function renderPayout() {
  const section = document.getElementById("payout-section");
  const p = payouts();
  if (p.status !== "active") {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");

  const total = p.base1 + p.base2 + p.base3;
  document.getElementById("payout-total").textContent = formatAmount(total);

  const grid = document.getElementById("payout-grid");
  grid.innerHTML = "";
  grid.appendChild(renderPayoutRow(1, "одна линия", p.level1));
  grid.appendChild(renderPayoutRow(2, "две линии", p.level2));
  grid.appendChild(renderPayoutRow(3, "полное лото", p.level3));
}

function renderPayoutRow(level, label, info) {
  const row = document.createElement("div");
  row.className = "payout-row level-" + level;

  const levelEl = document.createElement("div");
  levelEl.className = "payout-level";
  levelEl.textContent = label;

  const winnersEl = document.createElement("div");
  winnersEl.className = "payout-winners";

  const amountEl = document.createElement("div");
  amountEl.className = "payout-amount";

  if (info.status === "unclaimed") {
    row.classList.add("unclaimed");
    winnersEl.textContent = "ждёт";
    amountEl.textContent = formatAmount(info.base);
  } else if (info.status === "pending") {
    row.classList.add("pending");
    const labelSpan = document.createElement("span");
    labelSpan.textContent = "ничья: ";
    winnersEl.appendChild(labelSpan);
    info.candidates.forEach((card) => {
      const chip = document.createElement("span");
      chip.className = "chip-sm";
      chip.textContent = "#" + String(card.seq).padStart(3, "0");
      chip.addEventListener("click", () => openSheet(card.cid));
      winnersEl.appendChild(chip);
    });
    amountEl.textContent = formatAmount(info.base);
  } else if (info.status === "paid") {
    info.winners.forEach((card) => {
      const chip = document.createElement("span");
      chip.className = "chip-sm";
      chip.textContent = "#" + String(card.seq).padStart(3, "0");
      chip.addEventListener("click", () => openSheet(card.cid));
      winnersEl.appendChild(chip);
    });
    const perPersonText = formatAmount(info.perPerson);
    if (info.winners.length > 1) {
      amountEl.textContent = perPersonText + " × " + info.winners.length;
    } else {
      // Single winner: they get perPerson + remainder (at final level) or just base
      const amt = info.perPerson + (info.absorbFinalRemainder ? info.remainder : 0);
      amountEl.textContent = formatAmount(amt);
    }
    if (info.absorbFinalRemainder && info.winners.length > 1 && info.remainder > 0) {
      // First winner gets the remainder bonus
      const note = document.createElement("div");
      note.style.fontSize = "11px";
      note.style.color = "var(--text-dim)";
      note.style.marginTop = "2px";
      note.textContent = "#" + String(info.winners[0].seq).padStart(3, "0") + " +" + info.remainder;
      amountEl.appendChild(note);
    }
  }

  row.appendChild(levelEl);
  row.appendChild(winnersEl);
  row.appendChild(amountEl);
  return row;
}

// ---- Confirm-uncall modal ------------------------------------------------

let pendingUncall = null;

function askUncall(n) {
  pendingUncall = n;
  document.getElementById("confirm-uncall-num").textContent = String(n);
  document.getElementById("confirm-uncall").classList.add("open");
}

function setupModal(id, onConfirm) {
  const modal = document.getElementById(id);
  modal.querySelector('[data-action="cancel"]').addEventListener("click", () => {
    modal.classList.remove("open");
  });
  modal.querySelector('[data-action="confirm"]').addEventListener("click", () => {
    modal.classList.remove("open");
    onConfirm();
  });
  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) modal.classList.remove("open");
  });
}

function wireUncallModal() {
  setupModal("confirm-uncall", () => {
    if (pendingUncall !== null) {
      state.applyUncallNumber(current, pendingUncall, active());
      state.saveState(current);
      render();
      pendingUncall = null;
    }
  });
}

function wireWinContinueModal() {
  setupModal("confirm-win-continue", closeWin);
}

// ---- New-game modal ------------------------------------------------------

function openNewGameModal() {
  // Pre-fill form with current settings (or defaults if none).
  document.getElementById("ng-jackpot").value = current.jackpot || 0;
  document.getElementById("ng-pct1").value = (current.percentages && current.percentages[0]) || 10;
  document.getElementById("ng-pct2").value = (current.percentages && current.percentages[1]) || 25;
  document.getElementById("ng-pct3").value = (current.percentages && current.percentages[2]) || 65;
  document.getElementById("ng-split").checked = current.split !== false;
  document.getElementById("ng-error").textContent = "";
  const cardsInput = document.getElementById("ng-cards");
  if (current.cardRange) {
      cardsInput.value = current.cardRange[0] + "-" + current.cardRange[1];
  } else {
      cardsInput.value = "";
  }
  const allSeqs = CARDS.map((c) => c.seq);
  const minSeq = Math.min(...allSeqs);
  const maxSeq = Math.max(...allSeqs);
  document.getElementById("ng-cards-hint").textContent =
      "Загружено: №" + String(minSeq).padStart(3, "0") +
      "–№" + String(maxSeq).padStart(3, "0") +
      ", всего " + CARDS.length;
  syncPresetActive();
  updateNewGamePreview();
  document.getElementById("new-game-modal").classList.add("open");
}

function closeNewGameModal() {
  document.getElementById("new-game-modal").classList.remove("open");
}

function readNewGameForm() {
  const jackpot = parseInt(document.getElementById("ng-jackpot").value, 10) || 0;
  const pct1 = parseInt(document.getElementById("ng-pct1").value, 10);
  const pct2 = parseInt(document.getElementById("ng-pct2").value, 10);
  const pct3 = parseInt(document.getElementById("ng-pct3").value, 10);
  const split = document.getElementById("ng-split").checked;
  const cardsRaw = document.getElementById("ng-cards").value.trim();
  return { jackpot, percentages: [pct1, pct2, pct3], split, cardRange: cardsRaw || null };
}

function validateNewGameForm() {
  const form = readNewGameForm();
  const err = document.getElementById("ng-error");
  if (form.jackpot < 0 || isNaN(form.jackpot)) {
    err.textContent = "Банк должен быть 0 или больше.";
    return null;
  }
  const pcts = form.percentages;
  if (pcts.some((p) => isNaN(p) || p < 0 || p > 100)) {
    err.textContent = "Проценты должны быть от 0 до 100.";
    return null;
  }
  const sum = pcts[0] + pcts[1] + pcts[2];
  if (sum !== 100) {
    err.textContent = "Сумма процентов должна быть ровно 100 (сейчас " + sum + ").";
    return null;
  }
  if (form.cardRange) {
      const raw = form.cardRange;
      const rangeMatch = raw.match(/^(\d+)\s*-\s*(\d+)$/);
      const singleMatch = raw.match(/^(\d+)$/);
      if (rangeMatch) {
          const lo = parseInt(rangeMatch[1], 10);
          const hi = parseInt(rangeMatch[2], 10);
          if (lo < 1 || hi < 1 || lo > hi) {
              err.textContent = "Неверный диапазон карт.";
              return null;
          }
          form.cardRange = [lo, hi];
      } else if (singleMatch) {
          const n = parseInt(singleMatch[1], 10);
          if (n < 1) {
              err.textContent = "Номер карты должен быть >= 1.";
              return null;
          }
          form.cardRange = [n, n];
      } else {
          err.textContent = "Формат диапазона: 1-25 или одно число.";
          return null;
      }
      const [lo, hi] = form.cardRange;
      const count = CARDS.filter((c) => c.seq >= lo && c.seq <= hi).length;
      if (count === 0) {
          err.textContent = "Ни одной загруженной карты в этом диапазоне.";
          return null;
      }
  }
  err.textContent = "";
  return form;
}

function updateNewGamePreview() {
  const form = readNewGameForm();
  const preview = document.getElementById("ng-preview");
  if (form.jackpot > 0 && form.percentages.every((p) => !isNaN(p))) {
    const sum = form.percentages[0] + form.percentages[1] + form.percentages[2];
    if (sum === 100) {
      const b1 = Math.floor((form.jackpot * form.percentages[0]) / 100);
      const b2 = Math.floor((form.jackpot * form.percentages[1]) / 100);
      const b3 = form.jackpot - b1 - b2;
      document.getElementById("ng-preview-1").textContent = b1.toLocaleString("ru-RU");
      document.getElementById("ng-preview-2").textContent = b2.toLocaleString("ru-RU");
      document.getElementById("ng-preview-3").textContent = b3.toLocaleString("ru-RU");
      preview.classList.remove("hidden");
      return;
    }
  }
  preview.classList.add("hidden");
}

function applyPreset(btn) {
  const pctStr = btn.dataset.pct;
  if (pctStr) {
    const pcts = pctStr.split(",").map((s) => parseInt(s, 10));
    document.getElementById("ng-pct1").value = pcts[0];
    document.getElementById("ng-pct2").value = pcts[1];
    document.getElementById("ng-pct3").value = pcts[2];
  }
  syncPresetActive();
  updateNewGamePreview();
  validateNewGameForm();
}

function syncPresetActive() {
  const p1 = parseInt(document.getElementById("ng-pct1").value, 10);
  const p2 = parseInt(document.getElementById("ng-pct2").value, 10);
  const p3 = parseInt(document.getElementById("ng-pct3").value, 10);
  const currentPct = [p1, p2, p3].join(",");
  const buttons = document.querySelectorAll("#ng-presets button");
  let matched = false;
  buttons.forEach((btn) => {
    if (btn.dataset.pct === currentPct) {
      btn.classList.add("active");
      matched = true;
    } else {
      btn.classList.remove("active");
    }
  });
  if (!matched) {
    // Highlight "Свой" if no preset matches
    const customBtn = document.querySelector('#ng-presets button[data-preset="custom"]');
    if (customBtn) customBtn.classList.add("active");
  }
}

function wireNewGameModal() {
  ["ng-jackpot", "ng-pct1", "ng-pct2", "ng-pct3"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      syncPresetActive();
      updateNewGamePreview();
      validateNewGameForm();
    });
  });
  document.querySelectorAll("#ng-presets button").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      applyPreset(btn);
    });
  });

  const newGameModalEl = document.getElementById("new-game-modal");
  newGameModalEl.querySelector('[data-action="cancel"]').addEventListener("click", closeNewGameModal);
  newGameModalEl.querySelector('[data-action="confirm"]').addEventListener("click", () => {
    const form = validateNewGameForm();
    if (form === null) return;
    current = state.freshState(form);
    state.saveState(current);
    render();
    closeWin();
    closeNewGameModal();
  });
  newGameModalEl.addEventListener("click", (ev) => {
    if (ev.target === newGameModalEl) closeNewGameModal();
  });

  document.getElementById("new-game-btn").addEventListener("click", openNewGameModal);
}

// ---- Tiebreak modal ------------------------------------------------------

function maybeShowTiebreak() {
  const modal = document.getElementById("tiebreak-modal");
  const grid = document.getElementById("number-grid");
  const p = payouts();

  // Find the first pending level (lowest level number wins).
  let pending = null;
  if (p.status === "active") {
    for (const lvl of [1, 2, 3]) {
      const info = p["level" + lvl];
      if (info && info.status === "pending") {
        pending = { level: lvl, info };
        break;
      }
    }
  }

  if (!pending) {
    modal.classList.remove("open");
    grid.classList.remove("blocked");
    return;
  }

  const levelLabel = LEVEL_LABELS[pending.level];
  document.getElementById("tiebreak-title").textContent = "Ничья: " + levelLabel;
  const candidatesEl = document.getElementById("tiebreak-candidates");
  candidatesEl.innerHTML = "";
  for (const card of pending.info.candidates) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tiebreak-btn";
    const seqSpan = document.createElement("span");
    seqSpan.textContent = "#" + String(card.seq).padStart(3, "0");
    const cidSpan = document.createElement("span");
    cidSpan.className = "tiebreak-cid";
    cidSpan.textContent = card.cid;
    btn.appendChild(seqSpan);
    btn.appendChild(cidSpan);
    btn.addEventListener("click", () => resolveTiebreak(pending.info.tiebreakKey, card.cid));
    candidatesEl.appendChild(btn);
  }
  modal.classList.add("open");
  grid.classList.add("blocked");
}

function resolveTiebreak(key, cid) {
  state.applyResolveTiebreak(current, key, cid);
  state.saveState(current);
  render();
  // If we just resolved a level-3 tiebreak, the win overlay was deferred by
  // onCellClick and needs to fire now with the chosen winner.
  const lvl = parseInt(key.split("-")[0], 10);
  if (lvl === 3) {
    const winner = CARDS.find((c) => c.cid === cid);
    if (winner) showWin(winner);
  }
}

// ---- Win overlay ---------------------------------------------------------

function showWin(card) {
  document.getElementById("win-seq").textContent = "#" + String(card.seq).padStart(3, "0");
  document.getElementById("win-cid").textContent = card.cid;

  const amountEl = document.getElementById("win-amount");
  const amountValueEl = document.getElementById("win-amount-value");
  const noteEl = document.getElementById("win-amount-note");
  const p = payouts();
  if (
    p.status === "active" &&
    p.level3.status === "paid" &&
    p.level3.winners.some((w) => w.cid === card.cid)
  ) {
    let amount = p.level3.perPerson;
    if (
      p.level3.absorbFinalRemainder &&
      p.level3.remainder > 0 &&
      p.level3.winners[0].cid === card.cid
    ) {
      amount += p.level3.remainder;
    }
    amountValueEl.textContent = formatAmount(amount);
    if (p.level3.winners.length > 1) {
      const others = p.level3.winners.length - 1;
      noteEl.textContent = "Ничья, доля из " + formatAmount(p.level3.base) +
        " (ещё " + others + " победител" + (others === 1 ? "ь" : "ей") + ")";
      noteEl.classList.remove("hidden");
    } else {
      noteEl.classList.add("hidden");
    }
    amountEl.classList.remove("hidden");
  } else {
    amountEl.classList.add("hidden");
  }

  document.getElementById("win-backdrop").classList.add("open");
}

function closeWin() {
  document.getElementById("win-backdrop").classList.remove("open");
}

function wireWinOverlay() {
  document.getElementById("win-continue-btn").addEventListener("click", () => {
    document.getElementById("confirm-win-continue").classList.add("open");
  });
  document.getElementById("win-new-game-btn").addEventListener("click", openNewGameModal);
}

// ---- Bottom sheet --------------------------------------------------------

function openSheet(cid) {
  const card = CARDS.find((c) => c.cid === cid);
  if (!card) return;
  const called = calledSet();
  const closed = card.numbers.filter((n) => called.has(n)).length;
  const level = current.cardLevel[cid] || 0;

  document.getElementById("sheet-seq").textContent = "#" + String(card.seq).padStart(3, "0");
  document.getElementById("sheet-cid").textContent = card.cid;
  document.getElementById("sheet-stars").textContent = renderStars(level);
  document.getElementById("sheet-progress").textContent = closed + "/15";

  const cardEl = document.getElementById("sheet-card");
  cardEl.innerHTML = "";
  for (let r = 0; r < 3; r++) {
    const row = card.rows[r];
    for (let c = 0; c < 9; c++) {
      const cell = document.createElement("div");
      cell.className = "card-cell";
      const val = row[c];
      if (val === null) {
        cell.classList.add("empty");
      } else {
        cell.textContent = String(val);
        if (called.has(val)) cell.classList.add("closed");
      }
      cardEl.appendChild(cell);
    }
  }

  document.getElementById("sheet-backdrop").classList.add("open");
  document.getElementById("sheet").classList.add("open");
}

function closeSheet() {
  document.getElementById("sheet").classList.remove("open");
  document.getElementById("sheet-backdrop").classList.remove("open");
}

function renderStars(level) {
  const filled = "★".repeat(level);
  const empty = "☆".repeat(3 - level);
  return filled + empty;
}

function wireBottomSheet() {
  const sheet = document.getElementById("sheet");
  const sheetBackdrop = document.getElementById("sheet-backdrop");

  sheetBackdrop.addEventListener("click", closeSheet);

  // Swipe-down to dismiss
  let touchStartY = null;
  sheet.addEventListener("touchstart", (e) => { touchStartY = e.touches[0].clientY; }, { passive: true });
  sheet.addEventListener("touchmove", (e) => {
    if (touchStartY === null) return;
    const dy = e.touches[0].clientY - touchStartY;
    if (dy > 60) { closeSheet(); touchStartY = null; }
  }, { passive: true });
  sheet.addEventListener("touchend", () => { touchStartY = null; });
}
