const sampleSelect = document.querySelector("#sample-select");
const sourceText = document.querySelector("#source-text");
const charCount = document.querySelector("#char-count");
const runButton = document.querySelector("#run-button");
const errorMessage = document.querySelector("#error-message");
const emptyState = document.querySelector("#empty-state");
const reportContent = document.querySelector("#report-content");
const claimList = document.querySelector("#claim-list");
const verdictNames = ["supported", "partially_supported", "overstated", "unsupported"];
let currentReport = null;

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

function updateCharacterCount() {
  const count = sourceText.value.length;
  charCount.textContent = `${count.toLocaleString()} character${count === 1 ? "" : "s"}`;
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = !message;
}

async function loadSamples() {
  try {
    const response = await fetch("/api/samples");
    if (!response.ok) throw new Error("Could not load samples");
    const samples = await response.json();
    for (const name of samples) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      sampleSelect.append(option);
    }
    if (samples.length) {
      sampleSelect.value = samples[0];
      await loadSelectedSample();
    }
  } catch (error) {
    showError(error.message);
  }
}

async function loadSelectedSample() {
  const name = sampleSelect.value;
  if (!name) return;
  showError("");
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(name)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load sample");
    sourceText.value = data.text;
    updateCharacterCount();
  } catch (error) {
    showError(error.message);
  }
}

function renderCounts(audits) {
  const counts = Object.fromEntries(verdictNames.map((name) => [name, 0]));
  for (const audit of audits) counts[audit.verdict] = (counts[audit.verdict] || 0) + 1;
  const labels = {
    supported: "Supported",
    partially_supported: "Partially supported",
    overstated: "Overstated",
    unsupported: "Unsupported",
  };
  document.querySelector("#verdict-counts").innerHTML = verdictNames.map((name) => `
    <div class="count-cell count-${name}">
      <strong>${counts[name] || 0}</strong><span>${labels[name]}</span>
    </div>`).join("");
}

function renderClaims(audits) {
  claimList.innerHTML = audits.map((audit, index) => {
    const claim = audit.claim || {};
    const details = [];
    if (audit.evidence_quote) {
      details.push(`<p><span class="detail-label">Evidence quote</span><span class="evidence-quote">“${escapeHtml(audit.evidence_quote)}”</span></p>`);
    }
    if (audit.rationale) details.push(`<p><span class="detail-label">Reasoning</span>${escapeHtml(audit.rationale)}</p>`);
    if (audit.issues?.length) {
      details.push(`<p><span class="detail-label">Issues</span><span class="issue-tags">${audit.issues.map((issue) => `<span class="issue-tag">${escapeHtml(issue.replaceAll("_", " "))}</span>`).join("")}</span></p>`);
    }
    if (audit.rewrite) details.push(`<p><span class="detail-label">More defensible wording</span>${escapeHtml(audit.rewrite)}</p>`);
    if (audit.error) details.push(`<p><span class="detail-label">Audit error</span>${escapeHtml(audit.error)}</p>`);
    return `
      <details class="claim-item" data-verdict="${escapeHtml(audit.verdict)}" ${index === 0 ? "open" : ""}>
        <summary>
          <span class="claim-number">${String(claim.id ?? index + 1).padStart(2, "0")}</span>
          <span class="claim-text">${escapeHtml(claim.text)}</span>
          <span class="claim-kind">${escapeHtml(claim.type)}</span>
          <span class="claim-chevron" aria-hidden="true">⌄</span>
        </summary>
        <div class="claim-details">${details.join("")}</div>
      </details>`;
  }).join("");
}

function showReport(report) {
  currentReport = report;
  emptyState.hidden = true;
  reportContent.hidden = false;
  document.querySelector("#download-actions").hidden = false;
  document.querySelector("#report-caption").textContent = "Evidence review complete.";
  document.querySelector("#score-value").textContent = Number(report.score).toFixed(1);
  document.querySelector("#summary-text").textContent = report.summary || "No summary was returned.";
  document.querySelector("#claim-total").textContent = `${report.audits.length} claim${report.audits.length === 1 ? "" : "s"}`;
  document.querySelector("#usage-note").textContent = `${report.usage.calls} API calls · ${report.usage.cache_hits} cached · ${report.usage.input_tokens}/${report.usage.output_tokens} tokens in/out`;
  renderCounts(report.audits);
  renderClaims(report.audits);
}

async function runAudit() {
  showError("");
  if (!sourceText.value.trim()) {
    showError("Paste or load a document before running the audit.");
    sourceText.focus();
    return;
  }
  runButton.disabled = true;
  runButton.querySelector(".button-label").textContent = "Reviewing claims…";
  document.querySelector("#report-caption").textContent = "The audit may take a little while.";
  try {
    const response = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sourceText.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Audit failed");
    showReport(data);
  } catch (error) {
    document.querySelector("#report-caption").textContent = "Run an audit to see claim-level findings.";
    showError(error.message || "The audit could not be completed.");
  } finally {
    runButton.disabled = false;
    runButton.querySelector(".button-label").textContent = "Run audit";
  }
}

function downloadFile(contents, filename, type) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

sampleSelect.addEventListener("change", loadSelectedSample);
sourceText.addEventListener("input", updateCharacterCount);
runButton.addEventListener("click", runAudit);
document.querySelector("#download-md").addEventListener("click", () => {
  if (currentReport) downloadFile(currentReport.markdown, "claim-audit.md", "text/markdown");
});
document.querySelector("#download-json").addEventListener("click", () => {
  if (currentReport) downloadFile(JSON.stringify(currentReport, null, 2), "claim-audit.json", "application/json");
});

updateCharacterCount();
loadSamples();