"use strict";

// All text from the API goes through textContent or text nodes, never parsed as HTML markup (tests/test_api.py checks this).

const TYPE_COLORS = {
  Person: "#2458c6", Organization: "#8e44ad", Phone: "#16a085", BankAccount: "#d68910",
  Vehicle: "#6c7a89", Location: "#27ae60", Event: "#c0392b",
};
const EDGE_COLORS = {
  CALLED: "#5fb3a1", TRANSFERRED_MONEY_TO: "#e0a44a", USES_PHONE: "#a9c9c0", HOLDS_ACCOUNT: "#e3cfa6",
  MEMBER_OF: "#a57bc0", MET_AT: "#6cc08b", PRESENT_AT_EVENT: "#d9776b", OWNS_VEHICLE: "#9aa6b2", ASSOCIATED_WITH: "#b8bec8",
};
const NODE_SIZES = { Person: 16, Organization: 16, Event: 14, Location: 11, Vehicle: 10, Phone: 8, BankAccount: 8 };
const LAYOUT = { name: "preset", fit: true, padding: 20 }; // positions come from the server, so drawing is instant
const HISTORY_PAGE = 25;

const state = { cy: null, fullElements: null, selected: null, view: "full", token: 0, layoutMs: null };
window.veritas = state; // exposed so browser checks can inspect what is drawn

const $ = (selector) => document.querySelector(selector);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "text") node.textContent = value;
    else if (key === "className") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child !== null && child !== undefined) node.append(child); // strings become text nodes
  }
  return node;
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

const enc = encodeURIComponent; // node ids contain "+" and ":", e.g. Phone:+919876543210

function styles() {
  // Order matters: later rules win, so base rules come first and selection states last.
  return [
    { selector: "node", style: { width: 9, height: 9, "font-size": 9, color: "#1d2330", "text-valign": "bottom", "text-margin-y": 2,
                                 "text-outline-width": 2, "text-outline-color": "#fbfcfd", "min-zoomed-font-size": 7 } },
    ...Object.entries(TYPE_COLORS).map(([type, color]) => ({
      selector: `node[type = "${type}"]`, style: { "background-color": color, width: NODE_SIZES[type], height: NODE_SIZES[type] } })),
    { selector: 'node[type = "Person"], node[type = "Organization"], node[type = "Event"]', style: { label: "data(label)" } },
    { selector: "edge", style: { width: (e) => Math.min(1 + Math.log2(e.data("count") || 1), 6), opacity: 0.5, "curve-style": "bezier",
                                 "target-arrow-shape": "triangle", "arrow-scale": 0.6 } },
    ...Object.entries(EDGE_COLORS).map(([type, color]) => ({
      selector: `edge[type = "${type}"]`, style: { "line-color": color, "target-arrow-color": color } })),
    { selector: ".faded", style: { opacity: 0.06, "text-opacity": 0 } },
    { selector: "edge.neighbour", style: { opacity: 0.95 } },
    { selector: "node.neighbour", style: { label: "data(label)" } },
    { selector: "node.focus", style: { "border-width": 3, "border-color": "#111", label: "data(label)", "font-weight": "bold" } },
    { selector: "edge.focus", style: { opacity: 1, width: 5 } },
  ];
}

function buildLegend() {
  $("#legend").replaceChildren(...Object.entries(TYPE_COLORS).map(([type, color]) => {
    const swatch = el("span", { className: "swatch" });
    swatch.style.background = color;
    return el("li", {}, [swatch, type]);
  }));
}

function runLayout() {
  const started = performance.now();
  state.cy.layout(LAYOUT).run();
  state.layoutMs = Math.round(performance.now() - started);
}

function replaceElements(elements) {
  const cy = state.cy;
  cy.batch(() => {
    cy.elements().remove();
    cy.add(elements);
  });
  runLayout();
}

function highlight(keep, focus) {
  state.cy.batch(() => {
    state.cy.elements().removeClass("focus neighbour").addClass("faded");
    keep.removeClass("faded").addClass("neighbour");
    if (focus) focus.addClass("focus");
  });
}

function clearSelection() {
  state.cy.elements().removeClass("faded focus neighbour");
  state.selected = null;
  $("#focus").disabled = true;
  $("#details-body").replaceChildren(el("p", { className: "muted", text: "Click a node or an edge." }));
  $("#history").replaceChildren(el("p", { className: "muted", text: "Select a node or edge to see the blocks that recorded it." }));
}

function table(rows) {
  return el("table", { className: "kv" }, rows.map(([key, value]) => el("tr", {}, [el("th", { text: key }), el("td", { text: String(value) })])));
}

const formatCounts = (counts) => Object.entries(counts).map(([type, n]) => `${type} ${n}`).join(", ") || "none";
const nodeLabel = (id) => { const node = state.cy.getElementById(id); return node.nonempty() ? node.data("label") : id; };

// ---------- Selection ----------

async function selectNode(id, { center = false } = {}) {
  let node = state.cy.getElementById(id);
  if (node.empty() && state.view !== "full") {
    showFull(); // e.g. a ranking click while a neighbourhood is shown
    node = state.cy.getElementById(id);
  }
  if (node.empty()) return;
  const token = ++state.token;
  state.selected = { kind: "node", id };
  $("#focus").disabled = false;
  highlight(node.closedNeighborhood(), node);
  if (center) state.cy.animate({ fit: { eles: node.closedNeighborhood(), padding: 80 } }, { duration: 250 }); // whole neighbourhood in view

  const details = await api(`/api/nodes/${enc(id)}`);
  if (token !== state.token) return; // a newer click won
  const attributes = Object.entries(details.attributes).filter(([key]) => key !== "type");
  const docs = details.source_document_ids;
  $("#details-body").replaceChildren(
    el("p", {}, [el("strong", { text: details.label }), ` (${details.type})`]),
    table([
      ["ID", details.id],
      ...attributes,
      ["Distinct neighbours", details.neighbours],
      ["Outgoing edges", formatCounts(details.outgoing_edges)],
      ["Incoming edges", formatCounts(details.incoming_edges)],
      ["Source records", `${docs.length}: ${docs.slice(0, 8).join(", ")}${docs.length > 8 ? ", …" : ""}`],
    ]),
  );
  loadHistory(id, { token });
}

function selectEdge(edge) {
  const data = edge.data();
  const token = ++state.token;
  state.selected = { kind: "edge", id: data.id, source: data.source };
  $("#focus").disabled = false;
  highlight(edge.union(edge.connectedNodes()), edge);
  const ids = data.edge_ids || [data.id];
  $("#details-body").replaceChildren(
    el("p", {}, [el("strong", { text: data.type }), ` ${nodeLabel(data.source)} → ${nodeLabel(data.target)}`]),
    table([
      ["Records", data.count || 1],
      ["First", data.first || data.timestamp],
      ["Last", data.last || data.timestamp],
      ["Extraction", (data.extraction_methods || [data.extraction_method]).join(", ")],
      ["Highest confidence", data.max_confidence ?? data.confidence],
    ]),
    el("p", { className: "muted small", text: `Underlying edges (${ids.length}${ids.length > 100 ? ", first 100 shown" : ""}). Click one for its audit trail.` }),
    el("ul", { className: "edge-list" }, ids.slice(0, 100).map((id, i) =>
      el("li", {}, el("button", { type: "button", text: `${i + 1}. ${id}`, onclick: () => loadHistory(id, { token: ++state.token }) })))),
  );
  loadHistory(ids[0], { token });
}

// ---------- Audit trail ----------

function describe(block) {
  const p = block.payload;
  if (block.operation === "node_created") {
    return `Created ${p.node.type} ${p.node.id} from ${p.node.source_document_ids.join(", ")}`;
  }
  if (block.operation === "node_merged") {
    return `Exact-match merge added source record ${p.source_document_ids_added.join(", ")}`;
  }
  if (block.operation === "edge_created") {
    const e = p.edge;
    const amount = e.amount_inr ? `, ₹${e.amount_inr}` : "";
    return `Created ${e.type} ${e.source_id} → ${e.target_id} at ${e.timestamp} from ${e.source_document_id} ` +
           `(${e.extraction_method}, confidence ${e.confidence}${amount})`;
  }
  return block.operation;
}

async function loadHistory(entityId, { token, offset = 0, includeEdges = false } = {}) {
  const isSelectedNode = state.selected?.kind === "node" && state.selected.id === entityId;
  const url = `/api/audit/history/${enc(entityId)}?limit=${HISTORY_PAGE}&offset=${offset}&include_edges=${includeEdges && isSelectedNode}`;
  const data = await api(url);
  if (token !== undefined && token !== state.token) return; // a newer selection won
  const container = $("#history");
  if (offset === 0) {
    const controls = [el("p", { text: `${data.total} block(s) recorded ${entityId}${data.include_edges ? " or its edges" : ""}.` })];
    if (isSelectedNode) {
      const box = el("input", { type: "checkbox", onchange: (event) =>
        loadHistory(entityId, { token: ++state.token, includeEdges: event.target.checked }) });
      box.checked = data.include_edges;
      controls.push(el("label", {}, [box, " include edges that touch this node"]));
    }
    container.replaceChildren(...controls);
  } else {
    container.querySelector("button.more")?.remove();
  }
  for (const block of data.blocks) {
    container.append(el("div", { className: "block" }, [
      el("div", { className: "head" }, [el("span", { className: "op", text: `#${block.idx} ${block.operation}` }),
                                          el("span", { className: "muted", text: block.recorded_at.replace("T", " ").slice(0, 19) })]),
      el("div", { text: describe(block) }),
      el("div", { className: "muted", text: `actor: ${block.actor}` }),
      el("code", { text: `hash ${block.hash.slice(0, 16)}… · prev ${block.prev_hash.slice(0, 16)}…` }),
    ]));
  }
  const shown = offset + data.blocks.length;
  if (shown < data.total) {
    container.append(el("button", { type: "button", className: "more", text: `Load more (${data.total - shown} left)`,
      onclick: () => loadHistory(entityId, { token: state.token, offset: shown, includeEdges: data.include_edges }) }));
  }
}

async function verifyChain() {
  const status = $("#verify-status");
  const button = $("#verify");
  status.className = "status running";
  status.textContent = "Verifying the chain and replaying it against the served graph…";
  button.disabled = true;
  try {
    const r = await api("/api/audit/verify", { method: "POST" });
    const ok = r.chain.ok && r.served_graph_matches_log;
    const lines = [
      `${r.chain.blocks_checked} blocks checked${r.chain.anchor_checked ? ", including the saved anchor" : "; no anchor file, so a full rewrite would pass"}`,
      `Served graph matches the audit log: ${r.served_graph_matches_log ? "yes" : "no"}`,
      ...r.chain.problems.slice(0, 8).map((p) => `Block ${p.idx}, ${p.check} check: ${p.detail}`),
      ...(r.chain.problem_count > 8 ? [`… ${r.chain.problem_count - 8} more problems`] : []),
      ...r.differences.slice(0, 5).map((d) => `Graph differs: ${d}`),
      ...(r.replay_error ? [`Log could not be replayed: ${r.replay_error}`] : []),
      `Checked at ${r.checked_at}`,
    ];
    status.className = `status ${ok ? "ok" : "bad"}`;
    status.replaceChildren(el("div", { text: ok ? "Chain verified" : "Tampering detected" }),
                           el("ul", {}, lines.map((line) => el("li", { text: line }))));
  } catch (error) {
    status.className = "status bad";
    status.textContent = `Verification request failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

// ---------- Rankings and views ----------

async function loadRanking() {
  const metric = $("#metric").value;
  const variant = $("#variant").value;
  const data = await api(`/api/centrality?metric=${enc(metric)}&variant=${enc(variant)}&limit=15`);
  $("#ranking").replaceChildren(...data.ranking.map((row) => el("li", {}, el("button", {
    type: "button", title: row.node, onclick: () => selectNode(row.node, { center: true }),
  }, [el("span", { text: row.label }), el("span", { className: "score", text: row.score.toFixed(4) })]))));
  $("#ranking-note").textContent = `${data.note} ${data.people_ranked} people ranked.`;
}

function showFull() {
  replaceElements(state.fullElements);
  state.view = "full";
  $("#view-label").textContent = "Full graph (parallel edges merged)";
}

async function showNeighbourhood() {
  if (!state.selected) return;
  const center = state.selected.kind === "node" ? state.selected.id : state.selected.source;
  const depth = $("#depth").value;
  const data = await api(`/api/nodes/${enc(center)}/subgraph?depth=${depth}`);
  const label = nodeLabel(center);
  replaceElements(data.elements);
  state.view = "neighbourhood";
  $("#view-label").textContent = `${label}, depth ${depth}: ${data.counts.nodes} nodes, ${data.counts.edges} edge records`;
  selectNode(center);
}

async function init() {
  buildLegend();
  const meta = await api("/api/meta");
  $("#notice").textContent = meta.notice;
  $("#graph-stats").textContent = `${meta.graph.nodes} nodes · ${meta.graph.edges} edge records`;
  const graph = await api("/api/graph");
  state.fullElements = graph.elements;
  state.cy = cytoscape({ container: $("#cy"), elements: graph.elements, style: styles(), layout: { name: "preset" } });
  runLayout();
  $("#view-label").textContent = "Full graph (parallel edges merged)";

  state.cy.on("tap", "node", (event) => selectNode(event.target.id()));
  state.cy.on("tap", "edge", (event) => selectEdge(event.target));
  state.cy.on("tap", (event) => { if (event.target === state.cy) clearSelection(); });
  $("#metric").addEventListener("change", loadRanking);
  $("#variant").addEventListener("change", loadRanking);
  $("#verify").addEventListener("click", verifyChain);
  $("#show-all").addEventListener("click", () => { showFull(); clearSelection(); });
  $("#focus").addEventListener("click", showNeighbourhood);
  await loadRanking();
  state.ready = true;
}

init().catch((error) => {
  $("#graph-stats").textContent = `Failed to load: ${error.message}`;
  console.error(error);
});
