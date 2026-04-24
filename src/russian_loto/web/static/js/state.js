// Game state: shape, persistence, and mutators.
//
// State shape (persisted as JSON in localStorage at STORAGE_KEY):
//   called: sorted int[]                       -- every number called so far
//   events: [{ts, cid, seq, level, callCount, status}]  -- newest first
//                                                 status: "pending" |
//                                                 "confirmed" | "absent"
//   cardLevel: { cid: 0..3 }                   -- last computed level per card
//   jackpot: int                               -- 0 = feature disabled
//   percentages: [p1, p2, p3]                  -- integers, sum = 100
//   split: bool                                -- on ties: split or host picks
//   cardRange: [lo, hi] | null                 -- active card-seq filter
//   levelAutoConfirm: {1: bool, 2: bool, 3: bool}
//                                              -- once the admin confirms ANY
//                                                 card at level L is playing,
//                                                 later level-L crossings are
//                                                 auto-confirmed (no modal).
//                                                 Marking a card absent does
//                                                 not flip the flag.
//   tiebreakWinners: { "<level>:<callCount>": cid }
//                                              -- when split=false and several
//                                                 cards tie, the host picks
//                                                 one via a mini game and the
//                                                 choice is recorded here.
//
// Every level crossing creates an event that the admin either confirms or
// marks absent. Only "confirmed" events determine winners. The grid blocks
// while any event is pending, so no more numbers can be called until the
// admin resolves the crossing. After the first confirmation at a level the
// flow fast-paths: later crossings at that level skip the modal entirely.
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
    cardRange: null,
    levelAutoConfirm: { 1: false, 2: false, 3: false },
    tiebreakWinners: {},
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
    if (parsed.cardRange === undefined) parsed.cardRange = null;
    if (!parsed.levelAutoConfirm || typeof parsed.levelAutoConfirm !== "object") {
      // For old saves that pre-date the auto-confirm flow: if the admin has
      // already confirmed some events at a level, treat that level as
      // already-established (autoConfirm=true). This matches the user's
      // expectation that once a level has been validated once, subsequent
      // crossings should not re-prompt.
      parsed.levelAutoConfirm = { 1: false, 2: false, 3: false };
      for (const e of parsed.events || []) {
        if (e.status === "confirmed" && parsed.levelAutoConfirm[e.level] !== undefined) {
          parsed.levelAutoConfirm[e.level] = true;
        }
      }
    }
    if (!parsed.tiebreakWinners || typeof parsed.tiebreakWinners !== "object") {
      parsed.tiebreakWinners = {};
    }
    // Legacy events (pre-confirmation-flow) are auto-confirmed so in-progress
    // games keep their historical winners rather than flipping to "pending".
    if (Array.isArray(parsed.events)) {
      for (const e of parsed.events) {
        if (e.status === undefined) e.status = "confirmed";
      }
    }
    // tiebreakResolutions is a legacy field from the pre-confirmation tiebreak
    // flow; drop it silently so old persisted state loads cleanly.
    delete parsed.tiebreakResolutions;
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

// Reconcile cardLevel and events with the current called set. Mutates state
// in place. New level crossings are emitted as "pending" events -- the UI
// must present them for admin confirmation before they count as winners.
// Returns true if any new pending events were emitted this call; the caller
// uses this to decide whether to defer win overlays until confirmation.
// Used both on init (to fix stale cardLevel after a registry swap) and
// after every call/uncall.
export function recompute(state, cards, ts) {
  const called = logic.calledSet(state.called);
  const newLevels = {};
  const callCount = state.called.length;
  let newPending = false;

  for (const card of cards) {
    const prev = state.cardLevel[card.cid] || 0;
    const next = logic.levelOf(card, called);
    newLevels[card.cid] = next;

    if (next > prev) {
      // Crossed one or more thresholds upward; emit one event per new level.
      // If the admin has already confirmed some card at this level, new
      // crossings short-circuit to "confirmed" so we skip the modal entirely.
      for (let lvl = prev + 1; lvl <= next; lvl++) {
        const autoConfirmed = !!(state.levelAutoConfirm && state.levelAutoConfirm[lvl]);
        state.events.unshift({
          ts, cid: card.cid, seq: card.seq, level: lvl, callCount,
          status: autoConfirmed ? "confirmed" : "pending",
        });
        if (!autoConfirmed) newPending = true;
      }
    } else if (next < prev) {
      // Reversed (uncall): drop log entries for levels above the new one.
      // This covers both pending and already-resolved events -- if the card
      // is no longer at that level, the event shouldn't be recorded at all.
      state.events = state.events.filter(
        (e) => !(e.cid === card.cid && e.level > next),
      );
    }
  }
  state.cardLevel = newLevels;
  return newPending;
}

export function applyCallNumber(state, n, cards) {
  if (state.called.includes(n)) return { state, newPending: false };
  state.called.push(n);
  state.called.sort((a, b) => a - b);
  const newPending = recompute(state, cards, nowHHMM());
  return { state, newPending };
}

export function applyUncallNumber(state, n, cards) {
  const idx = state.called.indexOf(n);
  if (idx === -1) return { state };
  state.called.splice(idx, 1);
  // Uncall only decreases levels, so recompute never emits new events here.
  recompute(state, cards, nowHHMM());
  return { state };
}

// Mark a specific pending event as confirmed (player is in play) or absent
// (card not in this game). Events are addressed by their natural key
// (cid + level + callCount) rather than position, so concurrent mutations
// can't accidentally flip the wrong one.
//
// Side effect: confirming an event flips state.levelAutoConfirm[level] to
// true so subsequent crossings at that level fast-path straight to
// "confirmed". Marking absent leaves the flag untouched -- "this particular
// card isn't in the game" doesn't establish that the level has a player yet.
export function applyResolveEvent(state, { cid, level, callCount }, resolution) {
  if (resolution !== "confirmed" && resolution !== "absent") {
    throw new Error("applyResolveEvent: resolution must be 'confirmed' or 'absent'");
  }
  for (const e of state.events || []) {
    if (e.cid === cid && e.level === level && e.callCount === callCount && e.status === "pending") {
      e.status = resolution;
      break;
    }
  }
  if (resolution === "confirmed") {
    if (!state.levelAutoConfirm) state.levelAutoConfirm = { 1: false, 2: false, 3: false };
    state.levelAutoConfirm[level] = true;
  }
  return { state };
}

// Record the host's choice when multiple cards tied a level with split=false.
// Key is "<level>:<callCount>", value is the winning card's cid. resolveLevel
// consults this map to promote exactly that card to sole winner.
export function applyResolveTiebreak(state, { level, callCount }, cid) {
  if (!state.tiebreakWinners) state.tiebreakWinners = {};
  state.tiebreakWinners[level + ":" + callCount] = cid;
  return { state };
}
