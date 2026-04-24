// Pure Russian Loto game logic.
//
// Every function in this module is a pure transformation of its arguments.
// No DOM access, no localStorage, no window globals. This makes the module
// Node-testable and lets the Stage-2 /display page reuse the same logic.
//
// Card shape (as delivered by the server): { seq, cid, numbers, rows }, where
// `rows` is a 3x9 array with cells of `number | null`. A row has 9 positions,
// exactly 5 of which are numbers; the rest are null. A "line" = one row.
//
// "Level" of a card = how many of its 3 rows are fully closed (every number
// in that row has been called). Level ranges 0..3; 3 = полное лото (bingo).

export function calledSet(calledArray) {
  return new Set(calledArray);
}

export function activeCards(allCards, cardRange) {
  if (!cardRange) return allCards;
  const [lo, hi] = cardRange;
  return allCards.filter((c) => c.seq >= lo && c.seq <= hi);
}

// Per-row hit counts. Returns three {hit, total} objects in row order.
export function rowHits(card, called) {
  return card.rows.map((row) => {
    let hit = 0;
    let total = 0;
    for (const n of row) {
      if (n === null) continue;
      total += 1;
      if (called.has(n)) hit += 1;
    }
    return { hit, total };
  });
}

// How many rows are fully closed (0..3).
export function levelOf(card, called) {
  let lines = 0;
  for (const { hit, total } of rowHits(card, called)) {
    if (total > 0 && hit === total) lines += 1;
  }
  return lines;
}

// True if the card has at least one unclosed row at 4/5 (one call away from
// closing that line). Already-closed rows (5/5) don't count.
export function isCardClose(card, called) {
  for (const { hit, total } of rowHits(card, called)) {
    if (total === 5 && hit === 4) return true;
  }
  return false;
}

export function closeCards(cards, called) {
  return cards.filter((card) => isCardClose(card, called));
}

export function tiebreakKey(level, callCount) {
  return level + ":" + callCount;
}

// Stage-2-ready: categorize "close" cards by which level they would reach
// next. A card at current level L with an unclosed 4/5 row is close to L+1.
// Level-3 cards are skipped (no further level to reach).
// Returns { 1: count, 2: count, 3: count }.
export function closeCountsByLevel(cards, called) {
  const counts = { 1: 0, 2: 0, 3: 0 };
  for (const card of cards) {
    const lvl = levelOf(card, called);
    if (lvl === 3) continue;
    if (isCardClose(card, called)) {
      counts[lvl + 1] += 1;
    }
  }
  return counts;
}

// First confirmed winner per level, used by the /display page. Events with
// status "pending" or "absent" are skipped -- we only surface cards that
// the admin has confirmed are actually playing. For ties on callCount,
// falls back to lowest seq.
// Returns { 1: {seq, cid}|null, 2: ..., 3: ... }.
export function winnersByLevel(events) {
  const out = { 1: null, 2: null, 3: null };
  for (const lvl of [1, 2, 3]) {
    const filtered = (events || []).filter(
      (e) => e.level === lvl && (e.status === undefined || e.status === "confirmed"),
    );
    if (filtered.length === 0) continue;
    let minCall = Infinity;
    for (const e of filtered) {
      const c = e.callCount === undefined ? Infinity : e.callCount;
      if (c < minCall) minCall = c;
    }
    const first = filtered
      .filter((e) => (e.callCount === undefined ? Infinity : e.callCount) === minCall)
      .sort((a, b) => a.seq - b.seq)[0];
    if (first) out[lvl] = { seq: first.seq, cid: first.cid };
  }
  return out;
}

// ---- Jackpot / payouts ----
//
// Each event in state.events has a status: "pending" | "confirmed" | "absent".
// A level is won by the first card whose event is confirmed (lowest callCount
// among confirmed events at that level). Pending and absent events do not
// count toward winning but are still logged: absent events are informational
// ("card X closed first, but wasn't in play"), pending events are a signal
// the UI must show a confirmation modal and block further play.
//
// Returns one of:
//   { status: "unclaimed" }                     -- no confirmed events yet
//   { status: "decided", winners }              -- one or more confirmed at the
//                                                  earliest callCount; with
//                                                  split=true all ties share,
//                                                  with split=false + tiebreak
//                                                  resolved only the picked
//                                                  card is a winner
//   { status: "pending-tiebreak",               -- split=false and >1 confirmed
//     level, callCount, candidates }              tied; host must pick one
export function resolveLevel(state, cards, level) {
  const events = (state.events || []).filter(
    (e) => e.level === level && (e.status === undefined || e.status === "confirmed"),
  );
  if (events.length === 0) return { status: "unclaimed" };

  let minCall = Infinity;
  for (const e of events) {
    const c = e.callCount === undefined ? Infinity : e.callCount;
    if (c < minCall) minCall = c;
  }
  const firstEvents = events.filter(
    (e) => (e.callCount === undefined ? Infinity : e.callCount) === minCall,
  );
  const resolveCard = (cid) => cards.find((c) => c.cid === cid);
  const winners = firstEvents.map((e) => resolveCard(e.cid)).filter(Boolean);
  if (winners.length === 0) return { status: "unclaimed" };

  winners.sort((a, b) => a.seq - b.seq);

  // Split=false with a multi-card tie: the host picks one winner via a mini
  // game. The pick is recorded in state.tiebreakWinners; until it's set, the
  // level stays in "pending-tiebreak" and the UI shows the picker modal.
  if (winners.length > 1 && state.split === false) {
    const tiebreakWinners = state.tiebreakWinners || {};
    const pickedCid = tiebreakWinners[tiebreakKey(level, minCall)];
    if (pickedCid) {
      const picked = winners.find((c) => c.cid === pickedCid);
      if (picked) return { status: "decided", winners: [picked] };
      // Pick references an unknown card -- treat as unresolved so the UI can
      // re-prompt rather than silently award the remaining candidates.
    }
    return {
      status: "pending-tiebreak",
      level,
      callCount: minCall,
      candidates: winners,
    };
  }
  return { status: "decided", winners };
}

// Returns the next unresolved split=false tie the UI should ask the host to
// pick a winner for. Lowest level first, then earliest callCount. Returns
// null if no tie needs a pick.
//
// Defers while any pending event remains at the same level+callCount as the
// candidate batch: the admin must first say yes/no for every candidate so
// the set of winners is final. Firing the picker earlier would ask the host
// to choose among N cards while an (N+1)-th is still on the table.
export function nextTiebreakBatch(state, cards) {
  if (state.split !== false) return null;
  for (const level of [1, 2, 3]) {
    const r = resolveLevel(state, cards, level);
    if (r.status !== "pending-tiebreak") continue;
    const samePending = (state.events || []).some(
      (e) => e.status === "pending" && e.level === level && e.callCount === r.callCount,
    );
    if (samePending) continue;
    return { level: r.level, callCount: r.callCount, candidates: r.candidates };
  }
  return null;
}

// Returns pending events grouped by (level, callCount). Each group is a
// batch that crossed a level simultaneously and must be confirmed together.
// Returns at most one group (the lowest-level, earliest-callCount batch) so
// the UI shows one modal at a time. Returns null if nothing is pending.
export function nextPendingBatch(state, cards) {
  const pending = (state.events || []).filter((e) => e.status === "pending");
  if (pending.length === 0) return null;
  const resolveCard = (cid) => cards.find((c) => c.cid === cid);

  // Sort by level asc, then callCount asc — we want the earliest crossing at
  // the lowest level to be resolved first.
  pending.sort((a, b) => {
    if (a.level !== b.level) return a.level - b.level;
    const ac = a.callCount === undefined ? Infinity : a.callCount;
    const bc = b.callCount === undefined ? Infinity : b.callCount;
    return ac - bc;
  });
  const head = pending[0];
  const batch = pending.filter(
    (e) => e.level === head.level && e.callCount === head.callCount,
  );
  const candidates = batch
    .map((e) => ({ event: e, card: resolveCard(e.cid) }))
    .filter((p) => p.card)
    .sort((a, b) => a.card.seq - b.card.seq);
  if (candidates.length === 0) return null;
  return { level: head.level, callCount: head.callCount, candidates };
}

export function hasPendingEvents(state) {
  return (state.events || []).some((e) => e.status === "pending");
}

export function computeLevelPayout(state, cards, level, base, absorbFinalRemainder) {
  const resolved = resolveLevel(state, cards, level);
  if (resolved.status === "unclaimed") {
    return { status: "unclaimed", base };
  }
  if (resolved.status === "pending-tiebreak") {
    return {
      status: "pending-tiebreak",
      base,
      level: resolved.level,
      callCount: resolved.callCount,
      candidates: resolved.candidates,
    };
  }
  const winnerCards = resolved.winners;
  if (winnerCards.length === 0) return { status: "unclaimed", base };

  const perPerson = Math.floor(base / winnerCards.length);
  const paid = perPerson * winnerCards.length;
  const remainder = base - paid;
  return {
    status: "paid",
    base,
    winners: winnerCards,
    perPerson,
    remainder,
    absorbFinalRemainder: !!absorbFinalRemainder,
  };
}

// For each level, one of four statuses: disabled / unclaimed / pending / paid.
// Remainders from levels 1 and 2 roll into level 3's base so no unit is lost.
// At level 3 the remainder goes to the first winner by seq via absorbFinalRemainder.
export function computePayouts(state, cards) {
  if (!state.jackpot || state.jackpot <= 0) {
    return { status: "disabled" };
  }
  const pct = state.percentages || [10, 25, 65];
  const base1 = Math.floor((state.jackpot * pct[0]) / 100);
  const base2 = Math.floor((state.jackpot * pct[1]) / 100);
  // base3 absorbs any integer-percent rounding so the three bases always sum
  // to the jackpot exactly.
  const base3Initial = state.jackpot - base1 - base2;

  const p1 = computeLevelPayout(state, cards, 1, base1);
  const p2 = computeLevelPayout(state, cards, 2, base2);

  let remainderRoll = 0;
  if (p1.status === "paid") remainderRoll += p1.remainder;
  if (p2.status === "paid") remainderRoll += p2.remainder;
  const base3 = base3Initial + remainderRoll;

  const p3 = computeLevelPayout(state, cards, 3, base3, /* absorbFinalRemainder */ true);

  return {
    status: "active",
    jackpot: state.jackpot,
    base1,
    base2,
    base3,            // effective, including rolled-in remainders
    base3Initial,
    level1: p1,
    level2: p2,
    level3: p3,
  };
}
