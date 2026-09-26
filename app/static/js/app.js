/* Global live KPI poller */

async function fetchLive() {
  const res = await fetch("/api/live");
  if (!res.ok) throw new Error("live fetch failed");
  return res.json();
}

function formatNum(v, digits = 1) {
  if (typeof v !== "number") return v;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function updateTopKpis(live) {
  const map = {
    it_load_mw: [live.it_load_mw, 1],
    pue: [live.pue, 3],
    utilization_pct: [live.utilization_pct, 1],
    active_alerts: [live.active_alerts, 0],
  };
  Object.entries(map).forEach(([key, [val, digits]]) => {
    document.querySelectorAll(`[data-k="${key}"]`).forEach((el) => {
      el.textContent = formatNum(val, digits);
    });
  });
  const mode = document.getElementById("live-mode");
  if (mode) mode.textContent = live.mode;
}

window.DCIM = {
  live: null,
  onLive: [],
  async refresh() {
    try {
      const live = await fetchLive();
      this.live = live;
      updateTopKpis(live);
      this.onLive.forEach((fn) => fn(live));
    } catch (err) {
      console.warn(err);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => {
  window.DCIM.refresh();
  setInterval(() => window.DCIM.refresh(), 2000);
});
