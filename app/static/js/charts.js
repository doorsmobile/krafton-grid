/* Krafton Grid · Highcharts theme + factories. Teal/steel for data, red only for critical thresholds. */
(() => {
  if (!window.Highcharts) return;
  const C = { teal: "#2dd4bf", steel: "#8b95a5", sky: "#38bdf8", violet: "#a78bfa", amber: "#fbbf24", ok: "#34d399", crit: "#F9423A",
    grid: "#1b1b20", axis: "#26262c", label: "#8b8f98", ink: "#e5e7eb", info: "#60a5fa", steel2: "#5b6472" };
  Highcharts.setOptions({
    colors: [C.teal, C.steel, C.sky, C.violet, C.amber, C.ok, "#f472b6", C.steel2],
    chart: { backgroundColor: "transparent", style: { fontFamily: "Inter, -apple-system, sans-serif" }, spacing: [8, 6, 6, 4], animation: { duration: 300 },
      resetZoomButton: { theme: { fill: "#1a1a1e", stroke: "#2a2a30", style: { color: C.ink } } } },
    title: { text: null }, subtitle: { text: null }, credits: { enabled: false }, exporting: { enabled: false },
    accessibility: { enabled: false },
    time: { timezone: "Asia/Seoul" },
    legend: { itemStyle: { color: C.label, fontWeight: "500", fontSize: "11px" }, itemHoverStyle: { color: C.ink }, symbolRadius: 3, margin: 6, padding: 2 },
    xAxis: { lineColor: C.axis, tickColor: C.axis, gridLineColor: C.grid, labels: { style: { color: C.label, fontSize: "10.5px" } }, crosshair: { color: "#2d2d34", width: 1 } },
    yAxis: { gridLineColor: C.grid, lineColor: C.axis, labels: { style: { color: C.label, fontSize: "10.5px" } }, title: { text: null } },
    tooltip: { backgroundColor: "rgba(20,20,24,.96)", borderColor: "#2e2e35", borderRadius: 9, shadow: false, style: { color: C.ink, fontSize: "12px" },
      shared: true, valueDecimals: 2, xDateFormat: "%m-%d %H:%M:%S" },
    plotOptions: {
      series: { animation: false, marker: { enabled: false, radius: 2 }, states: { hover: { lineWidthPlus: 0 }, inactive: { opacity: .45 } }, turboThreshold: 0 },
      area: { fillOpacity: 0.12, lineWidth: 1.6, threshold: null },
      areaspline: { fillOpacity: 0.12, lineWidth: 1.6, threshold: null },
      line: { lineWidth: 1.6 }, spline: { lineWidth: 1.6 },
      column: { borderWidth: 0, borderRadius: 3, pointPadding: 0.08, groupPadding: 0.12 },
      bar: { borderWidth: 0, borderRadius: 3 },
      pie: { borderWidth: 0, dataLabels: { style: { color: C.ink, textOutline: "none", fontWeight: "500", fontSize: "11px" } } },
    },
    lang: { thousandsSep: ",", noData: "Collecting data…" },
    noData: { style: { color: C.label, fontSize: "12px", fontWeight: "500" } },
  });
  const toMs = (pts) => pts || [];
  const pct = (v, lo, hi) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));

  const K = {
    C,
    async series(metric, opts = {}) {
      const q = new URLSearchParams(); if (opts.col !== undefined) q.set("col", opts.col); if (opts.minutes) q.set("minutes", opts.minutes);
      if (opts.label) { q.set("label", opts.label); q.set("value", opts.value); } if (opts.points) q.set("points", opts.points);
      const r = await Grid.getJSON(`/api/series/${metric}?` + q); return r.points;
    },
    async seriesMulti(metric, cols, opts = {}) {
      const q = new URLSearchParams({ cols: cols.join(",") }); if (opts.minutes) q.set("minutes", opts.minutes);
      return (await Grid.getJSON(`/api/series/${metric}?` + q)).series;
    },
    spark(el, data, o = {}) {
      return Highcharts.chart(el, {
        chart: { type: "areaspline", margin: [2, 0, 2, 0], spacing: [0, 0, 0, 0], backgroundColor: "transparent" },
        xAxis: { visible: false, type: "datetime" }, yAxis: { visible: false, min: o.min, max: o.max, startOnTick: false, endOnTick: false },
        legend: { enabled: false }, tooltip: { enabled: o.tooltip !== false, shared: false, valueDecimals: o.decimals ?? 1, valueSuffix: o.unit ? " " + o.unit : "", outside: true },
        series: [{ data: toMs(data), color: o.color || C.teal, fillOpacity: 0.16, lineWidth: 1.5, name: o.name || "" }],
      });
    },
    line(el, series, o = {}) {
      const chart = { type: o.type || "line" };
      if (o.zoom) chart.zooming = { type: "x" };
      return Highcharts.chart(el, {
        chart,
        xAxis: { type: o.categories ? "category" : "datetime", categories: o.categories, plotBands: o.xBands },
        yAxis: [{ min: o.min, max: o.max, softMax: o.softMax, softMin: o.softMin, plotLines: o.plotLines, labels: o.yFormatter ? { formatter() { return o.yFormatter(this.value); } } : { format: o.yFormat || "{value}" }, title: { text: o.yTitle || null } }]
          .concat(o.y2 ? [{ opposite: true, title: { text: o.y2 }, labels: { format: o.y2Format || "{value}" } }] : []),
        legend: { enabled: o.legend ?? series.length > 1, align: "left", verticalAlign: "top", floating: false },
        tooltip: { valueDecimals: o.decimals ?? 2, valueSuffix: o.unit ? " " + o.unit : "", pointFormatter: o.pointFormatter },
        plotOptions: { series: { stacking: o.stacking } },
        series: series.map((s, i) => Object.assign({ color: Highcharts.getOptions().colors[i] }, s)),
      });
    },
    area(el, series, o = {}) { return K.line(el, series, Object.assign({ type: "areaspline" }, o)); },
    columns(el, categories, series, o = {}) {
      return Highcharts.chart(el, {
        chart: { type: o.horizontal ? "bar" : "column" },
        xAxis: { categories, labels: { style: { fontSize: "10.5px" } } },
        yAxis: { min: 0, max: o.max, plotLines: o.plotLines, labels: { formatter: o.yFormatter ? function () { return o.yFormatter(this.value); } : undefined }, stackLabels: { enabled: false } },
        legend: { enabled: o.legend ?? series.length > 1, align: "left", verticalAlign: "top" },
        tooltip: { valueDecimals: o.decimals ?? 0, pointFormatter: o.pointFormatter, shared: true },
        plotOptions: { series: { stacking: o.stacking, dataLabels: { enabled: !!o.labels, style: { color: C.ink, textOutline: "none", fontWeight: "500", fontSize: "10.5px" }, formatter: o.labelFormatter } } },
        series: series.map((s, i) => Object.assign({ color: Highcharts.getOptions().colors[i] }, s)),
      });
    },
    donut(el, data, o = {}) {
      return Highcharts.chart(el, {
        chart: { type: "pie", spacing: [0, 0, 0, 0] },
        tooltip: { pointFormatter: o.pointFormatter || function () { return `<b>${Highcharts.numberFormat(this.y, o.decimals ?? 0)}</b> (${this.percentage.toFixed(1)}%)`; }, shared: false },
        plotOptions: { pie: { innerSize: o.inner || "68%", dataLabels: { enabled: o.labels !== false, distance: 12, format: o.labelFormat || "{point.name}<br><span style='color:#8b8f98'>{point.percentage:.0f}%</span>" } } },
        series: [{ data, name: o.name || "" }],
        title: o.center ? { text: o.center, align: "center", verticalAlign: "middle", y: 8, style: { color: C.ink, fontSize: "15px", fontWeight: "650" } } : { text: null },
      });
    },
    gauge(el, value, o = {}) {
      const lo = o.min ?? 0, hi = o.max ?? 100;
      const stops = o.stops || [[0.0, C.teal], [0.8, C.teal], [0.9, C.amber], [1.0, C.crit]];
      return Highcharts.chart(el, {
        chart: { type: "solidgauge", spacing: [0, 0, 0, 0], height: o.height },
        pane: { center: ["50%", "72%"], size: "128%", startAngle: -110, endAngle: 110, background: { backgroundColor: "#1c1c21", innerRadius: "76%", outerRadius: "100%", shape: "arc", borderWidth: 0 } },
        yAxis: { min: lo, max: hi, stops, lineWidth: 0, tickWidth: 0, minorTickInterval: null, tickAmount: 0, labels: { enabled: false }, plotBands: o.bands },
        tooltip: { enabled: false },
        plotOptions: { solidgauge: { innerRadius: "76%", dataLabels: { y: -26, borderWidth: 0, useHTML: true,
          format: `<div style="text-align:center"><span style="font-size:${o.size || 22}px;font-weight:650;color:#f3f4f6;font-variant-numeric:tabular-nums">{y:.${o.decimals ?? 0}f}</span><span style="font-size:11px;color:#8b8f98"> ${o.unit || ""}</span><br><span style="font-size:10.5px;color:#8b8f98">${o.label || ""}</span></div>` } } },
        series: [{ data: [value], name: o.label || "" }],
      });
    },
    heat(el, xCats, yCats, data, o = {}) {
      return Highcharts.chart(el, {
        chart: { type: "heatmap", marginTop: 6, marginBottom: o.marginBottom ?? 36 },
        xAxis: { categories: xCats, labels: { style: { fontSize: "10px" } } },
        yAxis: { categories: yCats, reversed: true, labels: { style: { fontSize: "10px" } }, gridLineWidth: 0 },
        colorAxis: { min: o.min, max: o.max, stops: o.stops || [[0, "#10302c"], [0.5, C.teal], [0.85, C.amber], [1, C.crit]], labels: { style: { color: C.label } } },
        legend: { enabled: o.legend !== false, align: "right", layout: "vertical", verticalAlign: "middle", symbolHeight: 160 },
        tooltip: { shared: false, formatter: o.tooltip || function () { return `<b>${this.series.yAxis.categories[this.point.y]} · ${this.series.xAxis.categories[this.point.x]}</b><br>${Highcharts.numberFormat(this.point.value, 1)} ${o.unit || ""}`; } },
        series: [{ data, borderWidth: 1, borderColor: "#000", nullColor: "#16161a", dataLabels: { enabled: !!o.labels, style: { fontSize: "10px", textOutline: "none", color: "#000" } } }],
      });
    },
    sankey(el, links, o = {}) {
      return Highcharts.chart(el, {
        chart: { spacing: [6, 6, 6, 6] },
        tooltip: { shared: false, pointFormat: "{point.fromNode.name} → {point.toNode.name}: <b>{point.weight:.2f} MW</b>", nodeFormat: "{point.name}: <b>{point.sum:.2f} MW</b>" },
        series: [{ type: "sankey", keys: ["from", "to", "weight"], data: links, nodePadding: 14, nodeWidth: 12, linkOpacity: 0.28, curveFactor: 0.45,
          colors: [C.steel, C.steel, C.teal, C.violet, C.steel2, C.amber, C.teal, C.sky, C.sky, C.violet, C.violet, C.violet, C.violet],
          dataLabels: { style: { color: C.ink, textOutline: "none", fontSize: "11px", fontWeight: "500" }, nodeFormat: "{point.name} · {point.sum:.2f}" } }],
      });
    },
    xrange(el, cats, data, o = {}) {
      return Highcharts.chart(el, {
        chart: { type: "xrange" },
        xAxis: { type: "datetime", plotLines: [{ value: Date.now(), color: C.crit, width: 1, dashStyle: "Dash", label: { text: "today", style: { color: C.crit, fontSize: "10px" } } }] },
        yAxis: { categories: cats, reversed: true, gridLineWidth: 0, labels: { style: { color: C.ink, fontSize: "11px" } } },
        legend: { enabled: false },
        tooltip: { shared: false, pointFormat: "<b>{point.phase}</b><br>{point.x:%Y-%m} → {point.x2:%Y-%m}" },
        series: [{ data, borderRadius: 4, pointWidth: 16, dataLabels: { enabled: true, format: "{point.phase}", style: { fontSize: "10px", textOutline: "none", color: "#0b0b0d", fontWeight: "600" } } }],
      });
    },
    // append the latest value from a live payload to a time series chart
    push(chart, i, ms, value, max = 1800) { const s = chart && chart.series[i]; if (!s || value === undefined || value === null) return; s.addPoint([ms, value], true, s.data.length >= max, false); },
    pct,
  };
  window.GridCharts = K;
})();
