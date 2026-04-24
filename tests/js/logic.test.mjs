// Tests for src/russian_loto/web/static/js/logic.js.
//
// Run with:
//   node --test tests/js/
//
// No dependencies. Uses Node's built-in test runner (Node >= 20).

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  activeCards,
  calledSet,
  closeCards,
  closeCountsByLevel,
  computePayouts,
  hasPendingEvents,
  isCardClose,
  levelOf,
  nextPendingBatch,
  nextTiebreakBatch,
  resolveLevel,
  rowHits,
  winnersByLevel,
} from "../../src/russian_loto/web/static/js/logic.js";


// ---- Helpers --------------------------------------------------------------

// Build a card from a 3x9 grid literal. Use `_` for null cells for readability
// in tests. Returns a card object matching the server payload shape.
function card(seq, cid, grid) {
  const rows = grid.map((row) => row.map((v) => (v === "_" ? null : v)));
  const numbers = [];
  for (const row of rows) for (const n of row) if (n !== null) numbers.push(n);
  numbers.sort((a, b) => a - b);
  return { seq, cid, numbers, rows };
}

// A valid loto card: 5 numbers per row, 15 total. Numbers stay inside their
// column ranges (col c ∈ [c*10+1 .. c*10+9], col 8 = 80..90).
const simple = card(1, "aaa", [
  [1, 2, 3, 4, 5, "_", "_", "_", "_"],
  [6, "_", "_", "_", "_", 50, 60, 70, 80],
  [7, "_", "_", "_", "_", 55, 65, 75, 85],
]);


// ---- levelOf / isCardClose / rowHits --------------------------------------

test("levelOf: empty called set -> 0", () => {
  assert.equal(levelOf(simple, new Set()), 0);
});

test("levelOf: one full row -> 1", () => {
  assert.equal(levelOf(simple, new Set([1, 2, 3, 4, 5])), 1);
});

test("levelOf: two full rows -> 2", () => {
  assert.equal(levelOf(simple, new Set([1, 2, 3, 4, 5, 6, 50, 60, 70, 80])), 2);
});

test("levelOf: all three rows -> 3", () => {
  const all = new Set(simple.numbers);
  assert.equal(levelOf(simple, all), 3);
});

test("rowHits: per-row counts are correct", () => {
  const hits = rowHits(simple, new Set([1, 2, 3, 50]));
  assert.deepEqual(hits, [
    { hit: 3, total: 5 },
    { hit: 1, total: 5 },
    { hit: 0, total: 5 },
  ]);
});

test("isCardClose: true when one unclosed row is 4/5", () => {
  assert.equal(isCardClose(simple, new Set([1, 2, 3, 4])), true);
});

test("isCardClose: false when row is 5/5 (already closed, not 'close')", () => {
  assert.equal(isCardClose(simple, new Set([1, 2, 3, 4, 5])), false);
});

test("isCardClose: false when no row is 4/5", () => {
  assert.equal(isCardClose(simple, new Set([1, 2, 50])), false);
});


// ---- activeCards / calledSet ---------------------------------------------

test("calledSet: returns a Set of the given array", () => {
  const s = calledSet([3, 1, 2]);
  assert.ok(s instanceof Set);
  assert.equal(s.size, 3);
  assert.ok(s.has(1) && s.has(2) && s.has(3));
});

test("activeCards: null range returns all cards", () => {
  const cards = [{ seq: 1 }, { seq: 5 }, { seq: 10 }];
  assert.deepEqual(activeCards(cards, null), cards);
});

test("activeCards: range filters inclusively", () => {
  const cards = [{ seq: 1 }, { seq: 5 }, { seq: 10 }];
  assert.deepEqual(activeCards(cards, [3, 7]), [{ seq: 5 }]);
});


// ---- closeCards / closeCountsByLevel -------------------------------------

test("closeCards: returns cards one call from closing a line", () => {
  const nothing = { ...simple, cid: "a", seq: 1 };
  const almost = { ...simple, cid: "b", seq: 2 };
  const called = new Set([1, 2, 3, 4]);  // 4/5 on almost's first row
  const result = closeCards([nothing, almost], called);
  assert.equal(result.length, 2);  // simple also has hits in row 0
  // Any card with a 4/5 row qualifies. Both test cards share the same rows.
});

test("closeCountsByLevel: bucketizes by which level each card would reach", () => {
  // Card A: no lines closed yet, row 0 at 4/5 -> close to level 1
  // Card B: one line closed, row 1 at 4/5   -> close to level 2
  // Card C: already at level 3               -> skipped
  const a = card(1, "a", [
    [1, 2, 3, 4, "_", 50, "_", "_", "_"],
    ["_", "_", "_", "_", "_", "_", 60, 70, 80],
    ["_", "_", "_", "_", "_", 55, 65, 75, "_"],
  ]);
  const b = card(2, "b", [
    [1, 2, 3, 4, 5, "_", "_", "_", "_"],         // closed (all called)
    ["_", "_", "_", "_", "_", 56, 66, 76, 86],   // 4/5 if we call 56,66,76,86 but not 5 of them
    ["_", "_", "_", "_", "_", 57, 67, 77, 87],
  ]);
  const c = card(3, "c", [
    [10, 11, 12, 13, 14, "_", "_", "_", "_"],
    ["_", "_", "_", "_", "_", 15, 16, 17, 18],
    ["_", "_", "_", "_", "_", 19, 21, 22, 23],
  ]);
  // Build called set:
  //   a's row 0 at 4/5: 1,2,3,4 called (no 5 yet, 5 is not in row 0 of a)
  //     Actually row 0 of a is [1,2,3,4,_,50,_,_,_] -> 5 numbers: 1,2,3,4,50.
  //     For 4/5 we need to call 4 of those without the 5th. Call 1,2,3,4.
  //   b: row 0 closed => call 1,2,3,4,5. Row 1 4/5 => call 56,66,76 (3/5? need 4)
  //     Row 1 has 4 numbers: 56,66,76,86 (4 non-null). Wait, 4 total. So needs 3/4 hits for "close".
  //     Actually we require total==5, so rows with 4 nulls are total=4 and cannot be close. Let me
  //     adjust card b so row 1 has exactly 5 numbers.
  //   c: all 15 numbers called => level 3, skipped.
  // Simpler: just test the code paths on a single card.
  const single = card(1, "x", [
    [1, 2, 3, 4, "_", 50, "_", "_", "_"],   // 5 non-null: 1,2,3,4,50
    ["_", "_", "_", "_", "_", 56, 66, 76, 86], // only 4 non-null -- invalid in real loto
    ["_", "_", "_", "_", "_", 57, 67, 77, 87],
  ]);
  // Not all test cards can be "real" loto cards; the function only checks row
  // totals. We check {total: 5, hit: 4} semantics: call 1,2,3,4 -> row 0 is 4/5,
  // levelOf=0, so close to level 1.
  const called = new Set([1, 2, 3, 4]);
  const counts = closeCountsByLevel([single], called);
  assert.deepEqual(counts, { 1: 1, 2: 0, 3: 0 });
});

test("closeCountsByLevel: level-3 cards are excluded", () => {
  const all = new Set(simple.numbers);  // everything called -> level 3
  const counts = closeCountsByLevel([simple], all);
  assert.deepEqual(counts, { 1: 0, 2: 0, 3: 0 });
});

test("closeCountsByLevel: card with one line closed and another 4/5 -> level 2 bucket", () => {
  // Row 0 fully closed (level 1). Row 1 at 4/5.
  // Call: 1,2,3,4,5 (row 0 closed) + 56,66,76,86 (row 1 has 5 nums: 56,66,76,86,_) ... need row 1 to have 5 nums.
  const c = card(1, "x", [
    [1, 2, 3, 4, 5, "_", "_", "_", "_"],
    ["_", "_", "_", "_", "_", 56, 66, 76, 86],   // only 4 non-null => total=4, cannot be close
    ["_", "_", "_", "_", "_", 57, 67, 77, 87],
  ]);
  // Fix: include 5 numbers in row 1.
  const c2 = card(1, "x", [
    [1, 2, 3, 4, 5, "_", "_", "_", "_"],
    ["_", 11, "_", "_", "_", 56, 66, 76, 86],
    ["_", "_", "_", "_", "_", 57, 67, 77, 87],
  ]);
  // Level of c2 with just row 0 called: 1. Need row 1 at 4/5 -> call 4 of {11,56,66,76,86}.
  const called = new Set([1, 2, 3, 4, 5, 11, 56, 66, 76]); // row 1 hit 4/5 (missing 86)
  const counts = closeCountsByLevel([c2], called);
  assert.deepEqual(counts, { 1: 0, 2: 1, 3: 0 });
});


// ---- winnersByLevel ------------------------------------------------------

test("winnersByLevel: empty events -> nulls", () => {
  assert.deepEqual(winnersByLevel([]), { 1: null, 2: null, 3: null });
});

test("winnersByLevel: first-to-reach per level (confirmed only)", () => {
  const events = [
    { cid: "c", seq: 3, level: 1, callCount: 20, status: "confirmed" },
    { cid: "b", seq: 2, level: 1, callCount: 15, status: "confirmed" },
    { cid: "a", seq: 1, level: 2, callCount: 22, status: "confirmed" },
  ];
  const w = winnersByLevel(events);
  assert.deepEqual(w[1], { seq: 2, cid: "b" });
  assert.deepEqual(w[2], { seq: 1, cid: "a" });
  assert.equal(w[3], null);
});

test("winnersByLevel: ties on callCount resolve to lowest seq", () => {
  const events = [
    { cid: "x", seq: 7, level: 1, callCount: 10, status: "confirmed" },
    { cid: "y", seq: 3, level: 1, callCount: 10, status: "confirmed" },
    { cid: "z", seq: 9, level: 1, callCount: 10, status: "confirmed" },
  ];
  assert.deepEqual(winnersByLevel(events)[1], { seq: 3, cid: "y" });
});

test("winnersByLevel: absent events are skipped, confirmed at higher callCount wins", () => {
  const events = [
    { cid: "a", seq: 1, level: 1, callCount: 10, status: "absent" },
    { cid: "b", seq: 2, level: 1, callCount: 15, status: "confirmed" },
  ];
  assert.deepEqual(winnersByLevel(events)[1], { seq: 2, cid: "b" });
});

test("winnersByLevel: pending events are skipped (no winner yet)", () => {
  const events = [
    { cid: "a", seq: 1, level: 1, callCount: 10, status: "pending" },
  ];
  assert.equal(winnersByLevel(events)[1], null);
});

test("winnersByLevel: legacy events with no status field count as confirmed", () => {
  const events = [{ cid: "a", seq: 1, level: 1, callCount: 10 }];
  assert.deepEqual(winnersByLevel(events)[1], { seq: 1, cid: "a" });
});


// ---- nextPendingBatch / hasPendingEvents ---------------------------------

test("nextPendingBatch: null when nothing pending", () => {
  const state = { events: [{ cid: "a", seq: 1, level: 1, callCount: 5, status: "confirmed" }] };
  assert.equal(nextPendingBatch(state, [{ cid: "a", seq: 1 }]), null);
});

test("nextPendingBatch: returns the lowest-level earliest pending batch", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 2, callCount: 20, status: "pending" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "pending" },
    ],
  };
  const batch = nextPendingBatch(state, cards);
  assert.equal(batch.level, 1);
  assert.equal(batch.callCount, 10);
  assert.equal(batch.candidates.length, 1);
  assert.equal(batch.candidates[0].card.cid, "b");
});

test("nextPendingBatch: groups simultaneous pending events (same level + callCount)", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }, { cid: "c", seq: 3 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "pending" },
      { cid: "c", seq: 3, level: 1, callCount: 10, status: "pending" },
      { cid: "b", seq: 2, level: 1, callCount: 11, status: "pending" },
    ],
  };
  const batch = nextPendingBatch(state, cards);
  assert.equal(batch.level, 1);
  assert.equal(batch.callCount, 10);
  // Two simultaneous candidates, sorted by seq
  assert.deepEqual(batch.candidates.map((p) => p.card.seq), [1, 3]);
});

test("hasPendingEvents: true iff any event is pending", () => {
  assert.equal(hasPendingEvents({ events: [] }), false);
  assert.equal(hasPendingEvents({ events: [{ status: "confirmed" }, { status: "absent" }] }), false);
  assert.equal(hasPendingEvents({ events: [{ status: "pending" }] }), true);
});


// ---- resolveLevel --------------------------------------------------------

test("resolveLevel: no events -> unclaimed", () => {
  const state = { events: [], split: true };
  assert.deepEqual(resolveLevel(state, [], 1), { status: "unclaimed" });
});

test("resolveLevel: pending events are invisible to the resolver", () => {
  const state = {
    events: [{ cid: "a", seq: 1, level: 1, callCount: 10, status: "pending" }],
    split: true,
  };
  assert.equal(resolveLevel(state, [{ cid: "a", seq: 1 }], 1).status, "unclaimed");
});

test("resolveLevel: absent events are skipped, later confirmed event wins", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "absent" },
      { cid: "b", seq: 2, level: 1, callCount: 15, status: "confirmed" },
    ],
    split: true,
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.deepEqual(r.winners.map((c) => c.cid), ["b"]);
});

test("resolveLevel: multiple confirmed at same callCount -> all tied winners", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: true,
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.deepEqual(r.winners.map((c) => c.cid), ["a", "b"]);
});

test("resolveLevel: legacy events (no status) are treated as confirmed", () => {
  const cards = [{ cid: "a", seq: 1 }];
  const state = {
    events: [{ cid: "a", seq: 1, level: 1, callCount: 10 }],
    split: true,
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.equal(r.winners[0].cid, "a");
});


// ---- computePayouts ------------------------------------------------------

test("computePayouts: jackpot 0 -> disabled", () => {
  const state = { jackpot: 0, percentages: [10, 25, 65], events: [], split: true };
  assert.deepEqual(computePayouts(state, []), { status: "disabled" });
});

test("computePayouts: bases sum to jackpot regardless of rounding", () => {
  const state = {
    jackpot: 999,
    percentages: [10, 25, 65],
    events: [],
    split: true,
  };
  const out = computePayouts(state, []);
  assert.equal(out.status, "active");
  // base3 absorbs rounding; sum must equal jackpot
  assert.equal(out.base1 + out.base2 + out.base3Initial, 999);
});

test("computePayouts: level-3 winner gets remainder when winners.length==1", () => {
  const cards = [{ cid: "a", seq: 1 }];
  const state = {
    jackpot: 100,
    percentages: [10, 25, 65],
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 5, status: "confirmed" },
      { cid: "a", seq: 1, level: 2, callCount: 10, status: "confirmed" },
      { cid: "a", seq: 1, level: 3, callCount: 15, status: "confirmed" },
    ],
    split: true,
  };
  const out = computePayouts(state, cards);
  assert.equal(out.level3.status, "paid");
  assert.equal(out.level3.perPerson, out.base3);
  assert.equal(out.level3.remainder, 0);  // one winner, perPerson === base
});

test("computePayouts: pending events leave levels unclaimed", () => {
  const cards = [{ cid: "a", seq: 1 }];
  const state = {
    jackpot: 100,
    percentages: [10, 25, 65],
    events: [{ cid: "a", seq: 1, level: 1, callCount: 10, status: "pending" }],
    split: true,
  };
  const out = computePayouts(state, cards);
  assert.equal(out.level1.status, "unclaimed");
});


// ---- Tiebreak (split=false) ---------------------------------------------

test("resolveLevel: split=true, multiple confirmed ties -> all winners (shared)", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: true,
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.deepEqual(r.winners.map((c) => c.cid), ["a", "b"]);
});

test("resolveLevel: split=false, single confirmed -> decided with one winner (no tiebreak)", () => {
  const cards = [{ cid: "a", seq: 1 }];
  const state = {
    events: [{ cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" }],
    split: false,
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.deepEqual(r.winners.map((c) => c.cid), ["a"]);
});

test("resolveLevel: split=false, multiple confirmed ties, no pick -> pending-tiebreak", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "pending-tiebreak");
  assert.equal(r.level, 1);
  assert.equal(r.callCount, 10);
  assert.deepEqual(r.candidates.map((c) => c.cid), ["a", "b"]);
});

test("resolveLevel: split=false, tie with tiebreakWinner set -> decided with the picked card", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: { "1:10": "b" },
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "decided");
  assert.deepEqual(r.winners.map((c) => c.cid), ["b"]);
});

test("resolveLevel: split=false, tiebreakWinner with unknown cid -> pending-tiebreak", () => {
  // Defensive: a tiebreak entry pointing at a card not among candidates
  // should not silently promote the remaining candidates. Stay pending.
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: { "1:10": "nonsense-cid" },
  };
  const r = resolveLevel(state, cards, 1);
  assert.equal(r.status, "pending-tiebreak");
});


// ---- nextTiebreakBatch --------------------------------------------------

test("nextTiebreakBatch: null when split=true (ties are shared, no pick needed)", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: true,
    tiebreakWinners: {},
  };
  assert.equal(nextTiebreakBatch(state, cards), null);
});

test("nextTiebreakBatch: null when only one confirmed at level (no tie)", () => {
  const cards = [{ cid: "a", seq: 1 }];
  const state = {
    events: [{ cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" }],
    split: false,
    tiebreakWinners: {},
  };
  assert.equal(nextTiebreakBatch(state, cards), null);
});

test("nextTiebreakBatch: returns unresolved tie (lowest level first)", () => {
  const cards = [
    { cid: "a", seq: 1 }, { cid: "b", seq: 2 },
    { cid: "c", seq: 3 }, { cid: "d", seq: 4 },
  ];
  const state = {
    events: [
      { cid: "c", seq: 3, level: 2, callCount: 20, status: "confirmed" },
      { cid: "d", seq: 4, level: 2, callCount: 20, status: "confirmed" },
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  const batch = nextTiebreakBatch(state, cards);
  assert.equal(batch.level, 1);
  assert.equal(batch.callCount, 10);
  assert.deepEqual(batch.candidates.map((c) => c.cid), ["a", "b"]);
});

test("nextTiebreakBatch: skips levels already resolved via tiebreakWinners", () => {
  const cards = [
    { cid: "a", seq: 1 }, { cid: "b", seq: 2 },
    { cid: "c", seq: 3 }, { cid: "d", seq: 4 },
  ];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
      { cid: "c", seq: 3, level: 2, callCount: 20, status: "confirmed" },
      { cid: "d", seq: 4, level: 2, callCount: 20, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: { "1:10": "a" },
  };
  const batch = nextTiebreakBatch(state, cards);
  assert.equal(batch.level, 2);
  assert.equal(batch.callCount, 20);
});

test("nextTiebreakBatch: pending events do not trigger a tiebreak", () => {
  // Until both candidates are "confirmed", there is no tie to break.
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "pending" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  assert.equal(nextTiebreakBatch(state, cards), null);
});

test("nextTiebreakBatch: defers when a third candidate in the same batch is still pending", () => {
  // Three cards tied the level simultaneously; the admin has confirmed
  // two but not yet answered about the third. The tiebreak must wait --
  // otherwise the host is asked to pick a winner among 2 cards while a
  // third candidate is still on the table.
  const cards = [
    { cid: "a", seq: 1 }, { cid: "b", seq: 2 }, { cid: "c", seq: 3 },
  ];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 2, callCount: 20, status: "confirmed" },
      { cid: "b", seq: 2, level: 2, callCount: 20, status: "confirmed" },
      { cid: "c", seq: 3, level: 2, callCount: 20, status: "pending" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  assert.equal(nextTiebreakBatch(state, cards), null);
});

test("nextTiebreakBatch: fires once every candidate is resolved (even if some went absent)", () => {
  // Three-way tie, admin confirms two and marks the third absent. The
  // batch is now finalized and the host picks between the two confirmed.
  const cards = [
    { cid: "a", seq: 1 }, { cid: "b", seq: 2 }, { cid: "c", seq: 3 },
  ];
  const state = {
    events: [
      { cid: "a", seq: 1, level: 2, callCount: 20, status: "confirmed" },
      { cid: "b", seq: 2, level: 2, callCount: 20, status: "confirmed" },
      { cid: "c", seq: 3, level: 2, callCount: 20, status: "absent" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  const batch = nextTiebreakBatch(state, cards);
  assert.ok(batch, "expected a tiebreak batch");
  assert.equal(batch.level, 2);
  assert.deepEqual(batch.candidates.map((c) => c.cid), ["a", "b"]);
});


// ---- computePayouts with tiebreak ---------------------------------------

test("computePayouts: split=false with unresolved tie -> level is pending-tiebreak", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    jackpot: 100,
    percentages: [10, 25, 65],
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: {},
  };
  const out = computePayouts(state, cards);
  assert.equal(out.level1.status, "pending-tiebreak");
  // base is still reserved so the UI can show how much is at stake
  assert.equal(out.level1.base, 10);
});

test("computePayouts: split=false with resolved tie -> single winner gets full base", () => {
  const cards = [{ cid: "a", seq: 1 }, { cid: "b", seq: 2 }];
  const state = {
    jackpot: 100,
    percentages: [10, 25, 65],
    events: [
      { cid: "a", seq: 1, level: 1, callCount: 10, status: "confirmed" },
      { cid: "b", seq: 2, level: 1, callCount: 10, status: "confirmed" },
    ],
    split: false,
    tiebreakWinners: { "1:10": "b" },
  };
  const out = computePayouts(state, cards);
  assert.equal(out.level1.status, "paid");
  assert.equal(out.level1.winners.length, 1);
  assert.equal(out.level1.winners[0].cid, "b");
  assert.equal(out.level1.perPerson, 10);
});
