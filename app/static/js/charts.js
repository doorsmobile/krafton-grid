/* Highcharts theme — Krafton Grid DCIM */

window.DCIMCharts = (function () {
  const palette = {
    teal: "#2dd4bf",
    steel: "#94a3b8",
    amber: "#eab308",
    crimson: "#F9423A",
    soft: "#64748b",
    ink: "#e5e7eb",
    muted: "#9ca3af",
    red: "#F9423A",
    black: "#000000",
    info: "#3b82f6",
    ok: "#22c55e",
  };

  Highcharts.setOptions({
    chart: {
      backgroundColor: "transparent",
      style: { fontFamily: "IBM Plex Sans, sans-serif", color: palette.ink },
      animation: { duration: 450 },
    },
    title: { style: { display: "none" } },
    credits: { enabled: false },
    legend: {
      itemStyle: { color: palette.muted, fontWeight: "500" },
      itemHoverStyle: { color: palette.ink },
    },
    xAxis: {
      lineColor: "rgba(255,255,255,0.12)",
      tickColor: "rgba(255,255,255,0.12)",
      labels: { style: { color: palette.muted } },
    },
    yAxis: {
      gridLineColor: "rgba(255,255,255,0.06)",
      title: { style: { color: palette.muted } },
      labels: { style: { color: palette.muted } },
    },
    tooltip: {
      backgroundColor: "rgba(15,15,15,0.94)",
      style: { color: "#fff" },
      borderWidth: 0,
      shadow: false,
    },
  });

  function parseSeries(points) {
    return (points || []).map((p) => [Date.parse(p.t), p.v]);
  }

  async function fetchSeries(metric, limit = 60) {
    const res = await fetch(`/api/series/${metric}?limit=${limit}`);
    return parseSeries(await res.json());
  }

  function lineChart(el, series, opts = {}) {
    return Highcharts.chart(el, {
      chart: { type: "areaspline", zoomType: "x" },
      xAxis: { type: "datetime" },
      yAxis: { title: { text: opts.yTitle || null } },
      plotOptions: {
        areaspline: {
          fillOpacity: 0.18,
          marker: { enabled: false },
          lineWidth: 2.2,
        },
      },
      series: series.map((s, i) => ({
        name: s.name,
        data: s.data,
        color: s.color || [palette.teal, palette.steel, palette.amber][i % 3],
      })),
      ...opts.extra,
    });
  }

  function gauge(el, value, max, opts = {}) {
    return Highcharts.chart(el, {
      chart: { type: "solidgauge", height: opts.height || 220 },
      pane: {
        center: ["50%", "70%"],
        size: "130%",
        startAngle: -90,
        endAngle: 90,
        background: {
          backgroundColor: "rgba(15,28,46,0.06)",
          innerRadius: "70%",
          outerRadius: "100%",
          shape: "arc",
        },
      },
      yAxis: {
        min: 0,
        max,
        stops: [
          [0.55, palette.teal],
          [0.8, palette.amber],
          [0.92, palette.crimson],
        ],
        lineWidth: 0,
        tickWidth: 0,
        minorTickInterval: null,
        labels: { enabled: false },
      },
      series: [
        {
          name: opts.name || "Value",
          data: [value],
          dataLabels: {
            format:
              '<div style="text-align:center;font-family:Sora,sans-serif">' +
              '<span style="font-size:1.55rem;font-weight:700">{y:.1f}</span><br/>' +
              `<span style="font-size:0.75rem;color:${palette.muted}">${opts.unit || ""}</span></div>`,
            borderWidth: 0,
            y: -18,
          },
        },
      ],
    });
  }

  function columnChart(el, categories, data, opts = {}) {
    return Highcharts.chart(el, {
      chart: { type: "column" },
      xAxis: { categories },
      yAxis: { title: { text: opts.yTitle || null } },
      plotOptions: {
        column: {
          borderRadius: 6,
          color: {
            linearGradient: { x1: 0, x2: 0, y1: 0, y2: 1 },
            stops: [
              [0, palette.teal],
              [1, palette.steel],
            ],
          },
        },
      },
      series: [{ name: opts.name || "MW", data, showInLegend: false }],
    });
  }

  /** Multi-series column (optionally stacked) for cost monthly trends */
  function columnSeriesChart(el, categories, seriesList, opts = {}) {
    const colors = [palette.teal, palette.steel, palette.amber, palette.soft, palette.crimson, "#5b8def"];
    return Highcharts.chart(el, {
      chart: { type: "column", height: opts.height || 340 },
      xAxis: { categories, labels: { rotation: categories.length > 8 ? -35 : 0 } },
      yAxis: {
        title: { text: opts.yTitle || "KRW" },
        labels: {
          formatter: function () {
            const v = this.value;
            if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(1) + "억";
            if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(0) + "만";
            return v;
          },
        },
      },
      tooltip: {
        shared: true,
        formatter: function () {
          let s = `<b>${this.x}</b>`;
          this.points.forEach((p) => {
            s += `<br/>${p.series.name}: ₩${Highcharts.numberFormat(p.y, 0)}`;
          });
          return s;
        },
      },
      plotOptions: {
        column: {
          borderRadius: 4,
          stacking: opts.stacked ? "normal" : undefined,
          grouping: !opts.stacked,
        },
      },
      series: seriesList.map((s, i) => ({
        name: s.name,
        data: s.data,
        color: s.color || colors[i % colors.length],
        type: s.type || "column",
      })),
    });
  }

  function pieChart(el, data) {
    return Highcharts.chart(el, {
      chart: { type: "pie" },
      plotOptions: {
        pie: {
          innerSize: "58%",
          dataLabels: { enabled: true, distance: 12, style: { fontWeight: "500", color: palette.ink, textOutline: "none" } },
        },
      },
      colors: [palette.teal, palette.steel, palette.amber, palette.soft, palette.crimson],
      series: [{ name: "Share", data }],
    });
  }

  /** Compact sparkline for dashboard cards (no axes / no tooltip). */
  function sparkline(el, data, opts = {}) {
    const color = opts.color || palette.red;
    return Highcharts.chart(el, {
      chart: {
        type: "areaspline",
        height: opts.height || 52,
        margin: [4, 0, 2, 0],
        backgroundColor: "transparent",
        skipClone: true,
      },
      title: { text: null },
      xAxis: { visible: false, type: "datetime" },
      yAxis: {
        visible: false,
        min: opts.min,
        max: opts.max,
        startOnTick: false,
        endOnTick: false,
      },
      legend: { enabled: false },
      tooltip: { enabled: false },
      plotOptions: {
        areaspline: {
          enableMouseTracking: false,
          fillOpacity: 0.22,
          marker: { enabled: false },
          lineWidth: 1.8,
          color,
          fillColor: {
            linearGradient: { x1: 0, x2: 0, y1: 0, y2: 1 },
            stops: [
              [0, Highcharts.color(color).setOpacity(0.35).get("rgba")],
              [1, Highcharts.color(color).setOpacity(0.02).get("rgba")],
            ],
          },
        },
      },
      series: [{ data: data || [], name: opts.name || "spark" }],
    });
  }

  /** Tiny solid-gauge for card tiles. */
  function miniGauge(el, value, max, opts = {}) {
    return Highcharts.chart(el, {
      chart: { type: "solidgauge", height: opts.height || 88, margin: [0, 0, 0, 0] },
      pane: {
        center: ["50%", "55%"],
        size: "120%",
        startAngle: -90,
        endAngle: 90,
        background: {
          backgroundColor: "rgba(15,28,46,0.07)",
          innerRadius: "72%",
          outerRadius: "100%",
          shape: "arc",
        },
      },
      yAxis: {
        min: 0,
        max,
        stops: [
          [0.45, palette.teal],
          [0.8, palette.amber],
          [0.92, palette.crimson],
        ],
        lineWidth: 0,
        tickWidth: 0,
        minorTickInterval: null,
        labels: { enabled: false },
      },
      tooltip: { enabled: false },
      plotOptions: {
        solidgauge: { enableMouseTracking: false, dataLabels: { enabled: false } },
      },
      series: [{ name: opts.name || "v", data: [value] }],
    });
  }

  return { palette, parseSeries, fetchSeries, lineChart, gauge, columnChart, columnSeriesChart, pieChart, sparkline, miniGauge };
})();
