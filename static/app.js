"use strict";

// Interface and shared helpers
const pages = [...document.querySelectorAll(".page")];
let recommendationRows = [];
const byId = id => document.getElementById(id);
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function list(items) {
  const node = element("ul");
  items.forEach(item => node.append(element("li", item)));
  return node;
}
function sources(items) {
  const node = element("ul", undefined, "sources");
  for (const source of items) {
    const row = element("li");
    const link = element("a", `${new URL(source.url).hostname} · checked ${source.checked_on}`);
    link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    row.append(link, element("p", source.note)); node.append(row);
  }
  return node;
}
function table(headers, rows) {
  const wrap = element("div", undefined, "table-scroll"), node = element("table");
  const head = element("thead"), heading = element("tr");
  headers.forEach(text => { const cell = element("th", text); cell.scope = "col"; heading.append(cell); });
  head.append(heading); node.append(head);
  const body = element("tbody");
  rows.forEach(values => { const row = element("tr"); values.forEach(value => row.append(element("td", typeof value === "number" && !Number.isInteger(value) ? value.toFixed(2) : value ?? "Not recorded / unavailable"))); body.append(row); });
  node.append(body); wrap.append(node); return wrap;
}
function format(value, suffix = "") { return typeof value === "number" ? `${value.toFixed(2)}${suffix}` : "Unknown"; }
async function api(path, options = {}) {
  const {timeoutMs = 30000, ...fetchOptions} = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {...fetchOptions, signal: controller.signal});
    let body;
    try { body = await response.json(); } catch { throw new Error("The server did not return JSON. Check that ReviveOS is running."); }
    if (!response.ok) throw new Error(body.message || "Request failed.");
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("ReviveOS took too long to respond. Refresh to check any operation already started before trying again.");
    throw error;
  } finally { clearTimeout(timer); }
}
const post = (path, value = {}, options = {}) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(value), ...options});
async function action(button, target, work) {
  button.disabled = true; target.textContent = "Working…";
  try { await work(target); }
  catch (error) { target.textContent = `Unable to complete request: ${error.message}`; }
  finally { button.disabled = false; }
}
function navigate() {
  const requested = location.hash.slice(1) || "welcome";
  const id = pages.some(page => page.id === requested) ? requested : "welcome";
  pages.forEach(page => { page.hidden = page.id !== id; });
  document.querySelectorAll("nav a").forEach(link => {
    const active = link.hash === `#${id}`;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
}
window.addEventListener("hashchange", navigate);
navigate();

byId("hardware-check").addEventListener("click", event => {
  byId("hardware-details").replaceChildren();
  action(event.currentTarget, byId("hardware-result"), async target => {
    const {data: h} = await api("/api/hardware");
    target.textContent = `${h.status === "partial" ? "Partial detection — review warnings" : "Detection complete"} · ${new Date(h.collected_at).toLocaleString()}`;
    byId("hardware-details").append(table(["Property", "Detected value"], [
      ["Platform", h.platform], ["CPU", h.cpu], ["Image architecture", h.architecture], ["Physical / logical cores", `${h.physical_cores ?? "?"} / ${h.logical_cores ?? "?"}`],
      ["Rated maximum CPU boost", h.cpu_rated_clocks ? `Up to ${format(h.cpu_rated_clocks.max_boost_mhz / 1000, " GHz")} (${format(h.cpu_rated_clocks.max_boost_mhz, " MHz")}) · manufacturer rating, not measured` : "No reviewed manufacturer specification for this CPU"],
      ["Rated CPU base clock", h.cpu_rated_clocks ? format(h.cpu_rated_clocks.base_mhz / 1000, " GHz") : "Unknown"],
      ["OS-reported CPU clock (may be base)", format(h.cpu_max_mhz, " MHz")], ["Total / available RAM", `${format(h.memory_gb)} / ${format(h.memory_available_gb)} GB`],
      ["TPM", h.tpm?.version ? `TPM ${h.tpm.version} detected` : h.tpm?.message || "Not checked"],
      ["TPM check source", h.tpm?.source || "Unavailable"],
      ["System filesystem", h.storage_path], ["Capacity / free space", `${format(h.storage_gb)} / ${format(h.storage_free_gb)} GB`]
    ]), list(h.warnings));
    if (h.cpu_rated_clocks) byId("hardware-details").append(sources([{url: h.cpu_rated_clocks.source, checked_on: h.cpu_rated_clocks.checked_on, note: h.cpu_rated_clocks.note}]));
  });
});
byId("benchmark-check").addEventListener("click", event => {
  byId("benchmark-details").replaceChildren();
  action(event.currentTarget, byId("benchmark-result"), async target => {
    const {data: report} = await post("/api/benchmarks");
    target.textContent = `${report.status === "partial" ? "Some measurements unavailable" : "Measurements complete"} · ${new Date(report.collected_at).toLocaleString()}`;
    byId("benchmark-details").append(table(["Microbenchmark", "Measured MiB/s", "Status"], Object.entries(report.metrics).map(([name, metric]) => [name, format(metric.value), metric.status])), list(report.warnings));
    recommendationRows = [];
    byId("recommendations-list").replaceChildren();
    byId("recommend-result").textContent = "Measurements updated. Compare operating systems again to use the latest results.";
  });
});

const statusNames = {meets_known_requirements: "Meets known requirements", needs_review: "Needs review", incompatible: "Does not meet requirements"};
function simpleCheckNotes(warnings) {
  return [...new Set(warnings.map(note => {
    if (/graphics, display|wi-fi|firmware and boot/i.test(note)) return "Try this system from a USB first to check that your screen, Wi-Fi and other devices work before installing it.";
    if (/display requirement|resolution|display and GPU/i.test(note)) return "Check that text and pictures fit properly on your screen.";
    if (/microbenchmark|cached file-read|raw disk|cache effects|Python.*runtime/i.test(note)) return "These short tests give a rough guide. Your apps, open programs and files can change how fast the computer feels.";
    if (/system-filesystem free space|installation target|storage is/i.test(note)) return "We still need to check that there is enough space where you want to install the new system.";
    if (/No fresh benchmark/i.test(note)) return "Run the quick computer tests for a more complete comparison.";
    if (/unavailable|could not be read/i.test(note)) return "We couldn't read some information about your computer. Open the details below to see what's missing.";
    if (/below the published/i.test(note)) return "One of your apps may need more powerful hardware to work comfortably. Check its details below.";
    return "This option has some extra requirements to check. You can find them in the details below.";
  }))];
}
function renderRecommendation(row) {
  const card = element("article", undefined, `panel recommendation ${row.status}`);
  card.dataset.categories = (row.categories || []).join(",");
  card.dataset.osId = row.os_id;
  card.append(element("span", statusNames[row.status], "badge"), element("h2", `${row.name} ${row.version} · ${row.desktop}`));
  if (row.categories?.length) card.append(element("p", `Focus: ${row.categories.join(" · ")}`));
  if (row.description) card.append(element("p", row.description));
  if (row.planning_estimates) {
    card.append(element("h3", "Rough planning estimates"),
      element("p", "Our suggested starting budgets, not official requirements or a speed guarantee. Open programs, games and websites can need more. These estimates do not mark an unverified check as passed."),
      table(["System or app", "Suggested RAM", "Suggested free space", "Rough CPU speed"],
        row.planning_estimates.rows.map(item => [item.name, `${item.memory_gb} GB`, `${item.storage_gb} GB`, `About ${item.cpu_mhz / 1000} GHz`])),
      element("p", "RAM and CPU figures are not added together. Allow room for the system and apps running together. Clock speed alone cannot compare different processors; graphics and app support still need checking."));
  }
  card.append(element("p", row.score === null ? "Excluded from selectable choices. Review the exact reasons below." : `Assessed suitability: ${row.score.toFixed(1)} / 100 · Based on ${row.assessed_points.toFixed(2)} of ${row.assessed_maximum} assessed policy points · ${row.benchmark_used ? "Uses recent benchmark measurements" : "No fresh benchmarks used"}`));
  card.append(element("p", `Evidence coverage: ${row.evidence.assessed}/${row.evidence.total} checks assessed (${row.evidence.coverage_percent}%). This is documentation coverage, not confidence or accuracy.`, "evidence-caption"));
  if (row.status !== "incompatible") {
    const label = element("label", undefined, "check");
    const checkbox = element("input"); checkbox.type = "checkbox"; checkbox.name = "keep-choice"; checkbox.value = row.os_id;
    label.append(checkbox, document.createTextNode(` Keep ${row.name} for preparation`)); card.append(label);
  }
  if (row.exclusion_reasons.length) card.append(element("h3", "Why excluded"), list(row.exclusion_reasons));
  if (row.evidence_gaps.length) {
    const gaps = element("details"); gaps.append(element("summary", `Exactly what remains unverified (${row.evidence_gaps.length})`), list(row.evidence_gaps)); card.append(gaps);
  }
  const details = element("details"); details.append(element("summary", "Inspect score, requirements, and application evidence"));
  details.append(table(["Suitability factor", "Assessed points", "Assessed maximum"], Object.entries(row.components).map(([key, value]) => [key, value ?? "Not assessed — omitted", row.component_weights[key]])), element("p", row.explanation), element("h3", "Reasons"), list(row.reasons));
  details.append(table(["Hardware check", "Required", "Detected", "Result"], row.hardware_checks.map(check => [check.field, Array.isArray(check.required) ? check.required.join(", ") : check.required, check.actual, check.status])));
  for (const app of row.applications) {
    details.append(element("h3", app.name), element("p", `Availability: ${app.status} · Resource check: ${app.resource_status} · ${app.implementation ?? "No verified implementation"}`), list(app.notes));
    details.append(table(["Application minimum", "Required", "Detected", "Result / missing evidence"], app.checks.map(check => [check.field, check.required, check.actual, check.unknown_reason || check.status])));
    details.append(table(["Published recommendation", "Recommended", "Detected", "Result"], app.recommended_checks.map(check => [check.field, check.required, check.actual, check.status])));
    details.append(sources([...(app.source ? [app.source] : []), ...app.requirement_sources]));
  }
  details.append(element("h3", "OS sources"), sources(row.sources));
  details.append(element("h3", "Technical notes"), list(row.warnings));
  card.append(element("h3", "Before you choose"), list(simpleCheckNotes(row.warnings)), details);
  return card;
}
byId("recommend-check").addEventListener("click", event => {
  recommendationRows = [];
  byId("recommendations-list").replaceChildren();
  action(event.currentTarget, byId("recommend-result"), async target => {
    const {data} = await post("/api/recommend");
    const rows = data.recommendations;
    recommendationRows = rows;
    const groupTarget = byId("recommendations-list");
    byId("shortlist-panel").hidden = !rows.some(row => row.status !== "incompatible");
    byId("shortlist-result").textContent = "";
    byId("review-ack").checked = false;
    applyCategoryFilter();
    if (!rows.some(row => row.family === "Windows") && (data.preferences.os_preference === "windows" || (data.preferences.os_preference === "familiar" && data.hardware.platform === "Windows"))) {
      groupTarget.prepend(element("p", "No Windows image is evaluated in this catalog. Your Windows preference is respected; use Microsoft’s official checks linked in User Preferences. Linux choices are not substituted."));
    }
  });
});
function applyCategoryFilter() {
  const category = byId("os-category").value;
  const matching = recommendationRows.filter(row => row.status !== "incompatible" && (category === "all" || (row.categories || []).includes(category)));
  const top = matching.slice(0, 3);
  byId("recommendations-list").replaceChildren(...top.map(renderRecommendation));
  byId("shortlist-panel").hidden = !top.length;
  if (recommendationRows.length) {
    byId("recommend-result").textContent = top.length ? `Your top ${top.length} choices. Known incompatibilities are left out; any checks still needed are shown on each choice.` : "No suitable choices found for these preferences and checks. Try another focus or review your required apps.";
  }
  byId("os-filter-result").textContent = recommendationRows.length ? `Showing ${top.length} top choices for this focus.` : "";
}
byId("os-category").addEventListener("change", applyCategoryFilter);
byId("health-check").addEventListener("click", event => action(event.currentTarget, byId("health-result"), async target => {
  const result = await api("/api/health"); target.textContent = `Connected · ${result.data.stage} · ${result.data.algorithm}`;
}));
byId("preferences-form").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget, values = new FormData(form);
  const data = {applications: values.getAll("applications"), usage: values.get("usage"), experience: values.get("experience"), os_preference: values.get("os_preference"), essential_notes: values.get("essential_notes")};
  action(form.querySelector("button"), byId("preferences-result"), async target => {
    const result = await post("/api/preferences", data); target.textContent = result.message;
    recommendationRows = [];
    byId("recommendations-list").replaceChildren();
    byId("recommend-result").textContent = "Preferences updated. Compare operating systems to see updated results.";
    byId("shortlist-panel").hidden = true;
    window.dispatchEvent(new Event("reviveos:preferences"));
  });
});


// Guided preparation
let backupPlanId = null;
let preparation = null;
let downloadBusy = false;
const polling = new Set();

function externalLink(label, url) {
  const link = element("a", label); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; return link;
}
function invalidateBackupPreview() {
  backupPlanId = null; byId("backup-start").disabled = true; byId("backup-consent").checked = false;
  byId("backup-preview").replaceChildren();
}
async function loadPreparation() {
  const osId = byId("install-os").value;
  preparation = null; byId("preparation-details").replaceChildren(); byId("download-instructions").replaceChildren();
  if (!osId) { byId("preparation-result").textContent = "Keep one or two OS choices in Recommendations first."; return; }
  try {
    const {data} = await api(`/api/installation/${encodeURIComponent(osId)}`);
    preparation = data;
    byId("preparation-result").textContent = `Preparing ${data.assessment.name}. This is preparation only; no installation has started.`;
    byId("preparation-details").append(list(data.checklist), list(data.warnings));
    byId("download-instructions").append(externalLink("Official image download", data.download), document.createTextNode(" · "), externalLink("Verify publisher signature", data.verify), document.createTextNode(" · "), externalLink("Official installation guide", data.install));
    byId("preparation-details").append(externalLink("Rufus — manual USB creation on Windows", "https://rufus.ie/en/"));
    if (!data.automatic_download) {
      const official = externalLink(`Get ${data.assessment.name} from its official website ↗`, data.download);
      official.className = "button";
      byId("download-instructions").append(element("p", "For this system, get the installer from its official website. ReviveOS will not download or check the file for you."), official);
      byId("download-method").value = "manual";
      byId("download-controls").hidden = true;
    }
    byId("download-method").querySelector('option[value="real"]').disabled = !data.automatic_download;
    updateDownloadControls();
    byId("backup-confirm-result").textContent = data.backup_confirmation ? "Backup inspection confirmation is recorded for this session." : "Complete and confirm the backup checkpoint before a download or handoff.";
  } catch (error) { byId("preparation-result").textContent = error.message; }
}
async function loadWorkflow() {
  try {
    const {data} = await api("/api/workflow");
    byId("environment-result").textContent = `${data.environment.running_os} host${data.environment.live_environment ? " · live environment detected" : ""}. ${data.environment.message}`;
    if (data.entry_branch) byId("entry-form").elements.existing_os.value = data.entry_branch;
    const previous = byId("install-os").value;
    byId("install-os").replaceChildren();
    if (!data.shortlist.length) {
      const option = element("option", "Keep an OS in Recommendations first"); option.value = ""; byId("install-os").append(option);
    } else {
      const {data: catalog} = await api("/api/operating-systems");
      data.shortlist.forEach(id => { const option = element("option", catalog.find(row => row.id === id)?.name || id); option.value = id; byId("install-os").append(option); });
      if (data.shortlist.includes(previous)) byId("install-os").value = previous;
    }
    await loadPreparation();
    if (data.backup_task) pollTask(data.backup_task, "backup");
    if (data.download_task) pollTask(data.download_task, "download");
  } catch (error) { byId("environment-result").textContent = `Could not read workflow: ${error.message}`; }
}
async function pollTask(id, kind) {
  if (polling.has(id)) return;
  polling.add(id);
  if (kind === "download") { downloadBusy = true; byId("download-start").disabled = true; }
  const status = byId(kind === "model" ? "ai-setup-result" : kind === "backup" ? "backup-task-result" : "download-result");
  const details = byId(kind === "backup" ? "backup-task-details" : "download-details");
  try {
    while (true) {
      const {data} = await api(`/api/tasks/${encodeURIComponent(id)}`);
      if (data.status === "failed") { status.textContent = `Operation failed: ${data.error}`; break; }
      if (data.status === "complete") {
        if (kind === "model") { status.textContent = "Local model prepared. No paid API is needed."; break; }
        status.textContent = kind === "backup" ? "Backup copy completed and file hashes matched. Inspect the copied files before confirming below." : "Download finished; SHA-256 matches. Publisher-signature authentication is still pending.";
        details.replaceChildren();
        const result = data.result;
        if (kind === "backup") {
          details.append(element("p", `New backup folder: ${result.folder}`), element("p", `${result.file_count} files · ${format(result.bytes_copied / 1e6)} MB · ${result.verification}`), list(result.warnings));
          byId("backup-method").value = "reviveos";
        } else {
          details.append(element("p", `Downloaded file: ${result.path}`), element("p", result.message), element("p", `SHA-256: ${result.sha256}`), externalLink("Complete signature verification", result.verification_guide));
        }
        break;
      }
      const progress = data.progress;
      status.textContent = kind === "model" ? `${progress.status || data.status}${progress.completed ? ` · ${format(progress.completed / 1e6)} MB${progress.total ? ` / ${format(progress.total / 1e6)} MB` : ""}` : ""}` : kind === "backup" ? `${data.status}: ${progress.files_copied ?? 0}/${progress.total_files ?? "?"} files copied.` : `${progress.message || (progress.bytes_downloaded > 0 ? "Downloading the installer…" : "Connecting to the official download site…")}${progress.bytes_downloaded != null ? ` · ${format(progress.bytes_downloaded / 1e6)} MB${progress.total_bytes ? ` of ${format(progress.total_bytes / 1e6)} MB` : ""}` : ""} · Last checked ${new Date().toLocaleTimeString()}`;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  } catch (error) { status.textContent = `Could not read operation status: ${error.message}. Refresh to reconnect; do not assume success.`; }
  finally { polling.delete(id); if (kind === "download") { downloadBusy = false; updateDownloadControls(); } }
}

byId("entry-form").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget;
  action(form.querySelector("button"), byId("entry-result"), async target => {
    const {data} = await post("/api/workflow/start", {existing_os: form.elements.existing_os.value});
    target.textContent = data.guidance;
    if (data.branch === "yes") location.hash = "preferences";
  });
});
byId("shortlist-save").addEventListener("click", event => action(event.currentTarget, byId("shortlist-result"), async target => {
  const osIds = [...document.querySelectorAll('input[name="keep-choice"]:checked')].map(input => input.value);
  const result = await post("/api/shortlist", {os_ids: osIds, acknowledge_review: byId("review-ack").checked});
  target.textContent = result.message; await loadWorkflow();
}));
byId("install-os").addEventListener("change", loadPreparation);
window.addEventListener("reviveos:preferences", loadWorkflow);

for (const button of document.querySelectorAll("[data-picker]")) {
  button.addEventListener("click", event => action(event.currentTarget, byId("backup-result"), async target => {
    const {data} = await post("/api/paths/pick", {kind: button.dataset.picker}, {timeoutMs: 125000});
    const input = byId(button.dataset.target);
    if (data.paths.length) {
      input.value = input.tagName === "TEXTAREA" ? [input.value.trim(), ...data.paths].filter(Boolean).join("\n") : data.paths[0];
      input.dispatchEvent(new Event("input"));
    }
    target.textContent = data.paths.length ? "Selection recorded. Preview before copying." : "No path selected.";
  }));
}
for (const id of ["backup-sources", "backup-destination"]) byId(id).addEventListener("input", invalidateBackupPreview);
byId("destination-drive").addEventListener("change", () => { byId("backup-destination").value = byId("destination-drive").value; invalidateBackupPreview(); });
byId("backup-preview-form").addEventListener("submit", event => {
  event.preventDefault(); invalidateBackupPreview();
  action(event.currentTarget.querySelector('button:not([type="button"])'), byId("backup-result"), async target => {
    const sources = byId("backup-sources").value.split("\n").map(value => value.trim()).filter(Boolean);
    const {data, message} = await post("/api/backup/preview", {sources, destination: byId("backup-destination").value.trim()});
    backupPlanId = data.plan_id; target.textContent = message;
    byId("backup-preview").append(element("p", `${data.file_count} files · ${format(data.total_bytes / 1e6)} MB → ${data.destination}`), list(data.sources), list(data.warnings));
    byId("backup-start").disabled = false;
  });
});
byId("backup-start").addEventListener("click", event => action(event.currentTarget, byId("backup-task-result"), async target => {
  const {data, message} = await post("/api/backup/start", {plan_id: backupPlanId, consent: byId("backup-consent").checked});
  backupPlanId = null; byId("backup-consent").checked = false; target.textContent = message; pollTask(data.task_id, "backup");
}));
byId("backup-confirm-form").addEventListener("submit", event => {
  event.preventDefault();
  action(event.currentTarget.querySelector("button"), byId("backup-confirm-result"), async target => {
    const result = await post("/api/backup/confirm", {method: byId("backup-method").value, confirmed: byId("backup-inspected").checked}); target.textContent = result.message;
  });
});
function updateDownloadControls() {
  const method = byId("download-method").value;
  const real = method === "real";
  byId("download-controls").hidden = method === "manual";
  byId("download-start").disabled = downloadBusy || (real && !preparation?.automatic_download);
  byId("download-start").textContent = real ? "Download and check SHA-256" : "Preview download steps";
  byId("download-mode-note").textContent = real ? "A real installer will be downloaded after your backup confirmation and explicit permission. A checksum check is not publisher-signature authentication." : "Demo only. No installer will be downloaded or verified.";
  byId("download-consent-text").textContent = real ? "I permit this selected installer download (up to 8 GiB) into a new folder after my backup confirmation." : "I understand this is a demo: no installer will be downloaded or verified.";
}
byId("download-method").addEventListener("change", () => { byId("download-consent").checked = false; updateDownloadControls(); });
byId("download-start").addEventListener("click", event => action(event.currentTarget, byId("download-result"), async target => {
  const real = byId("download-method").value === "real";
  target.textContent = real ? "Requesting your installer download…" : "Showing demo steps… No files are being downloaded.";
  const {data, message} = await post(real ? "/api/downloads/start" : "/api/downloads/demo", {os_id: byId("install-os").value, destination: byId("download-destination").value.trim(), consent: byId("download-consent").checked});
  byId("download-consent").checked = false; target.textContent = message;
  if (real) await pollTask(data.task_id, "download");
  else byId("download-details").replaceChildren(list(data.steps));
}));
byId("handoff-form").addEventListener("submit", event => {
  event.preventDefault();
  action(event.currentTarget.querySelector("button"), byId("handoff-result"), async target => {
    const {data} = await post("/api/installation/handoff", {os_id: byId("install-os").value, method: byId("usb-method").value, device_label: byId("usb-device").value.trim(),
      signature_verified: byId("signature-verified").checked, media_verified: byId("media-verified").checked, usb_erasure_ack: byId("usb-erasure-ack").checked,
      separate_usb_confirmed: byId("separate-usb").checked, recovery_ack: byId("recovery-ack").checked});
    target.textContent = data.message; byId("handoff-details").replaceChildren(list(data.instructions));
  });
});
async function loadDestinations() {
  try {
    const {data} = await api("/api/destinations");
    data.forEach(row => { const option = element("option", `${row.mountpoint} · ${row.device} · ${row.filesystem} (verify drive identity)`); option.value = row.mountpoint; byId("destination-drive").append(option); });
  } catch (error) { byId("backup-result").textContent = `Drive list unavailable; enter an existing path manually. ${error.message}`; }
}
loadWorkflow();
loadDestinations();


// Local AI
let aiDraft = null;

async function refreshLocalAI() {
  try {
    const {data} = await api("/api/ai/status");
    const model = data.models.find(row => row.id === byId("ai-model").value);
    byId("ai-status").textContent = !data.available ? data.message : model?.installed ? `${model.name} is installed locally. Ready to answer on this device.` : "Local engine connected. The selected model has not been downloaded into its model store.";
    if (data.task_id && !polling.has(data.task_id)) pollTask(data.task_id, "model");
  } catch (error) { byId("ai-status").textContent = `Local AI unavailable: ${error.message}`; }
}
byId("ai-status-check").addEventListener("click", refreshLocalAI);
byId("ai-model").addEventListener("change", refreshLocalAI);
byId("ai-setup").addEventListener("click", event => action(event.currentTarget, byId("ai-setup-result"), async target => {
  const {data, message} = await post("/api/ai/setup", {model: byId("ai-model").value, consent: byId("ai-download-consent").checked});
  byId("ai-download-consent").checked = false; target.textContent = message; pollTask(data.task_id, "model");
}));
byId("ai-chat-form").addEventListener("submit", event => {
  event.preventDefault(); aiDraft = null; byId("ai-apply-draft").hidden = true;
  const question = byId("ai-question").value.trim();
  action(event.currentTarget.querySelector("button"), byId("ai-chat-result"), async target => {
    target.textContent = "Thinking locally… This may take a while on an older CPU. No compatibility decisions are being changed.";
    const {data} = await post("/api/ai/chat", {question, model: byId("ai-model").value}, {timeoutMs: 150000});
    const exchange = element("article", undefined, "chat-exchange");
    exchange.append(element("h3", "You"), element("p", question), element("h3", "Local assistant · draft explanation"), element("p", data.explanation));
    byId("ai-conversation").append(exchange);
    while (byId("ai-conversation").children.length > 6) byId("ai-conversation").firstElementChild.remove();
    aiDraft = data.suggested_preferences;
    byId("ai-apply-draft").hidden = !Object.keys(aiDraft).length;
    target.textContent = data.message;
  });
});
byId("ai-apply-draft").addEventListener("click", () => {
  if (!aiDraft) return;
  const form = byId("preferences-form");
  for (const [key, value] of Object.entries(aiDraft)) {
    if (key === "applications") form.querySelectorAll('input[name="applications"]').forEach(input => { input.checked = value.includes(input.value); });
    else if (form.elements[key]) form.elements[key].value = value;
  }
  byId("preferences-result").textContent = "AI suggestions filled in as a draft. Review them and click Save preferences to apply.";
  location.hash = "preferences";
});
refreshLocalAI();
