const drop = document.querySelector("#drop");
const detail = document.querySelector("#drop-detail");
const fileInput = document.querySelector("#file-input");
const sourceText = document.querySelector("#source-text");

let activeRequest = 0;

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
      selector: "node.hub, node.detailed, node.focused",
      style: {
        "background-color": "#fff",
        content: "data(label)",
        height: 22,
        width: "data(width)",
        padding: 6,
        shape: "round-rectangle",
        "text-background-color": "#fff",
        "text-background-opacity": 0.92,
        "text-background-padding": 3,
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
        "font-size": 8,
        "text-background-color": "#fff",
        "text-background-opacity": 1,
        "text-background-padding": 4,
        "text-rotation": "autorotate",
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
    { selector: ".faded", style: { opacity: 0.08 } }
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

function unit(value) {
  let hash = 0;
  for (const character of value) {
    hash = (Math.imul(hash, 31) + character.charCodeAt(0)) | 0;
  }
  return ((hash >>> 0) % 10000) / 10000;
}

function position(label, index) {
  const graph = document.querySelector("#cy");
  const width = Math.max(600, graph.clientWidth);
  const height = Math.max(500, graph.clientHeight);
  return {
    x: width * (0.06 + unit(`${label}:x:${index}`) * 0.88),
    y: height * (0.06 + unit(`${label}:y:${index}`) * 0.88)
  };
}

function addClaim(claim, index, requestId) {
  if (requestId !== activeRequest) return;
  const subjectId = idFor(claim.subject);
  const objectId = idFor(claim.object);
  const widthFor = (label) => Math.min(150, Math.max(44, label.length * 5.6));

  if (cy.$id(subjectId).empty()) {
    cy.add({
      group: "nodes",
      data: { id: subjectId, label: claim.subject, width: widthFor(claim.subject) },
      position: position(claim.subject, 0)
    });
  }
  if (cy.$id(objectId).empty()) {
    cy.add({
      group: "nodes",
      data: { id: objectId, label: claim.object, width: widthFor(claim.object) },
      position: position(claim.object, index)
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

  if (index < 30) cy.fit(undefined, 42);
}

function updateLabels() {
  cy.nodes().removeClass("hub detailed");
  if (cy.zoom() >= 0.72) {
    cy.nodes().addClass("detailed");
    return;
  }
  [...cy.nodes()]
    .sort((left, right) => right.degree(false) - left.degree(false))
    .slice(0, 12)
    .forEach((node) => node.addClass("hub"));
}

function finishGraph() {
  const count = cy.nodes().length;
  cy.layout({
    name: "cose",
    animate: count < 450,
    animationDuration: 650,
    componentSpacing: 90,
    coolingFactor: 0.92,
    fit: true,
    gravity: 0.12,
    idealEdgeLength: 90,
    nodeOverlap: 24,
    nodeRepulsion: 180000,
    numIter: 700,
    padding: 48,
    randomize: true
  }).run();
  window.setTimeout(updateLabels, 700);
}

async function compile(file) {
  activeRequest += 1;
  const requestId = activeRequest;
  cy.elements().remove();
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
  cy.elements().addClass("faded").removeClass("focused");
  neighborhood.removeClass("faded").addClass("focused");
  sourceText.textContent = edge.data("evidence");
}

function focusNode(node, zoom = false) {
  const neighborhood = node.closedNeighborhood();
  cy.elements().addClass("faded").removeClass("focused");
  neighborhood.removeClass("faded");
  neighborhood.nodes().addClass("focused");
  neighborhood.edges().removeClass("faded");
  if (zoom) {
    cy.animate({ fit: { eles: neighborhood, padding: 90 } }, { duration: 320 });
  }
}

function clearFocus() {
  cy.elements().removeClass("faded focused");
  sourceText.textContent = "Hover over an edge to see its source sentence.";
}

cy.on("mouseover", "edge", (event) => focus(event.target));
cy.on("mouseout", "edge", clearFocus);
cy.on("mouseover", "node", (event) => focusNode(event.target));
cy.on("mouseout", "node", clearFocus);
cy.on("tap", "edge", (event) => focus(event.target));
cy.on("tap", "node", (event) => focusNode(event.target, true));
cy.on("tap", (event) => {
  if (event.target === cy) {
    clearFocus();
    cy.animate(
      { fit: { eles: cy.elements(), padding: 48 } },
      { duration: 320 }
    );
  }
});
cy.on("zoom", updateLabels);

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
