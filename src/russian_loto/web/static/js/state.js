// Game state: shape, persistence, and mutators.
//
// State shape (persisted as JSON in localStorage at STORAGE_KEY):
//   called: sorted int[]                       -- every number called so far
//   events: [{ts, cid, seq, level, callCount}] -- newest first (unshifted)
//   cardLevel: { cid: 0..3 }                   -- last computed level per card
//   jackpot: int                               -- 0 = feature disabled
//   percentages: [p1, p2, p3]                  -- integers, sum = 100
//   split: bool                                -- on ties: split or host picks
//   tiebreakResolutions: { "level-callCount": cid }
//   cardRange: [lo, hi] | null                 -- active card-seq filter
//
// Mutators mutate the passed state in place and return { state, ...effects }.
// `state` in the return is the same reference; it's included so callers can
// cleanly chain or reassign without special-casing.

import * as logic from "./logic.js";

export const STORAGE_KEY = "loto-game-state";

export function freshState(overrides) {
  const base = {
    called: [],
    events: [],
    cardLevel: {},
    jackpot: 0,
    percentages: [10, 25, 65],
    split: true,
    tiebreakResolutions: {},
    cardRange: null,
  };
  return Object.assign(base, overrides || {});
}

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.called)) return null;
    // Back-fill fields added in later versions so old persisted state keeps working.
    if (parsed.jackpot === undefined) parsed.jackpot = 0;
    if (!Array.isArray(parsed.percentages)) parsed.percentages = [10, 25, 65];
    if (parsed.split === undefined) parsed.split = true;
    if (!parsed.tiebreakResolutions) parsed.tiebreakResolutions = {};
    if (parsed.cardRange === undefined) parsed.cardRange = null;
    return parsed;
  } catch (e) {
    return null;
  }
}

export function saveState(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    // localStorage may be unavailable in private mode; degrade silently
  }
}

export function nowHHMM() {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

// Reconcile cardLevel/events/tiebreakResolutions with the current called set.
// Mutates state in place. Returns the first card (by iteration order over
// `cards`, which callers provide seq-sorted) that crosses level 3 this call,
// or null. Used both on init (to fix stale cardLevel after a registry swap)
// and after every call/uncall.
export function recompute(state, cards, ts) {
  const called = logic.calledSet(state.called);
  const newLevels = {};
  const callCount = state.called.length;
  let bingoCard = null;

  for (const card of cards) {
    const prev = state.cardLevel[card.cid] || 0;
    const next = logic.levelOf(card, called);
    newLevels[card.cid] = next;

    if (next > prev) {
      // Crossed one or more thresholds upward; emit one event per new level.
      for (let lvl = prev + 1; lvl <= next; lvl++) {
        state.events.unshift({
          ts, cid: card.cid, seq: card.seq, level: lvl, callCount,
        });
        if (lvl === 3 && bingoCard === null) bingoCard = card;
      }
    } else if (next < prev) {
      // Reversed (uncall): drop log entries for levels above the new one and
      // any tiebreak resolutions that referred to rolled-back levels.
      state.events = state.events.filter(
        (e) => !(e.cid === card.cid && e.level > next),
      );
      const res = state.tiebreakResolutions || {};
      for (const key of Object.keys(res)) {
        const lvlStr = key.split("-")[0];
        if (parseInt(lvlStr, 10) > next && res[key] === card.cid) {
          delete res[key];
        }
      }
    }
  }
  state.cardLevel = newLevels;
  return bingoCard;
}

export function applyCallNumber(state, n, cards) {
  if (state.called.includes(n)) return { state, bingoCard: null };
  state.called.push(n);
  state.called.sort((a, b) => a - b);
  const bingoCard = recompute(state, cards, nowHHMM());
  return { state, bingoCard };
}

export function applyUncallNumber(state, n, cards) {
  const idx = state.called.indexOf(n);
  if (idx === -1) return { state };
  state.called.splice(idx, 1);
  // Uncall only decreases levels, so recompute never returns a bingo card here.
  recompute(state, cards, nowHHMM());
  return { state };
}

export function applyResolveTiebreak(state, key, cid) {
  if (!state.tiebreakResolutions) state.tiebreakResolutions = {};
  state.tiebreakResolutions[key] = cid;
  return { state };
}
