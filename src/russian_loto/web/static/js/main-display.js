import * as displayUI from "./display-ui.js";

const CARDS = JSON.parse(document.getElementById("cards-data").textContent);
const SERVER_RANGE = JSON.parse(document.getElementById("server-range").textContent);

displayUI.init({ cards: CARDS, range: SERVER_RANGE });

fetch("/api/state")
  .then((r) => (r.ok ? r.json() : null))
  .then((s) => { if (s) displayUI.render(s); })
  .catch(() => {});

function connectSSE() {
  const es = new EventSource("/api/events");

  es.onopen = () => displayUI.setConnected(true);

  es.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data);
      displayUI.render(payload.state || payload);
    } catch (_e) { /* ignore malformed frames */ }
  };

  es.onerror = () => {
    displayUI.setConnected(false);
    es.close();
    setTimeout(connectSSE, 2000);
  };
}

connectSSE();
