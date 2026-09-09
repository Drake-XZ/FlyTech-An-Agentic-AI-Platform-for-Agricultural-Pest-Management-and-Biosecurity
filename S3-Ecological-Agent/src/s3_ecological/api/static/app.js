const FIXED_LIMITATIONS = [
  "The visual model recognizes exactly four genera (Anastrepha, Bactrocera, " +
    "Ceratitis, Rhagoletis) in a closed-set softmax. The four probabilities " +
    "sum to 1, but this does not mean only these four taxa exist in the " +
    "world - there is no unknown-class detection.",
  "The geographic prior and fusion weights are research-reproduction " +
    "results, not a validated production model.",
  "This demo does not claim species confirmation, pest-quarantine " +
    "conclusions, incursion confirmation, absence evidence, production " +
    "readiness, or biosecurity efficacy.",
  "No online map, GBIF, ALA, or environmental service is called by this demo.",
  "Occurrence-based evidence records shown below are a small synthetic " +
    "fixture dataset for demonstration, not live occurrence data.",
];

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child) node.appendChild(child);
  }
  return node;
}

function formatScore(value) {
  return value === null || value === undefined ? "unavailable" : value.toFixed(3);
}

function formatPercent(value) {
  return value === null || value === undefined ? "unavailable" : (value * 100).toFixed(1) + "%";
}

async function useSampleImage() {
  const response = await fetch("/static/sample_specimen.png");
  const blob = await response.blob();
  const file = new File([blob], "sample_specimen.png", { type: "image/png" });
  const input = document.getElementById("image");
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  input.files = dataTransfer.files;
  showPreview(file);
}

function showPreview(file) {
  const preview = document.getElementById("preview");
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
}

function renderSummary(assessment) {
  const top = assessment.reranked_candidates[0];
  const container = el(
    "div",
    {},
    el("h2", { text: "A. Summary (research demo, closed-set, four genera only)" }),
    el(
      "p",
      {},
      el("strong", { text: "Top candidate: " }),
      document.createTextNode(top ? top.submitted_name : "none ranked")
    ),
    el(
      "p",
      {},
      el("strong", { text: "Risk state: " }),
      document.createTextNode(assessment.risk_state)
    ),
    el(
      "p",
      {},
      el("strong", { text: "Review suggested: " }),
      document.createTextNode(assessment.review_required ? "yes" : "no")
    )
  );
  if (assessment.review_required) {
    container.appendChild(
      el("p", {
        text:
          "A suggested-review flag is not a confirmed incursion, a pest-quarantine " +
          "conclusion, or a biosecurity determination.",
      })
    );
  }
  return container;
}

function renderCandidates(assessment) {
  const tbody = document.querySelector("#candidate-table tbody");
  tbody.innerHTML = "";
  assessment.reranked_candidates.forEach((candidate, index) => {
    const row = el(
      "tr",
      {},
      el("td", { text: String(index + 1) }),
      el("td", { text: candidate.submitted_name }),
      el("td", { text: formatPercent(candidate.visual_probability_raw) }),
      el("td", { text: formatScore(candidate.geo_support) }),
      el("td", { text: formatScore(candidate.rerank_score) }),
      el("td", { text: candidate.ecological_state })
    );
    tbody.appendChild(row);
  });
}

function renderNarrative(narrative) {
  const list = document.getElementById("narrative-list");
  list.innerHTML = "";
  for (const line of narrative) {
    list.appendChild(el("li", { text: line }));
  }
}

function renderEvidence(assessment, warnings) {
  const container = document.getElementById("evidence-content");
  container.innerHTML = "";

  const versions = el("div", {}, el("h3", { text: "Model and configuration versions" }));
  const versionList = el("ul", {});
  for (const [key, value] of Object.entries(assessment.model_versions || {})) {
    versionList.appendChild(el("li", { text: `${key}: ${value}` }));
  }
  versionList.appendChild(
    el("li", { text: `profile_version: ${assessment.profile_version}` })
  );
  versionList.appendChild(
    el("li", { text: `configuration_version: ${assessment.configuration_version}` })
  );
  for (const [key, value] of Object.entries(assessment.data_snapshot_versions || {})) {
    versionList.appendChild(el("li", { text: `${key}: ${value}` }));
  }
  versions.appendChild(versionList);
  container.appendChild(versions);

  if (assessment.missing_evidence && assessment.missing_evidence.length) {
    container.appendChild(el("h3", { text: "Missing evidence" }));
    const missingList = el("ul", {});
    for (const item of assessment.missing_evidence) {
      missingList.appendChild(el("li", { text: item }));
    }
    container.appendChild(missingList);
  }

  if (warnings && warnings.length) {
    container.appendChild(el("h3", { text: "Warnings" }));
    const warningList = el("ul", {});
    for (const item of warnings) {
      warningList.appendChild(el("li", { text: item }));
    }
    container.appendChild(warningList);
  }

  container.appendChild(
    el("h3", { text: `Evidence records referenced: ${(assessment.evidence || []).length}` })
  );

  container.appendChild(el("h3", { text: "Fixed limitations" }));
  const limitationsList = el("ul", {});
  for (const item of FIXED_LIMITATIONS) {
    limitationsList.appendChild(el("li", { text: item }));
  }
  container.appendChild(limitationsList);
}

async function submitForm(event) {
  event.preventDefault();
  const form = document.getElementById("assess-form");
  const runButton = document.getElementById("run-button");
  const loading = document.getElementById("loading");
  const errorBox = document.getElementById("error");
  const results = document.getElementById("results");

  errorBox.hidden = true;
  results.hidden = true;
  loading.hidden = false;
  runButton.disabled = true;

  try {
    const formData = new FormData(form);
    const response = await fetch("/api/assess", { method: "POST", body: formData });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "The request could not be completed.");
    }

    const summaryContainer = document.getElementById("section-summary");
    summaryContainer.innerHTML = "";
    summaryContainer.appendChild(renderSummary(payload.assessment));

    renderCandidates(payload.assessment);
    renderNarrative(payload.narrative);
    renderEvidence(payload.assessment, payload.warnings);

    results.hidden = false;
  } catch (err) {
    errorBox.textContent = err.message || "Something went wrong running the local demo.";
    errorBox.hidden = false;
  } finally {
    loading.hidden = true;
    runButton.disabled = false;
  }
}

document.getElementById("image").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) showPreview(file);
});
document.getElementById("use-sample").addEventListener("click", useSampleImage);
document.getElementById("assess-form").addEventListener("submit", submitForm);
