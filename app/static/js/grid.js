/* Krafton Grid · core client — live stream, bindings, palette, tables, tabs, toasts */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // ---------------------------------------------------------------- format
  const fmt = {
    num(v, d = 0) { if (v === null || v === undefined || Number.isNaN(+v)) return "—"; return (+v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); },
    int(v) { return fmt.num(v, 0); }, f1(v) { return fmt.num(v, 1); }, f2(v) { return fmt.num(v, 2); }, f3(v) { return fmt.num(v, 3); },
    pct(v) { return fmt.num(v, 1) + "%"; },
    krw(v) {
      if (v === null || v === undefined) return "—"; v = +v; const a = Math.abs(v), sg = v < 0 ? "−" : "";
      if (a >= 1e12) return sg + "₩" + (a / 1e12).toFixed(2) + "조";
      if (a >= 1e8) return sg + "₩" + (a / 1e8).toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) + "억";
      if (a >= 1e4) return sg + "₩" + Math.round(a / 1e4).toLocaleString("en-US") + "만";
      return sg + "₩" + Math.round(a).toLocaleString("en-US");
    },
    krwfull(v) { return v === null || v === undefined ? "—" : "₩" + Math.round(+v).toLocaleString("en-US"); },
    dur(s) {
      if (s === null || s === undefined) return "—"; s = Math.max(0, Math.round(+s));
      if (s < 60) return s + "s"; if (s < 3600) return Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s";
      if (s < 86400) return Math.floor(s / 3600) + "h " + String(Math.floor((s % 3600) / 60)).padStart(2, "0") + "m";
      return Math.floor(s / 86400) + "d " + Math.floor((s % 86400) / 3600) + "h";
    },
    ago(t) { return t ? fmt.dur(Date.now() / 1000 - t) + " ago" : "—"; },
    kst(t) { if (!t) return "—"; const d = new Date(t * 1000 + 9 * 3600e3); return d.toISOString().substr(11, 8); },
    raw(v) { return v === null || v === undefined ? "—" : String(v); },
  };
  const pick = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
  const level = (s) => {
    s = String(s || "").toLowerCase();
    if (["ok", "running", "online", "up", "healthy", "ready", "energized", "active", "alloc", "mix", "serving", "closed", "resolved", "approved", "completed", "n+1", "2n"].includes(s)) return "ok";
    if (["critical", "failed", "fault", "tripped", "down", "lost", "notready", "crashloopbackoff", "open", "over", "rejected", "error"].includes(s) || s.startsWith("n (")) return "crit";
    if (["warning", "warn", "degraded", "drain", "busy", "starting", "on-battery", "cooldown", "maintenance", "pending", "watch", "mitigating", "online · genset", "containercreating"].includes(s) ) return "warn";
    if (["info", "submitted", "team_lead", "finance", "scheduled"].includes(s)) return "info";
    return "idle";
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pill = (s, text) => `<span class="pill ${level(s)}">${esc(text ?? s)}</span>`;
  const barClass = (v, warn = 80, crit = 92) => (v >= crit ? "crit" : v >= warn ? "warn" : "");

  // ---------------------------------------------------------------- live store
  const subs = [];
  let last = window.__LIVE__ || null;
  let lastAt = Date.now();
  let es = null, pollTimer = null, seenAlerts = new Set();
  (last && last.alerts && last.alerts.recent || []).forEach((a) => seenAlerts.add(a.id));

  function dispatch(live) {
    last = live; lastAt = Date.now(); window.__LIVE__ = live;
    bindAll(document, live);
    topbar(live);
    for (const fn of subs) { try { fn(live); } catch (e) { console.error(e); } }
    (live.alerts && live.alerts.recent || []).forEach((a) => {
      if (!seenAlerts.has(a.id)) {
        seenAlerts.add(a.id);
        if (a.severity !== "info") toast(a.severity, a.name, a.summary, a.href);
      }
    });
  }
  // One EventSource per *browser*, not per tab. HTTP/1.1 allows ~6 concurrent connections per host;
  // a long-lived SSE in every open tab used them all and new page loads queued behind them (5 s+ stalls).
  // Tabs elect a leader with the Web Locks API; only the leader streams and rebroadcasts each snapshot
  // over a BroadcastChannel. The lock is released when the leader tab closes or navigates, and the
  // next tab takes over. Followers poll /api/live if the broadcast goes quiet.
  const LIVE_CH = "grid-live-v1";
  let bc = null, isLeader = false;
  function connect() {
    if (window.BroadcastChannel && navigator.locks && navigator.locks.request) {
      bc = new BroadcastChannel(LIVE_CH);
      bc.onmessage = (m) => { if (!isLeader && typeof m.data === "string") { try { dispatch(JSON.parse(m.data)); } catch (e) { } } };
      navigator.locks.request(LIVE_CH, () => new Promise(() => { isLeader = true; openStream(); }));
      setInterval(() => { if (!isLeader && Date.now() - lastAt > 7000) pollOnce(); }, 3000);
    } else openStream();
  }
  function openStream() {
    if (!window.EventSource) return poll();
    es = new EventSource("/api/stream");
    es.addEventListener("live", (ev) => { try { dispatch(JSON.parse(ev.data)); if (bc) bc.postMessage(ev.data); } catch (e) { /* partial frame */ } });
    es.onerror = () => { es.close(); es = null; setDot("off"); setTimeout(openStream, 4000); if (!pollTimer) poll(); };
    es.onopen = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } };
  }
  function poll() {
    if (pollTimer) return;
    pollTimer = setInterval(() => { if (!es) pollOnce(); }, 3000);
  }
  async function pollOnce() { try { dispatch(await getJSON("/api/live")); } catch (e) { } }
  function setDot(state) { const d = $("#live-dot"); if (d) d.className = "live-dot " + (state || ""); }
  setInterval(() => { const age = Date.now() - lastAt; setDot(age > 12000 ? "off" : age > 6000 ? "stale" : ""); }, 2000);

  function bindAll(root, live) {
    $$("[data-live]", root).forEach((el) => {
      const v = pick(live, el.dataset.live);
      if (v === undefined) return;
      const f = fmt[el.dataset.fmt || "raw"] || fmt.raw;
      const txt = f(v);
      if (el.textContent !== txt) el.textContent = txt;
    });
    $$("[data-live-bar]", root).forEach((el) => {
      let v = +pick(live, el.dataset.liveBar);
      if (el.dataset.max) v = (v / +el.dataset.max) * 100;
      if (Number.isNaN(v)) return;
      el.style.width = Math.max(0, Math.min(100, v)) + "%";
      if (el.dataset.warn) el.className = barClass(v, +el.dataset.warn, +(el.dataset.crit || 101));
    });
    $$("[data-live-pill]", root).forEach((el) => {
      const v = pick(live, el.dataset.livePill);
      if (v === undefined) return;
      el.className = "pill " + level(v); el.textContent = v;
    });
  }
  function topbar(live) {
    const a = live.alerts || {};
    const b = $("#bell-badge");
    if (b) { b.textContent = a.firing || 0; b.className = "badge " + (a.critical ? "crit" : a.warning ? "warn" : ""); b.style.display = a.firing ? "" : "none"; }
    const sc = $("#scenario-chip");
    if (sc) {
      const s = live.scenarios || [];
      sc.style.display = s.length ? "" : "none";
      if (s.length) sc.innerHTML = `<span class="dot warn pulse"></span>${esc(s[0].name)}${s.length > 1 ? " +" + (s.length - 1) : ""} · ${fmt.dur(s[0].remaining_s)}`;
    }
    const mc = $("#mode-chip");
    if (mc) { mc.textContent = "mode · " + live.mode; mc.className = "chip mode " + (live.mode === "normal" ? "" : "warn"); }
    const tk = $("#tick"); if (tk) tk.textContent = "tick " + live.tick;
  }

  // ---------------------------------------------------------------- fetch
  async function getJSON(url, opts) {
    const r = await fetch(url, Object.assign({ headers: { Accept: "application/json" } }, opts || {}));
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch (e) { } throw new Error(m); }
    return r.json();
  }
  async function postJSON(url, body) {
    return getJSON(url, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body || {}) });
  }
  function every(ms, fn) {
    let t = null;
    const run = async () => { if (document.hidden) return; try { await fn(); } catch (e) { console.warn(e); } };
    run(); t = setInterval(run, ms);
    return () => clearInterval(t);
  }

  // ---------------------------------------------------------------- toasts
  function toast(sev, title, text, href) {
    const box = $("#toasts"); if (!box) return;
    const el = document.createElement(href ? "a" : "div");
    if (href) el.href = href;
    el.className = "toast " + (sev || "");
    el.innerHTML = `<b>${esc(title)}</b><span class="muted">${esc(text || "")}</span>`;
    box.appendChild(el);
    setTimeout(() => { el.style.transition = "opacity .3s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 320); }, sev === "critical" ? 9000 : 5000);
  }

  // ---------------------------------------------------------------- tabs
  function initTabs(root = document) {
    $$("[data-tabs]", root).forEach((bar) => {
      const key = bar.dataset.tabs;
      const scope = bar.closest("[data-tab-scope]") || document;
      const btns = $$("[data-tab]", bar);
      const set = (id, push) => {
        btns.forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
        $$(`[data-panel][data-group="${key}"]`, scope).forEach((p) => p.classList.toggle("on", p.dataset.panel === id));
        if (push) { const u = new URL(location.href); u.searchParams.set(key, id); history.replaceState(null, "", u); }
        window.dispatchEvent(new CustomEvent("tab:" + key, { detail: id }));
        setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
      };
      btns.forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); set(b.dataset.tab, true); }));
      const want = new URL(location.href).searchParams.get(key) || bar.dataset.default || (btns[0] && btns[0].dataset.tab);
      set(btns.some((b) => b.dataset.tab === want) ? want : btns[0].dataset.tab, false);
    });
  }

  // ---------------------------------------------------------------- tables
  function initTables(root = document) {
    $$("table.t[data-sortable]", root).forEach((t) => {
      $$("th", t).forEach((th, i) => {
        if (th.dataset.nosort !== undefined) return;
        th.classList.add("sortable");
        th.addEventListener("click", () => {
          const asc = th.classList.contains("sorted") && !th.classList.contains("asc");
          $$("th", t).forEach((x) => x.classList.remove("sorted", "asc"));
          th.classList.add("sorted"); if (asc) th.classList.add("asc");
          const body = t.tBodies[0];
          const rows = Array.from(body.rows);
          const val = (r) => { const c = r.cells[i]; const v = c ? (c.dataset.v ?? c.textContent.trim()) : ""; const n = parseFloat(String(v).replace(/[₩,%억만\s]/g, "")); return Number.isNaN(n) ? v.toLowerCase() : n; };
          rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
          rows.forEach((r) => body.appendChild(r));
        });
      });
    });
    $$("[data-filter]", root).forEach((inp) => {
      const t = document.getElementById(inp.dataset.filter.replace(/^#/, "")); if (!t) return;
      inp.addEventListener("input", () => {
        const q = inp.value.trim().toLowerCase();
        Array.from(t.tBodies[0].rows).forEach((r) => { r.style.display = !q || r.textContent.toLowerCase().includes(q) ? "" : "none"; });
      });
    });
    $$("[data-export]", root).forEach((btn) => btn.addEventListener("click", () => exportCSV(document.getElementById(btn.dataset.export.replace(/^#/, "")), btn.dataset.name)));
    root.addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-href]");
      if (tr && !e.target.closest("a,button,input")) { if (e.metaKey || e.ctrlKey) window.open(tr.dataset.href); else location.href = tr.dataset.href; }
    });
  }
  function exportCSV(table, name) {
    if (!table) return;
    const rows = Array.from(table.rows).filter((r) => r.style.display !== "none").map((r) =>
      Array.from(r.cells).map((c) => `"${(c.dataset.v ?? c.textContent).trim().replace(/"/g, '""').replace(/\s+/g, " ")}"`).join(","));
    const blob = new Blob(["﻿" + rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = (name || "export") + ".csv"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ---------------------------------------------------------------- command palette
  function initPalette() {
    const ov = $("#palette"); if (!ov) return;
    const inp = $("input", ov), list = $(".palette-results", ov);
    let items = [], idx = 0, timer = null;
    const open = () => { ov.classList.add("on"); inp.value = ""; search(""); setTimeout(() => inp.focus(), 10); };
    const close = () => ov.classList.remove("on");
    const draw = () => {
      list.innerHTML = items.length ? items.map((it, i) => `<div class="p-item ${i === idx ? "on" : ""}" data-i="${i}"><span class="p-kind">${esc(it.kind)}</span><span class="p-title">${esc(it.title)}</span><span class="p-group">${esc(it.group || "")}</span></div>`).join("")
        : `<div class="empty">No matches — try R12, kg-r07-n03, CDU-A2, ib-leaf-05, pue, scenario</div>`;
    };
    const go = async (it) => {
      if (!it) return;
      if (it.action) { try { await postJSON(it.action.url); toast("ok", "Started", it.title); } catch (e) { toast("critical", "Failed", e.message); } close(); return; }
      location.href = it.href;
    };
    const search = (q) => { clearTimeout(timer); timer = setTimeout(async () => { try { items = (await getJSON("/api/search?q=" + encodeURIComponent(q))).results; idx = 0; draw(); } catch (e) { } }, 90); };
    inp.addEventListener("input", () => search(inp.value));
    inp.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { idx = Math.min(items.length - 1, idx + 1); draw(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { idx = Math.max(0, idx - 1); draw(); e.preventDefault(); }
      else if (e.key === "Enter") { go(items[idx]); }
      else if (e.key === "Escape") close();
    });
    list.addEventListener("click", (e) => { const p = e.target.closest(".p-item"); if (p) go(items[+p.dataset.i]); });
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); ov.classList.contains("on") ? close() : open(); }
      else if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement.tagName)) { e.preventDefault(); open(); }
    });
    $$("[data-open-palette]").forEach((b) => b.addEventListener("click", open));
  }

  // ---------------------------------------------------------------- misc
  function clock() { const el = $("#clock"); if (el) el.textContent = fmt.kst(Date.now() / 1000) + " KST"; }
  function initNav() {
    const h = $("#hamburger"); if (h) h.addEventListener("click", () => document.body.classList.toggle("nav-open"));
    const active = $(".nav-sub a.active, .nav-top.active"); if (active) active.scrollIntoView({ block: "center" });
  }
  function md(text) {
    // tiny markdown: **bold**, `code`, bullets, paragraphs, links
    const lines = esc(text || "").split("\n");
    let html = "", inList = false;
    for (let ln of lines) {
      ln = ln.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\[([^\]]+)\]\((\/[^)\s]*)\)/g, '<a class="link" href="$2">$1</a>');
      if (/^\s*[-*•]\s+/.test(ln)) { if (!inList) { html += "<ul>"; inList = true; } html += "<li>" + ln.replace(/^\s*[-*•]\s+/, "") + "</li>"; continue; }
      if (inList) { html += "</ul>"; inList = false; }
      if (/^#{1,3}\s/.test(ln)) { html += "<p><b>" + ln.replace(/^#{1,3}\s/, "") + "</b></p>"; continue; }
      if (ln.trim()) html += "<p>" + ln + "</p>";
    }
    if (inList) html += "</ul>";
    return html;
  }
  async function confirmAction(btn) {
    const msg = btn.dataset.confirm;
    if (msg && !window.confirm(msg)) return;
    btn.disabled = true;
    try {
      const body = btn.dataset.body ? JSON.parse(btn.dataset.body) : {};
      await postJSON(btn.dataset.post, body);
      toast("ok", btn.dataset.done || "Done", btn.dataset.post);
      if (btn.dataset.reload !== undefined) setTimeout(() => location.reload(), 500);
    } catch (e) { toast("critical", "Request failed", e.message); }
    btn.disabled = false;
  }

  document.addEventListener("click", (e) => { const b = e.target.closest("[data-post]"); if (b) { e.preventDefault(); confirmAction(b); } });
  document.addEventListener("DOMContentLoaded", () => {
    initNav(); initTabs(); initTables(); initPalette(); clock(); setInterval(clock, 1000);
    if (last) { bindAll(document, last); topbar(last); }
    connect();
  });

  window.Grid = { get liveRole() { return isLeader ? "leader" : (bc ? "follower" : "single"); }, $, $$, fmt, pick, level, esc, pill, barClass, getJSON, postJSON, every, toast, md, exportCSV, initTabs, initTables,
    onLive(fn) { subs.push(fn); if (last) { try { fn(last); } catch (e) { console.error(e); } } }, get live() { return last; } };
})();
