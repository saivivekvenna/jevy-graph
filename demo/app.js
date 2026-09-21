const drop = document.querySelector("#drop");
const detail = document.querySelector("#drop-detail");
const fileInput = document.querySelector("#file-input");
const sourceText = document.querySelector("#source-text");
const tooltip = document.querySelector("#graph-tooltip");

let activeRequest = 0;
let selectedNodeId = null;
let overviewPositions = new Map();

const cy = cytoscape({
  container: document.querySelector("#cy"),
  elements: [],
  minZoom: 0.12,
  maxZoom: 3,
  style: [
    {
      selector: "node",
      style: {
        "background-color": "#111",
        "border-color": "#111",
        "border-width": 1,
        color: "#111",
        content: "",
        "font-family": "Inter, -apple-system, sans-serif",
        "font-size": 9,
        "font-weight": 500,
        height: 9,
        width: 9,
        padding: 0,
        shape: "ellipse",
        "text-halign": "center",
        "text-valign": "center"
      }
    },
    {
      selector: "node.hub, node.labeled, node.focused",
      style: {
        "background-color": "#fff",
        content: "data(label)",
        height: "data(height)",
        width: "data(width)",
        padding: 6,
        shape: "round-rectangle",
        "text-background-color": "#fff",
        "text-background-opacity": 0.92,
        "text-background-padding": 3,
        "text-max-width": 160,
        "text-wrap": "wrap",
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

function idFor(value) {
  let hash = 2166136261;
  for (const character of value.toLowerCase()) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `n-${(hash >>> 0).toString(36)}`;
}

function streamPosition(index) {
  const graph = document.querySelector("#cy");
  const width = Math.max(600, graph.clientWidth);
  const height = Math.max(500, graph.clientHeight);
  const angle = index * Math.PI * (3 - Math.sqrt(5));
  const radius = 54 * Math.sqrt(index);
  return {
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius
  };
}

let streamFrame = null;

function scheduleStreamFormat(requestId) {
  if (streamFrame !== null) return;
  streamFrame = window.requestAnimationFrame(() => {
    streamFrame = null;
    if (requestId !== activeRequest || selectedNodeId) return;
    updateLabels();
    cy.fit(cy.elements(), 54);
  });
}

function nextPaint() {
  return new Promise((resolve) => window.requestAnimationFrame(resolve));
}

function addClaim(claim, index, requestId) {
  if (requestId !== activeRequest) return;
  const subjectId = idFor(claim.subject);
  const objectId = idFor(claim.object);
  const widthFor = (label) => Math.min(180, Math.max(54, label.length * 5.6));
  const heightFor = (label) => Math.min(64, Math.max(24, Math.ceil(label.length / 28) * 11));

  if (cy.$id(subjectId).empty()) {
    cy.add({
      group: "nodes",
      data: {
        id: subjectId,
        label: claim.subject,
        width: widthFor(claim.subject),
        height: heightFor(claim.subject)
      },
      position: streamPosition(cy.nodes().length)
    });
  }
  if (cy.$id(objectId).empty()) {
    cy.add({
      group: "nodes",
      data: {
        id: objectId,
        label: claim.object,
        width: widthFor(claim.object),
        height: heightFor(claim.object)
      },
      position: streamPosition(cy.nodes().length)
    });
  }
  cy.add({
    group: "edges",
    data: {
      id: `e-${requestId}-${index}`,
      source: subjectId,
      target: objectId,
      label: claim.predicate.replaceAll("_", " "),
      evidence: claim.evidence
    }
  });
  document.querySelector("#cy").dataset.claims = String(cy.edges().length);

  scheduleStreamFormat(requestId);
}

function updateLabels() {
  cy.nodes().removeClass("hub");
  if (selectedNodeId) return;
  [...cy.nodes()]
    .sort((left, right) => right.degree(false) - left.degree(false))
    .slice(0, 8)
    .forEach((node) => node.addClass("hub"));
}

function finishGraph() {
  const showPrimaryNeighborhood = () => {
    overviewPositions = new Map(
      cy.nodes().map((node) => [node.id(), { ...node.position() }])
    );
    const primary = [...cy.nodes()].sort(
      (left, right) => right.degree(false) - left.degree(false)
    )[0];
    if (!primary) return;
    selectedNodeId = primary.id();
    focusNode(primary, true);
  };
  cy.layout({
    name: "cose",
    animate: false,
    componentSpacing: 90,
    coolingFactor: 0.92,
    fit: true,
    gravity: 0.12,
    idealEdgeLength: 90,
    nodeOverlap: 24,
    nodeRepulsion: 180000,
    numIter: 700,
    padding: 48,
    randomize: true,
    stop: () => window.setTimeout(showPrimaryNeighborhood, 1000)
  }).run();
}

async function compile(file) {
  activeRequest += 1;
  const requestId = activeRequest;
  selectedNodeId = null;
  overviewPositions = new Map();
  cy.elements().remove();
  tooltip.classList.remove("visible");
  document.querySelector("#cy").dataset.claims = "0";
  sourceText.textContent = "Hover over an edge to see its source sentence.";
  drop.classList.add("busy");
  detail.textContent = "PDF, TXT, DOCX";

  try {
    const response = await fetch("/api/compile", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(file.name)
      },
      body: file
    });
    if (!response.ok || !response.body) throw new Error(await response.text());

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let claimIndex = 0;

    while (requestId === activeRequest) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === "claim") {
          addClaim(event.claim, claimIndex, requestId);
          claimIndex += 1;
          if (claimIndex % 3 === 0) await nextPaint();
        } else if (event.type === "error") {
          throw new Error(event.message);
        } else if (event.type === "done") {
          finishGraph();
        }
      }
      if (done) break;
    }
  } catch (error) {
    sourceText.textContent = error.message || "The document could not be compiled.";
  } finally {
    if (requestId === activeRequest) drop.classList.remove("busy");
  }
}

function handleFiles(files) {
  const file = files?.[0];
  if (file) compile(file);
}

function focus(edge) {
  const neighborhood = edge.connectedNodes().union(edge);
  cy.elements().addClass("faded").removeClass("focused labeled hub");
  neighborhood.removeClass("faded").addClass("focused");
  sourceText.textContent = edge.data("evidence");
}

function tooltipText(edge) {
  return `${edge.source().data("label")} — ${edge.data("label")} → ${edge.target().data("label")}`;
}

function showTooltip(text, renderedPosition) {
  tooltip.textContent = text;
  tooltip.classList.add("visible");
  const graph = document.querySelector("#cy");
  const left = Math.max(16, Math.min(renderedPosition.x + 18, graph.clientWidth - 420));
  const top = Math.max(16, Math.min(renderedPosition.y + 18, graph.clientHeight - 100));
  tooltip.style.transform = `translate(${left}px, ${top}px)`;
}

function hideTooltip() {
  tooltip.classList.remove("visible");
  cy.nodes().removeClass("hovered");
}

function focusNode(node, zoom = false) {
  const allEdges = [...node.connectedEdges()];
  const edges = cy.collection(allEdges);
  const neighborhood = edges.union(edges.connectedNodes()).union(node);
  const labeledNeighbors = neighborhood.nodes().not(node);
  cy.elements().addClass("hidden").removeClass("focused labeled hub");
  neighborhood.removeClass("hidden faded");
  node.addClass("focused");
  labeledNeighbors.addClass("labeled");
  neighborhood.edges().removeClass("faded hidden");

  sourceText.textContent = `${node.data("label")} · ${allEdges.length} relationships`;
  if (zoom) {
    cy.stop();
    const neighbors = [...labeledNeighbors];
    cy.batch(() => {
      node.position({ x: 0, y: 0 });
      let offset = 0;
      let radius = 360;
      while (offset < neighbors.length) {
        const capacity = Math.max(8, Math.floor((Math.PI * 2 * radius) / 230));
        const ring = neighbors.slice(offset, offset + capacity);
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
  cy.nodes().removeClass("labeled");
  if (selectedNodeId) {
    const selected = cy.$id(selectedNodeId);
    if (selected.length) {
      focusNode(selected);
      return;
    }
  } else {
    updateLabels();
  }
  sourceText.textContent = "Hover over an edge to see its source sentence.";
}

cy.on("mouseover", "edge", (event) => {
  focus(event.target);
  showTooltip(tooltipText(event.target), event.renderedPosition);
});
cy.on("mousemove", "edge", (event) => {
  showTooltip(tooltipText(event.target), event.renderedPosition);
});
cy.on("mouseout", "edge", () => {
  hideTooltip();
  clearFocus();
});
cy.on("mouseover", "node", (event) => {
  event.target.addClass("hovered");
  showTooltip(event.target.data("label"), event.renderedPosition);
});
cy.on("mousemove", "node", (event) => {
  showTooltip(event.target.data("label"), event.renderedPosition);
});
cy.on("mouseout", "node", hideTooltip);
cy.on("tap", "edge", (event) => focus(event.target));
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
