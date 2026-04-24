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

// Stage-2-ready: which card first crossed each level? Events are stored
// newest-first. For ties on callCount, falls back to lowest seq.
// Returns { 1: {seq, cid}|null, 2: ..., 3: ... }.
export function winnersByLevel(events) {
  const out = { 1: null, 2: null, 3: null };
  for (const lvl of [1, 2, 3]) {
    const filtered = events.filter((e) => e.level === lvl);
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
// Resolve who won a given level (if anyone). Shared between the payout
// calculation and any UI that needs to know the winner regardless of money.
// Returns one of:
//   { status: "unclaimed" }                                     -- no events yet
//   { status: "pending", candidates, tiebreakKey }              -- tied + split=off + no resolution
//   { status: "decided", winners }                              -- one unique winner, or split tie, or resolved
export function resolveLevel(state, cards, level) {
  const events = (state.events || []).filter((e) => e.level === level);
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

  if (firstEvents.length === 1 || state.split) {
    const winners = firstEvents.map((e) => resolveCard(e.cid)).filter(Boolean);
    if (winners.length === 0) return { status: "unclaimed" };
    return { status: "decided", winners: winners.slice().sort((a, b) => a.seq - b.seq) };
  }

  const key = level + "-" + minCall;
  const resolvedCid = (state.tiebreakResolutions || {})[key];
  if (!resolvedCid) {
    const candidates = firstEvents.map((e) => resolveCard(e.cid)).filter(Boolean);
    return {
      status: "pending",
      candidates: candidates.slice().sort((a, b) => a.seq - b.seq),
      tiebreakKey: key,
    };
  }
  const winner = resolveCard(resolvedCid);
  return { status: "decided", winners: winner ? [winner] : [] };
}

export function computeLevelPayout(state, cards, level, base, absorbFinalRemainder) {
  const resolved = resolveLevel(state, cards, level);
  if (resolved.status === "unclaimed") {
    return { status: "unclaimed", base };
  }
  if (resolved.status === "pending") {
    return {
      status: "pending",
      base,
      candidates: resolved.candidates,
      tiebreakKey: resolved.tiebreakKey,
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
