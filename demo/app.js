const drop = document.querySelector("#drop");
const fileInput = document.querySelector("#file-input");
const graph = document.querySelector("#cy");
const sourceText = document.querySelector("#source-text");
const tripleText = document.querySelector("#triple-text");
const edgeCount = document.querySelector("#edge-count");
const nodeCount = document.querySelector("#node-count");
const elapsedTime = document.querySelector("#elapsed-time");
const MEDIUM_GRAPH_NODES = 900;
const LARGE_GRAPH_NODES = 2500;

let activeRequest = 0;
let uploadController = null;
let selectedNodeId = null;
let overviewPositions = new Map();

const cy = cytoscape({
  container: graph,
  elements: [],
  hideEdgesOnViewport: true,
  textureOnViewport: true,
  minZoom: 0.12,
  maxZoom: 3,
  style: [
    {
      selector: "node",
      style: {
        "background-color": "#fff",
        "border-color": "#111",
        "border-width": 1,
        color: "#111",
        content: "data(label)",
        "font-family": "Inter, -apple-system, sans-serif",
        "font-size": 11,
        "font-weight": 600,
        height: "data(height)",
        width: "data(width)",
        padding: 6,
        shape: "round-rectangle",
        "text-background-color": "#fff",
        "text-background-opacity": 0.92,
        "text-background-padding": 3,
        "text-halign": "center",
        "text-justification": "center",
        "text-max-width": 160,
        "text-valign": "center",
        "text-wrap": "wrap",
        "line-height": 1.15,
        "z-index": 11
      }
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": "#c2c2c2",
        "target-arrow-color": "#777",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.55,
        width: 0.8
      }
    },
    {
      selector: "edge.focused",
      style: {
        "line-color": "#111",
        "target-arrow-color": "#111",
        width: 2,
        label: "data(label)",
        color: "#111",
        "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "font-size": 11,
        "text-background-color": "#fff",
        "text-background-opacity": 1,
        "text-background-padding": 4,
        "text-max-width": 180,
        "text-rotation": "none",
        "text-wrap": "wrap",
        "z-index": 10
      }
    },
    {
      selector: "node.focused",
      style: {
        "background-color": "#111",
        "border-color": "#111",
        color: "#fff",
        "text-background-color": "#111",
        "text-background-opacity": 1,
        "z-index": 11
      }
    },
    {
      selector: "node.hovered",
      style: {
        "border-width": 3,
        "z-index": 20
      }
    },
    { selector: ".faded", style: { opacity: 0 } },
    { selector: ".hidden", style: { display: "none" } }
  ],
  layout: { name: "preset" }
});

cy.layoutUtilities({
  componentSpacing: 120,
  desiredAspectRatio: 1.5,
  polyominoGridSizeFactor: 0.75
});

function idFor(value) {
  let hash = 2166136261;
  for (const character of value.toLowerCase()) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `n-${(hash >>> 0).toString(36)}`;
}

function streamPosition(index) {
  const width = Math.max(600, graph.clientWidth);
  const height = Math.max(500, graph.clientHeight);
  const angle = index * Math.PI * (3 - Math.sqrt(5));
  const radius = 150 * Math.sqrt(index);
  return {
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius
  };
}

let renderFrame = null;
let pendingClaims = [];
let streamFinished = false;
let nextClaimIndex = 0;
let lastStreamFitAt = 0;
let lastStreamFitNodeCount = 0;

function updateGraphStats() {
  edgeCount.textContent = String(cy.edges().length);
  nodeCount.textContent = String(cy.nodes().length);
}

function fitStreamGraph(force = false) {
  const now = performance.now();
  const nodes = cy.nodes().length;
  const shouldFit =
    force ||
    nodes < MEDIUM_GRAPH_NODES ||
    now - lastStreamFitAt >= 350 ||
    nodes - lastStreamFitNodeCount >= 300;
  if (!shouldFit) return;

  cy.fit(cy.elements(), 54);
  lastStreamFitAt = now;
  lastStreamFitNodeCount = nodes;
}

function addClaims(items, requestId) {
  const widthFor = (label) => Math.min(220, Math.max(68, label.length * 7));
  const heightFor = (label) =>
    Math.min(84, Math.max(32, Math.ceil(label.length / 26) * 15));
  const nodeIds = new Set(cy.nodes().map((node) => node.id()));
  const elements = [];

  for (const { claim, index } of items) {
    const subjectId = idFor(claim.subject);
    const objectId = idFor(claim.object);
    for (const [id, label] of [
      [subjectId, claim.subject],
      [objectId, claim.object]
    ]) {
      if (nodeIds.has(id)) continue;
      elements.push({
        group: "nodes",
        data: {
          id,
          label,
          width: widthFor(label),
          height: heightFor(label)
        },
        position: streamPosition(nodeIds.size)
      });
      nodeIds.add(id);
    }
    elements.push({
      group: "edges",
      data: {
        id: `e-${requestId}-${index}`,
        source: subjectId,
        target: objectId,
        label: claim.predicate.replaceAll("_", " "),
        evidence: claim.evidence
      }
    });
  }
  cy.add(elements);
}

function scheduleRender(requestId) {
  if (renderFrame !== null) return;
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = null;
    if (requestId !== activeRequest) return;

    const ready = pendingClaims;
    pendingClaims = [];
    if (ready.length) {
      addClaims(ready, requestId);
      updateGraphStats();
      if (!selectedNodeId) fitStreamGraph();
    }

    if (pendingClaims.length) {
      scheduleRender(requestId);
    } else if (streamFinished) {
      streamFinished = false;
      window.requestAnimationFrame(() => {
        if (requestId === activeRequest) finishGraph(requestId);
      });
    }
  });
}

function enqueueClaim(claim, requestId) {
  enqueueClaims([claim], requestId);
}

function enqueueClaims(claims, requestId) {
  if (requestId !== activeRequest) return;
  for (const claim of claims) {
    pendingClaims.push({ claim, index: nextClaimIndex });
    nextClaimIndex += 1;
  }
  scheduleRender(requestId);
}

function finishGraph(requestId) {
  const preserveOverview = () => {
    if (requestId !== activeRequest) return;
    selectedNodeId = null;
    overviewPositions = new Map(
      cy.nodes().map((node) => [node.id(), { ...node.position() }])
    );
    fitStreamGraph(true);
    drop.classList.remove("busy");
  };

  const nodes = cy.nodes().length;
  if (nodes > LARGE_GRAPH_NODES) {
    preserveOverview();
    return;
  }

  const mediumGraph = nodes > MEDIUM_GRAPH_NODES;
  cy.layout({
    name: "fcose",
    quality: mediumGraph ? "default" : "proof",
    randomize: true,
    animate: false,
    fit: true,
    padding: 64,
    nodeDimensionsIncludeLabels: !mediumGraph,
    uniformNodeDimensions: false,
    packComponents: true,
    nodeSeparation: 110,
    nodeRepulsion: () => 16000,
    idealEdgeLength: () => 170,
    edgeElasticity: () => 0.2,
    tilingPaddingHorizontal: 70,
    tilingPaddingVertical: 70,
    gravity: 0.12,
    gravityRange: 4.5,
    initialEnergyOnIncremental: 0.5,
    stop: preserveOverview
  }).run();
}

async function compile(file) {
  uploadController?.abort();
  uploadController = new AbortController();
  activeRequest += 1;
  const requestId = activeRequest;
  const startedAt = performance.now();
  const updateTimer = () => {
    if (requestId === activeRequest) {
      elapsedTime.textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)}s`;
    }
  };
  elapsedTime.textContent = "0.0s";
  const timer = window.setInterval(updateTimer, 100);
  const stopTimer = () => {
    window.clearInterval(timer);
    updateTimer();
  };
  selectedNodeId = null;
  overviewPositions = new Map();
  pendingClaims = [];
  streamFinished = false;
  nextClaimIndex = 0;
  lastStreamFitAt = 0;
  lastStreamFitNodeCount = 0;
  if (renderFrame !== null) {
    window.cancelAnimationFrame(renderFrame);
    renderFrame = null;
  }
  cy.elements().remove();
  updateGraphStats();
  setSourceText("Hover over an edge or leaf node to see its source sentence.");
  drop.classList.add("busy");

  try {
    const response = await fetch("/api/compile", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(file.name)
      },
      signal: uploadController.signal,
      body: file
    });
    if (!response.ok || !response.body) throw new Error(await response.text());

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let receivedDone = false;

    while (requestId === activeRequest) {
      const { value, done } = await reader.read();
      if (requestId !== activeRequest) break;
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === "claim") {
          enqueueClaim(event.claim, requestId);
        } else if (event.type === "graph") {
          enqueueClaims(event.claims, requestId);
        } else if (event.type === "error") {
          throw new Error(event.message);
        } else if (event.type === "done") {
          stopTimer();
          receivedDone = true;
          streamFinished = true;
          scheduleRender(requestId);
        }
      }
      if (done) break;
    }
    if (requestId === activeRequest && !receivedDone) {
      throw new Error("The compilation stream ended before completion.");
    }
  } catch (error) {
    if (requestId !== activeRequest || error.name === "AbortError") return;
    setSourceText(error.message || "The document could not be compiled.");
    if (requestId === activeRequest) drop.classList.remove("busy");
  } finally {
    window.clearInterval(timer);
    if (!streamFinished) updateTimer();
  }
}

function handleFiles(files) {
  const file = files?.[0];
  if (file) compile(file);
}

function showEdgeDetails(edge) {
  setSourceText(edge.data("evidence"), `${edge.source().data("label")} — ${edge.data("label")} → ${edge.target().data("label")}`);
}

function setSourceText(text, triple = "") {
  tripleText.textContent = triple || "—";
  sourceText.textContent = text;
  sourceText.classList.toggle("long", text.length > 260);
  sourceText.classList.toggle("very-long", text.length > 440);
  window.requestAnimationFrame(() => cy.resize());
}

function focusNode(node, zoom = false) {
  const allEdges = [...node.connectedEdges()];
  const edges = cy.collection(allEdges);
  const neighborhood = edges.union(edges.connectedNodes()).union(node);
  const neighbors = neighborhood.nodes().not(node);
  cy.elements().addClass("hidden").removeClass("focused");
  neighborhood.removeClass("hidden faded");
  node.addClass("focused");
  neighborhood.edges().removeClass("faded hidden");

  setSourceText(`${node.data("label")} · ${allEdges.length} relationships`);
  if (zoom) {
    cy.stop();
    const positionedNeighbors = [...neighbors];
    cy.batch(() => {
      node.position({ x: 0, y: 0 });
      let offset = 0;
      let radius = 360;
      while (offset < positionedNeighbors.length) {
        const capacity = Math.max(8, Math.floor((Math.PI * 2 * radius) / 230));
        const ring = positionedNeighbors.slice(offset, offset + capacity);
        ring.forEach((neighbor, index) => {
          const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ring.length;
          neighbor.position({
            x: Math.cos(angle) * radius,
            y: Math.sin(angle) * radius
          });
        });
        offset += ring.length;
        radius += 280;
      }
    });
    window.setTimeout(() => cy.fit(neighborhood, 100), 150);
  }
}

function restoreOverview() {
  cy.nodes().positions((node) => overviewPositions.get(node.id()) || node.position());
}

function clearFocus() {
  cy.elements().removeClass("faded focused hidden");
  if (selectedNodeId) {
    const selected = cy.$id(selectedNodeId);
    if (selected.length) {
      focusNode(selected);
      return;
    }
  }
  setSourceText("Hover over an edge or leaf node to see its source sentence.");
}

cy.on("mouseover", "edge", (event) => {
  showEdgeDetails(event.target);
});
cy.on("mouseover", "node", (event) => {
  const node = event.target;
  const edges = node.connectedEdges();
  if (edges.length === 1) {
    showEdgeDetails(edges[0]);
  } else {
    setSourceText(`${node.data("label")} · ${edges.length} relationships. Hover over an edge to see its triple and source sentence.`);
  }
});
cy.on("tap", "edge", (event) => showEdgeDetails(event.target));
cy.on("tap", "node", (event) => {
  selectedNodeId = event.target.id();
  focusNode(event.target, true);
});
cy.on("tap", (event) => {
  if (event.target === cy) {
    selectedNodeId = null;
    restoreOverview();
    clearFocus();
    cy.animate(
      { fit: { eles: cy.elements(), padding: 48 } },
      { duration: 320 }
    );
  }
});

fileInput.addEventListener("change", (event) => handleFiles(event.target.files));

for (const eventName of ["dragenter", "dragover"]) {
  drop.addEventListener(eventName, (event) => {
    event.preventDefault();
    drop.classList.add("dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  drop.addEventListener(eventName, (event) => {
    event.preventDefault();
    drop.classList.remove("dragging");
  });
}

drop.addEventListener("drop", (event) => handleFiles(event.dataTransfer.files));
