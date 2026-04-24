// Admin page entry point.
//
// The server bakes the cards payload and card-range into two JSON blobs
// inside the HTML. We read them, restore any saved game state, and hand
// everything to the UI module. All pure logic lives in logic.js and all
// state management lives in state.js -- this file is just wiring.

import * as state from "./state.js";
import * as ui from "./ui.js";

const CARDS = JSON.parse(document.getElementById("cards-data").textContent);

// SERVER_RANGE is the --cards range the operator passed to `loto serve`.
// On the admin page the user can refine the active range via the new-game
// modal, so SERVER_RANGE is only a starting default when no saved state
// exists. The Stage-2 /display page will consume it directly.
const SERVER_RANGE = JSON.parse(document.getElementById("server-range").textContent);

const initialState = state.loadState()
  || state.freshState({ cardRange: SERVER_RANGE });

function pushToServer(s) {
  fetch("/api/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  }).catch(() => {});
}

ui.init({ cards: CARDS, initialState, onSave: pushToServer });
