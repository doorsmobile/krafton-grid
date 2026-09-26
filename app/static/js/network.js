/* Network overview — topology canvas (detail opens as pages) */

window.DCIMNetwork = (function () {
  function drawTopology(topo) {
    const canvas = document.getElementById("topo-canvas");
    if (!canvas || !topo) return;
    const w = canvas.clientWidth || 640;
    const h = 320;
    canvas.style.height = h + "px";
    const spines = (topo.nodes || []).filter((n) => n.role === "spine");
    const leaves = (topo.nodes || []).filter((n) => n.role === "leaf").slice(0, 24);
    const ibs = (topo.nodes || []).filter((n) => n.role === "ib-switch").slice(0, 12);
    const pos = {};
    function place(list, y) {
      list.forEach((node, i) => {
        pos[node.id] = { x: ((i + 1) / (list.length + 1)) * w, y, node };
      });
    }
    place(spines, 48);
    place(leaves, 150);
    place(ibs, 260);

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", h);
    const linkLayer = document.createElementNS(svgNS, "g");
    (topo.links || []).forEach((L) => {
      const a = pos[L.source],
        b = pos[L.target];
      if (!a || !b) return;
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", a.x);
      line.setAttribute("y1", a.y);
      line.setAttribute("x2", b.x);
      line.setAttribute("y2", b.y);
      line.setAttribute("class", L.kind === "ib-fabric" ? "topo-link ib" : "topo-link eth");
      linkLayer.appendChild(line);
    });
    svg.appendChild(linkLayer);
    Object.values(pos).forEach(({ x, y, node }) => {
      const g = document.createElementNS(svgNS, "g");
      g.setAttribute("class", "topo-node " + node.role);
      g.style.cursor = "pointer";
      g.addEventListener("click", () => {
        location.href = "/network/device/" + encodeURIComponent(node.id);
      });
      const r = document.createElementNS(svgNS, "rect");
      r.setAttribute("x", x - 28);
      r.setAttribute("y", y - 12);
      r.setAttribute("width", 56);
      r.setAttribute("height", 24);
      r.setAttribute("rx", 5);
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", x);
      t.setAttribute("y", y + 4);
      t.setAttribute("text-anchor", "middle");
      t.textContent = node.id.replace(/^AR-/, "").replace(/^IB-/, "IB");
      g.appendChild(r);
      g.appendChild(t);
      svg.appendChild(g);
    });
    canvas.innerHTML = "";
    canvas.appendChild(svg);
  }

  function initOverview(opts) {
    drawTopology((opts || {}).topology);
  }

  return { initOverview };
})();
