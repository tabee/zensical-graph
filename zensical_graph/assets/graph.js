// zensical-graph: interactive knowledge graph (force-graph).
// Runs inline after its container. Safe to execute again: Zensical's instant
// navigation re-runs scripts of the new page, so every run starts from the
// DOM and tears down an earlier graph whose container is gone.
(function () {
  "use strict";
  var w = window;
  var me = document.currentScript;
  var el = (me && me.closest(".zg[data-zg]")) || document.querySelector(".zg[data-zg]");
  if (!el || el.dataset.zgReady) return;
  el.dataset.zgReady = "1";

  function teardown() {
    if (w.__zensicalGraph && !w.__zensicalGraph.el.isConnected) {
      try { w.__zensicalGraph.graph._destructor(); } catch (e) { /* old version */ }
      if (w.__zensicalGraph.ro) w.__zensicalGraph.ro.disconnect();
      w.__zensicalGraph = null;
    }
  }
  teardown();
  // Leaving the page with instant navigation: stop the animation loop.
  if (w.document$ && !w.__zensicalGraphSub) {
    w.__zensicalGraphSub = w.document$.subscribe(teardown);
  }

  var dataEl = el.querySelector("script.zg-data");
  var data = JSON.parse(dataEl ? dataEl.textContent : '{"nodes":[],"links":[]}');
  var root = el.dataset.root || "";
  var text = JSON.parse(el.dataset.text || "{}");
  var canvas = el.querySelector(".zg-canvas");
  var search = el.querySelector(".zg-search");
  var local = el.querySelector(".zg-local");
  var minInput = el.querySelector(".zg-min");
  var reset = el.querySelector(".zg-reset");

  function withLibrary(cb) {
    if (w.ForceGraph) return cb();
    var s = document.querySelector("script[data-zg-lib]");
    if (!s) {
      s = document.createElement("script");
      s.src = el.dataset.lib;
      if (el.dataset.sri) { s.integrity = el.dataset.sri; s.crossOrigin = "anonymous"; }
      s.setAttribute("data-zg-lib", "");
      document.head.appendChild(s);
    }
    s.addEventListener("load", cb);
  }

  function css(name, fallback) {
    var v = getComputedStyle(el).getPropertyValue(name).trim();
    return v || fallback;
  }
  function colors(list) {
    return (list.match(/(?:rgba?|hsla?|color-mix|oklch|lab|lch)\([^)]*\)+|#[0-9a-f]{3,8}\b|[a-z]+/gi) || []);
  }

  var sid = function (l) { return typeof l.source === "object" ? l.source.id : l.source; };
  var tid = function (l) { return typeof l.target === "object" ? l.target.id : l.target; };
  var neighbors = {};
  data.links.forEach(function (l) {
    (neighbors[l.source] = neighbors[l.source] || {})[l.target] = 1;
    (neighbors[l.target] = neighbors[l.target] || {})[l.source] = 1;
  });
  var groups = [];
  data.nodes.forEach(function (n) { if (groups.indexOf(n.group) < 0) groups.push(n.group); });
  var maxDeg = Math.max.apply(null, data.nodes.map(function (n) { return n.degree; }).concat([1]));

  var Graph, hover = null, localCenter = null, palette = [], theme = {};

  function readTheme() {
    palette = colors(css("--zg-palette", "#ff79c6, #8be9fd, #bd93f9"));
    theme = {
      link: css("--zg-link", "rgba(200,200,200,.3)"),
      active: css("--zg-link-active", "#ff79c6"),
      label: css("--zg-label", "#e6e6e6"),
      halo: css("--zg-halo", "#0f1115")
    };
  }
  function nodeColor(n) {
    if (groups.length > 1) return palette[groups.indexOf(n.group) % palette.length];
    // one group only: colour by link count (few -> last colour, hub -> first)
    var i = Math.round((1 - n.degree / maxDeg) * (Math.min(palette.length, 3) - 1));
    return palette[i];
  }
  var refit = true, MAX_ZOOM = 2.5;
  function isLit(n) { return !hover || n.id === hover.id || (neighbors[hover.id] || {})[n.id]; }
  // Node size grows gently with the link count (hub stays readable next to
  // its labels).
  function radius(n) { return 3 + 2 * Math.sqrt(Math.max(1, n.size)); }

  function drawNode(n, ctx, scale) {
    var r = radius(n), lit = isLit(n);
    ctx.globalAlpha = lit ? 1 : 0.2;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = nodeColor(n);
    ctx.shadowColor = nodeColor(n);
    ctx.shadowBlur = hover && n.id === hover.id ? 18 : 8;
    ctx.fill();
    ctx.shadowBlur = 0;
    // Label below the node, constant screen size. Fades out when zoomed out
    // (threshold grows with the number of visible nodes); hovered node and
    // its neighbours always show their label.
    var crowd = Math.max(1, Math.sqrt(Graph.graphData().nodes.length / 25));
    var a = Math.min(1, Math.max(0, (scale - 0.5 * crowd) / (0.5 * crowd)));
    if (hover && lit) a = 1;
    if (a <= 0.02) { ctx.globalAlpha = 1; return; }
    var size = 12 / scale;
    ctx.font = (hover && n.id === hover.id ? "600 " : "") + size + "px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.globalAlpha = a * (lit ? 1 : 0.35);
    ctx.lineWidth = 3 / scale;
    ctx.strokeStyle = theme.halo;
    ctx.strokeText(n.title, n.x, n.y + r + 2 / scale);
    ctx.fillStyle = theme.label;
    ctx.fillText(n.title, n.x, n.y + r + 2 / scale);
    ctx.globalAlpha = 1;
  }

  function subgraph(keep) {
    return {
      nodes: data.nodes.filter(function (n) { return keep[n.id]; }),
      links: data.links
        .filter(function (l) { return keep[sid(l)] && keep[tid(l)]; })
        .map(function (l) { return { source: sid(l), target: tid(l) }; })
    };
  }
  function applyFilters() {
    localCenter = null;
    var q = (search.value || "").toLowerCase();
    var min = parseInt(minInput.value || "0", 10);
    var keep = {};
    data.nodes.forEach(function (n) {
      if (n.degree >= min && (!q || n.title.toLowerCase().indexOf(q) >= 0 ||
          (n.path || "").toLowerCase().indexOf(q) >= 0)) keep[n.id] = 1;
    });
    refit = true;
    Graph.graphData(subgraph(keep));
  }
  function showLocal(center) {
    localCenter = center.id;
    var keep = {};
    keep[center.id] = 1;
    Object.keys(neighbors[center.id] || {}).forEach(function (id) { keep[id] = 1; });
    refit = true;
    Graph.graphData(subgraph(keep));
  }
  function open(n) {
    // A click on a real link lets Zensical's instant navigation take over.
    var a = document.createElement("a");
    a.href = root + n.url;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function init() {
    if (!el.isConnected) return;
    readTheme();
    Graph = w.ForceGraph()(canvas)
      .width(canvas.clientWidth)
      .height(canvas.clientHeight)
      .backgroundColor("rgba(0,0,0,0)")
      .nodeId("id")
      .nodePointerAreaPaint(function (n, color, ctx) {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius(n) + 2, 0, 2 * Math.PI);
        ctx.fill();
      })
      .nodeLabel(function (n) {
        return n.title + " (" + n.degree + " " + (n.degree === 1 ? text.link : text.links) + ")";
      })
      .nodeCanvasObject(drawNode)
      .linkColor(function (l) {
        return hover && (sid(l) === hover.id || tid(l) === hover.id) ? theme.active : theme.link;
      })
      .linkWidth(function (l) {
        return hover && (sid(l) === hover.id || tid(l) === hover.id) ? 2 : 1;
      })
      .linkDirectionalParticles(function (l) {
        return hover && (sid(l) === hover.id || tid(l) === hover.id) ? 2 : 0;
      })
      .linkDirectionalParticleColor(function () { return theme.active; })
      .onNodeHover(function (n) {
        hover = n || null;
        canvas.style.cursor = n ? "pointer" : null;
        // Redraw while hovering (highlight, particles); a few frames after
        // leaving the node, let force-graph pause again.
        Graph.autoPauseRedraw(false);
        if (!n) setTimeout(function () { if (!hover) Graph.autoPauseRedraw(true); }, 150);
      })
      .onNodeClick(function (n) {
        if (local.checked && localCenter !== n.id) showLocal(n);
        else open(n);
      })
      .cooldownTicks(200)
      .onEngineStop(function () {
        // Fit once per new data set (not after every drag), and never zoom in
        // further than MAX_ZOOM: small graphs would otherwise fill the canvas.
        if (!refit) return;
        refit = false;
        Graph.zoomToFit(400, 60);
        setTimeout(function () { if (Graph.zoom() > MAX_ZOOM) Graph.zoom(MAX_ZOOM, 300); }, 450);
      });
    Graph.d3Force("charge").strength(-160);
    Graph.d3Force("link").distance(60);
    w.__zensicalGraph = { el: el, graph: Graph, ro: null };
    if (w.ResizeObserver) {
      var ro = new ResizeObserver(function () {
        Graph.width(canvas.clientWidth).height(canvas.clientHeight);
      });
      ro.observe(canvas);
      w.__zensicalGraph.ro = ro;
    }
    // Palette switch (light/dark) changes the CSS variables.
    new MutationObserver(readTheme).observe(document.body, {
      attributes: true, attributeFilter: ["data-md-color-scheme"]
    });
    applyFilters();
  }

  search.addEventListener("input", applyFilters);
  minInput.addEventListener("input", applyFilters);
  local.addEventListener("change", function () { if (!local.checked) applyFilters(); });
  if (reset) reset.addEventListener("click", function () {
    search.value = "";
    minInput.value = el.dataset.min || "0";
    applyFilters();
  });
  withLibrary(init);
})();
