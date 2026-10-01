/* Krafton Grid · 5,000-GPU canvas heat grid (40 racks × 16 nodes × 8 GPUs) */
(() => {
  const RAMPS = {
    util: [[0, [24, 27, 33]], [0.05, [22, 46, 52]], [0.4, [16, 92, 88]], [0.75, [20, 158, 139]], [0.92, [45, 212, 191]], [1, [190, 247, 234]]],
    sm: [[0, [24, 27, 33]], [0.05, [22, 46, 52]], [0.4, [16, 92, 88]], [0.75, [20, 158, 139]], [0.92, [45, 212, 191]], [1, [190, 247, 234]]],
    temp: [[0, [28, 70, 96]], [0.45, [45, 212, 191]], [0.72, [251, 191, 36]], [0.86, [249, 115, 22]], [1, [249, 66, 58]]],
    power: [[0, [40, 44, 52]], [0.3, [91, 100, 114]], [0.7, [45, 212, 191]], [1, [251, 191, 36]]],
    mem: [[0, [26, 30, 36]], [0.5, [99, 102, 241]], [1, [167, 139, 250]]],
  };
  const lerp = (a, b, t) => a + (b - a) * t;
  function color(ramp, t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < ramp.length; i++) {
      if (t <= ramp[i][0]) {
        const [p0, c0] = ramp[i - 1], [p1, c1] = ramp[i];
        const k = (t - p0) / (p1 - p0 || 1);
        return `rgb(${Math.round(lerp(c0[0], c1[0], k))},${Math.round(lerp(c0[1], c1[1], k))},${Math.round(lerp(c0[2], c1[2], k))})`;
      }
    }
    const c = ramp[ramp.length - 1][1]; return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  function rampCSS(metric) {
    const r = RAMPS[metric] || RAMPS.util;
    return "linear-gradient(90deg," + r.map(([p, c]) => `rgb(${c.join(",")}) ${p * 100}%`).join(",") + ")";
  }

  class HeatGrid {
    constructor(wrap, opts = {}) {
      this.wrap = wrap; this.opts = opts;
      this.canvas = document.createElement("canvas"); wrap.appendChild(this.canvas);
      this.tip = document.createElement("div"); this.tip.className = "heat-tip"; this.tip.style.display = "none"; document.body.appendChild(this.tip);
      this.data = null; this.hover = null; this.metric = opts.metric || "util";
      this.canvas.addEventListener("mousemove", (e) => this.onMove(e));
      this.canvas.addEventListener("mouseleave", () => { this.tip.style.display = "none"; this.hover = null; });
      this.canvas.addEventListener("click", () => { if (this.hover && this.hover.id) location.href = "/gpu-fleet/device/" + this.hover.id; });
      window.addEventListener("resize", () => this.draw());
    }
    layout() {
      const W = this.wrap.clientWidth || 900;
      const labelW = 38, nodeGap = 3, gpuGap = 1;
      const cols = 16, per = 8;
      const cell = Math.max(3, Math.floor((W - labelW - cols * nodeGap) / (cols * per)) - gpuGap);
      const rowH = 12, rowGap = 3, groupGap = 9;
      return { W, labelW, nodeGap, gpuGap, cols, per, cell, rowH, rowGap, groupGap };
    }
    set(d) { this.data = d; this.metric = d.metric; this.draw(); }
    draw() {
      const d = this.data; if (!d) return;
      const L = this.layout(); this.L = L;
      const racks = d.racks.length;
      const groups = Math.ceil(racks / 5);
      const H = racks * (L.rowH + L.rowGap) + (groups - 1) * L.groupGap + 4;
      const dpr = window.devicePixelRatio || 1;
      const c = this.canvas; c.width = L.W * dpr; c.height = H * dpr; c.style.height = H + "px";
      const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, L.W, H);
      const ramp = RAMPS[d.metric] || RAMPS.util;
      const span = (d.max - d.min) || 1;
      g.font = "600 10px JetBrains Mono, monospace"; g.textBaseline = "middle";
      this.rowsY = [];
      for (let r = 0; r < racks; r++) {
        const y = r * (L.rowH + L.rowGap) + Math.floor(r / 5) * L.groupGap + 2;
        this.rowsY.push(y);
        g.fillStyle = "#6b7280"; g.fillText(d.racks[r], 0, y + L.rowH / 2);
        for (let s = 0; s < L.cols; s++) {
          for (let k = 0; k < L.per; k++) {
            const i = r * d.cols + s * L.per + k;
            const v = d.values[i];
            const x = L.labelW + s * (L.per * (L.cell + L.gpuGap) + L.nodeGap) + k * (L.cell + L.gpuGap);
            if (v < 0) { g.fillStyle = "#0c0c0e"; g.fillRect(x, y, L.cell, L.rowH); continue; }
            const st = d.status[i];
            g.fillStyle = st === 3 ? "#F9423A" : st === 4 ? "#5a1512" : color(ramp, (v - d.min) / span);
            g.fillRect(x, y, L.cell, L.rowH);
            if (st === 1) { g.fillStyle = "rgba(251,191,36,.85)"; g.fillRect(x, y + L.rowH - 2, L.cell, 2); }
            if (st === 2) { g.strokeStyle = "#fff"; g.lineWidth = 1; g.strokeRect(x + .5, y + .5, L.cell - 1, L.rowH - 1); }
          }
        }
      }
      if (this.opts.onDraw) this.opts.onDraw(d);
    }
    onMove(e) {
      const d = this.data, L = this.L; if (!d || !L) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      let r = -1;
      for (let i = 0; i < this.rowsY.length; i++) if (y >= this.rowsY[i] && y < this.rowsY[i] + L.rowH + L.rowGap) { r = i; break; }
      const nodeW = L.per * (L.cell + L.gpuGap) + L.nodeGap;
      const s = Math.floor((x - L.labelW) / nodeW), k = Math.floor(((x - L.labelW) - s * nodeW) / (L.cell + L.gpuGap));
      if (r < 0 || s < 0 || s >= L.cols || k < 0 || k >= L.per) { this.tip.style.display = "none"; this.hover = null; return; }
      const i = r * d.cols + s * L.per + k, v = d.values[i];
      if (v < 0) { this.tip.style.display = "none"; this.hover = null; return; }
      const rack = d.racks[r].toLowerCase();
      const id = `kg-${rack}-n${String(s + 1).padStart(2, "0")}-g${k}`;
      this.hover = { id };
      const st = d.legend[String(d.status[i])];
      this.tip.innerHTML = `<b>${id}</b>${d.metric} <span style="float:right;font-weight:650">${Grid.fmt.f1(v)} ${d.unit}</span><br><span class="muted">status</span> <span style="float:right">${st}</span><br><span class="faint xs">click for device detail</span>`;
      this.tip.style.display = "block";
      this.tip.style.left = Math.min(window.innerWidth - 220, e.clientX + 14) + "px";
      this.tip.style.top = e.clientY + 14 + "px";
    }
  }
  window.HeatGrid = HeatGrid;
  window.HeatGrid.rampCSS = rampCSS;
  window.HeatGrid.color = (metric, t) => color(RAMPS[metric] || RAMPS.util, t);
})();
