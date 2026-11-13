/* --- STATE MANAGEMENT --- */
let currentFrom = "2026-10-01";
let currentTo = "2026-10-31";
let activeReportData = null; // cached report JSON

// Selected filters
let selectedSiteId = "";
let selectedResponderId = "";
let selectedWithinTarget = "";
let selectedLate = "";
let selectedSort = "id";
let selectedLimit = 50;

// Pagination state (Level 4 cursor stack)
let cursorStack = [null]; // cursorStack[0] is initial page
let pageIndex = 0;
let nextCursor = null;

// Responders table sorting
let responderSortKey = "requests";
let responderSortAsc = false;

// Controllers for request cancellation
let reportAbortController = null;
let browseAbortController = null;

// Background auto-refresh timer
let autoRefreshInterval = null;

/* --- INITIALIZATION & READINESS CHECK --- */
window.addEventListener("DOMContentLoaded", () => {
  pollReadyStatus();
});

async function pollReadyStatus() {
  try {
    const res = await fetch("/ready");
    if (res.ok) {
      const body = await res.json();
      if (body.ready) {
        document.getElementById("sync-overlay").style.display = "none";
        document.getElementById("app").style.display = "block";
        initApp();
        return;
      }
    }
  } catch (_) {}
  setTimeout(pollReadyStatus, 2000);
}

function initApp() {
  setupAutoRefresh();
  loadDashboard(currentFrom, currentTo);
}

function setupAutoRefresh() {
  const toggle = document.getElementById("auto-refresh-toggle");
  toggle.addEventListener("change", () => {
    if (toggle.checked) {
      startAutoRefresh();
    } else {
      stopAutoRefresh();
    }
  });
  startAutoRefresh();
}

function startAutoRefresh() {
  stopAutoRefresh();
  autoRefreshInterval = setInterval(() => {
    silentBackgroundRefresh();
  }, 20000);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
  }
}

/* --- DATE RANGE & PRESETS --- */
function handleDateFormSubmit(e) {
  e.preventDefault();
  const fromVal = document.getElementById("input-from").value;
  const toVal = document.getElementById("input-to").value;

  if (fromVal > toVal) {
    alert("From date cannot be after To date.");
    return;
  }

  document.querySelectorAll(".pill-btn").forEach(p => p.classList.remove("active"));
  currentFrom = fromVal;
  currentTo = toVal;
  resetPagination();
  loadDashboard(currentFrom, currentTo);
}

function applyPreset(preset) {
  document.querySelectorAll(".pill-btn").forEach(p => p.classList.remove("active"));
  event.target.classList.add("active");

  if (preset === "7d") {
    currentFrom = "2026-10-25";
    currentTo = "2026-10-31";
  } else if (preset === "30d") {
    currentFrom = "2026-10-01";
    currentTo = "2026-10-31";
  } else if (preset === "6m") {
    currentFrom = "2026-05-01";
    currentTo = "2026-10-31";
  }

  document.getElementById("input-from").value = currentFrom;
  document.getElementById("input-to").value = currentTo;
  resetPagination();
  loadDashboard(currentFrom, currentTo);
}

/* --- DATA FETCHING --- */
async function loadDashboard(from, to) {
  if (reportAbortController) reportAbortController.abort();
  reportAbortController = new AbortController();

  setSyncStatus("Loading...");

  try {
    const res = await fetch(`/api/sla-report?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`, {
      signal: reportAbortController.signal
    });
    const data = await res.json();

    if (!res.ok) {
      setSyncStatus("Error loading report", true);
      alert(data.error || "Failed to load SLA report");
      return;
    }

    activeReportData = data;
    renderSiteSummaryCards(data.requests);
    populateDropdownFilters(data.requests, data.responders);
    renderRespondersTable(data.responders);
    setSyncStatus(`Live • Synced ${new Date().toLocaleTimeString()}`);

    // Load first page of requests table
    loadRequestsPage();
  } catch (err) {
    if (err.name === "AbortError") return;
    setSyncStatus("Network error", true);
  }
}

async function silentBackgroundRefresh() {
  try {
    const res = await fetch(`/api/sla-report?from=${encodeURIComponent(currentFrom)}&to=${encodeURIComponent(currentTo)}`);
    if (!res.ok) return;
    const data = await res.json();

    const oldCount = activeReportData ? activeReportData.requests.length : 0;
    const newCount = data.requests.length;

    activeReportData = data;
    renderSiteSummaryCards(data.requests);
    renderRespondersTable(data.responders);
    setSyncStatus(`Live • Synced ${new Date().toLocaleTimeString()}`);

    if (newCount !== oldCount) {
      document.getElementById("update-banner").style.display = "flex";
    }
  } catch (_) {}
}

function triggerManualRefresh() {
  loadDashboard(currentFrom, currentTo);
}

function refreshRequestsTable() {
  document.getElementById("update-banner").style.display = "none";
  resetPagination();
  loadRequestsPage();
}

function setSyncStatus(text, isError = false) {
  document.getElementById("sync-time-label").textContent = text;
  document.getElementById("live-indicator").style.background = isError ? "var(--danger)" : "var(--success)";
}

const SITE_NAMES = {
  11: "Singapore",
  12: "Sydney",
  13: "Jakarta"
};

/* --- SECTION B: SITE SUMMARY CARDS (Single O(N) grouping) --- */
function renderSiteSummaryCards(requests) {
  const container = document.getElementById("sites-grid");
  container.innerHTML = "";

  // Group in a single O(N) pass
  const siteStats = {};
  const overall = {
    total: 0,
    respSum: 0,
    respCount: 0,
    withinTargetCount: 0,
    withinTargetDenom: 0,
    lateCount: 0,
    lateDenom: 0
  };

  for (let i = 0; i < requests.length; i++) {
    const r = requests[i];
    const sId = r.site_id;

    if (!siteStats[sId]) {
      siteStats[sId] = {
        site_id: sId,
        total: 0,
        respSum: 0,
        respCount: 0,
        withinTargetCount: 0,
        withinTargetDenom: 0,
        lateCount: 0,
        lateDenom: 0
      };
    }

    const st = siteStats[sId];
    st.total++;
    overall.total++;

    if (r.response_business_minutes !== null) {
      st.respSum += r.response_business_minutes;
      st.respCount++;
      overall.respSum += r.response_business_minutes;
      overall.respCount++;
    }

    if (r.within_target !== null) {
      st.withinTargetDenom++;
      overall.withinTargetDenom++;
      if (r.within_target === true) {
        st.withinTargetCount++;
        overall.withinTargetCount++;
      }
    }

    if (r.completed_late !== null) {
      st.lateDenom++;
      overall.lateDenom++;
      if (r.completed_late === true) {
        st.lateCount++;
        overall.lateCount++;
      }
    }
  }

  // Render "All Sites" card
  const allCard = createSiteCardEl("All Sites", "", overall, selectedSiteId === "");
  container.appendChild(allCard);

  // Render sorted individual site cards
  const sortedSiteIds = Object.keys(siteStats).map(Number).sort((a, b) => a - b);
  sortedSiteIds.forEach(sId => {
    const siteLabel = SITE_NAMES[sId] ? `Site #${sId} (${SITE_NAMES[sId]})` : `Site #${sId}`;
    const card = createSiteCardEl(siteLabel, String(sId), siteStats[sId], selectedSiteId === String(sId));
    container.appendChild(card);
  });
}

function createSiteCardEl(title, siteIdStr, st, isActive) {
  const card = document.createElement("div");
  card.className = "site-card" + (isActive ? " active" : "");
  card.onclick = () => onSiteCardClick(siteIdStr);

  const avgMins = st.respCount > 0 ? Math.round(st.respSum / st.respCount) : null;
  const avgFormatted = formatDuration(avgMins);

  const targetPct = st.withinTargetDenom > 0
    ? ((st.withinTargetCount / st.withinTargetDenom) * 100).toFixed(1) + "%"
    : "—";

  const latePct = st.lateDenom > 0
    ? ((st.lateCount / st.lateDenom) * 100).toFixed(1) + "%"
    : "—";

  card.innerHTML = `
    <div class="site-card-header">
      <span class="site-card-title">${title}</span>
      <span class="site-card-active-tag">Active Filter</span>
    </div>
    <div class="metrics-grid">
      <div class="metric-item">
        <span class="metric-label">Total Requests</span>
        <span class="metric-value num">${st.total}</span>
      </div>
      <div class="metric-item">
        <span class="metric-label">Avg Response</span>
        <span class="metric-value num">${avgFormatted}</span>
      </div>
      <div class="metric-item">
        <span class="metric-label">Within Target</span>
        <span class="metric-value num">${targetPct}<span class="metric-fraction">(${st.withinTargetCount}/${st.withinTargetDenom})</span></span>
      </div>
      <div class="metric-item">
        <span class="metric-label">Finished Late</span>
        <span class="metric-value num">${latePct}<span class="metric-fraction">(${st.lateCount}/${st.lateDenom})</span></span>
      </div>
    </div>
  `;
  return card;
}

function onSiteCardClick(siteIdStr) {
  if (selectedSiteId === siteIdStr) {
    selectedSiteId = "";
  } else {
    selectedSiteId = siteIdStr;
  }
  document.getElementById("filter-site").value = selectedSiteId;
  updateClearFiltersButton();
  renderSiteSummaryCards(activeReportData.requests);
  resetPagination();
  loadRequestsPage();
}

/* --- SECTION C: RESPONDER SUMMARY TABLE --- */
function renderRespondersTable(responders) {
  const tbody = document.getElementById("responders-tbody");
  tbody.innerHTML = "";

  if (!responders || responders.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="inline-msg">No responder data available.</td></tr>';
    return;
  }

  const sorted = [...responders].sort((a, b) => {
    let vA = a[responderSortKey];
    let vB = b[responderSortKey];
    if (typeof vA === "string") return responderSortAsc ? vA.localeCompare(vB) : vB.localeCompare(vA);
    return responderSortAsc ? vA - vB : vB - vA;
  });

  sorted.forEach(r => {
    const tr = document.createElement("tr");
    tr.className = "interactive-row" + (selectedResponderId === String(r.id) ? " active-row" : "");
    tr.onclick = () => onResponderRowClick(String(r.id));

    const targetPct = r.requests > 0 ? ((r.within_target / r.requests) * 100).toFixed(1) : "0.0";
    const latePct = r.requests > 0 ? ((r.completed_late / r.requests) * 100).toFixed(1) : "0.0";

    tr.innerHTML = `
      <td><strong>${escapeHtml(r.name)}</strong> <span style="color: var(--text-muted); font-size: 11px;">#${r.id}</span></td>
      <td class="num">${r.requests}</td>
      <td class="num">${r.within_target} <span style="color: var(--text-muted); font-size: 12px;">(${targetPct}%)</span></td>
      <td class="num">${r.completed_late} <span style="color: var(--text-muted); font-size: 12px;">(${latePct}%)</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function sortResponders(key) {
  if (responderSortKey === key) {
    responderSortAsc = !responderSortAsc;
  } else {
    responderSortKey = key;
    responderSortAsc = (key === "name");
  }
  renderRespondersTable(activeReportData ? activeReportData.responders : []);
}

function onResponderRowClick(respIdStr) {
  if (selectedResponderId === respIdStr) {
    selectedResponderId = "";
  } else {
    selectedResponderId = respIdStr;
  }
  document.getElementById("filter-responder").value = selectedResponderId;
  updateClearFiltersButton();
  renderRespondersTable(activeReportData ? activeReportData.responders : []);
  resetPagination();
  loadRequestsPage();
}

/* --- SECTION D: REQUESTS BROWSE TABLE (Level 4 API) --- */
function populateDropdownFilters(requests, responders) {
  // Populate Sites
  const siteSelect = document.getElementById("filter-site");
  const existingSiteVal = siteSelect.value;
  siteSelect.innerHTML = '<option value="">All Sites</option>';

  const distinctSites = [...new Set(requests.map(r => r.site_id))].sort((a, b) => a - b);
  distinctSites.forEach(sId => {
    const opt = document.createElement("option");
    opt.value = sId;
    opt.textContent = `Site #${sId}`;
    siteSelect.appendChild(opt);
  });
  siteSelect.value = existingSiteVal;

  // Populate Responders
  const respSelect = document.getElementById("filter-responder");
  const existingRespVal = respSelect.value;
  respSelect.innerHTML = '<option value="">All Responders</option>';

  const sortedResps = [...responders].sort((a, b) => a.name.localeCompare(b.name));
  sortedResps.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = `${r.name} (#${r.id})`;
    respSelect.appendChild(opt);
  });
  respSelect.value = existingRespVal;
}

function onFilterChange() {
  selectedSiteId = document.getElementById("filter-site").value;
  selectedResponderId = document.getElementById("filter-responder").value;
  selectedWithinTarget = document.getElementById("filter-target").value;
  selectedLate = document.getElementById("filter-late").value;
  selectedSort = document.getElementById("filter-sort").value;
  selectedLimit = parseInt(document.getElementById("filter-limit").value, 10);

  updateClearFiltersButton();
  if (activeReportData) {
    renderSiteSummaryCards(activeReportData.requests);
    renderRespondersTable(activeReportData.responders);
  }

  resetPagination();
  loadRequestsPage();
}

function updateClearFiltersButton() {
  const hasFilter = selectedSiteId !== "" || selectedResponderId !== "" || selectedWithinTarget !== "" || selectedLate !== "";
  document.getElementById("btn-clear-filters").style.display = hasFilter ? "inline-block" : "none";
}

function clearAllFilters() {
  selectedSiteId = "";
  selectedResponderId = "";
  selectedWithinTarget = "";
  selectedLate = "";
  document.getElementById("filter-site").value = "";
  document.getElementById("filter-responder").value = "";
  document.getElementById("filter-target").value = "";
  document.getElementById("filter-late").value = "";

  updateClearFiltersButton();
  if (activeReportData) {
    renderSiteSummaryCards(activeReportData.requests);
    renderRespondersTable(activeReportData.responders);
  }

  resetPagination();
  loadRequestsPage();
}

function resetPagination() {
  cursorStack = [null];
  pageIndex = 0;
  nextCursor = null;
}

function getFilteredRequestsCount() {
  if (!activeReportData || !activeReportData.requests) return 0;
  let count = 0;
  const reqs = activeReportData.requests;
  for (let i = 0; i < reqs.length; i++) {
    const r = reqs[i];
    if (selectedSiteId && String(r.site_id) !== selectedSiteId) continue;
    if (selectedResponderId && String(r.responder_id) !== selectedResponderId) continue;
    if (selectedWithinTarget !== "") {
      const targetBool = selectedWithinTarget === "true";
      if (r.within_target !== targetBool) continue;
    }
    if (selectedLate !== "") {
      const lateBool = selectedLate === "true";
      if (r.completed_late !== lateBool) continue;
    }
    count++;
  }
  return count;
}

async function loadRequestsPage() {
  if (browseAbortController) browseAbortController.abort();
  browseAbortController = new AbortController();

  const tbody = document.getElementById("requests-tbody");
  if (tbody.children.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="inline-msg">Loading requests...</td></tr>';
  } else {
    tbody.classList.add("is-loading");
  }

  const params = new URLSearchParams({
    from: currentFrom,
    to: currentTo,
    sort: selectedSort,
    limit: selectedLimit
  });

  if (selectedSiteId) params.append("site_id", selectedSiteId);
  if (selectedResponderId) params.append("responder_id", selectedResponderId);
  if (selectedWithinTarget) params.append("within_target", selectedWithinTarget);
  if (selectedLate) params.append("late", selectedLate);

  const cursor = cursorStack[pageIndex];
  if (cursor) params.append("cursor", cursor);

  try {
    const res = await fetch(`/api/requests?${params.toString()}`, {
      signal: browseAbortController.signal
    });
    const body = await res.json();

    tbody.classList.remove("is-loading");

    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="6" class="inline-msg error">${escapeHtml(body.error || "Failed to load requests")}</td></tr>`;
      return;
    }

    nextCursor = body.next_cursor;
    const rows = body.data || [];

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="inline-msg">No requests match the selected filters.</td></tr>';
    } else {
      tbody.innerHTML = "";
      rows.forEach(r => {
        const tr = document.createElement("tr");

        // Target Pill
        let targetPill = '<span class="badge badge-neutral">Pending</span>';
        if (r.within_target === true) targetPill = '<span class="badge badge-success">Within Target</span>';
        else if (r.within_target === false) targetPill = '<span class="badge badge-danger">Missed</span>';

        // Completion Pill
        let latePill = '<span class="badge badge-neutral">Open</span>';
        if (r.completed_late === false) latePill = '<span class="badge badge-success">On Time</span>';
        else if (r.completed_late === true) latePill = '<span class="badge badge-danger">Late</span>';

        const responderName = r.responder
          ? `<strong>${escapeHtml(r.responder)}</strong> <span style="color: var(--text-muted); font-size: 11px;">#${r.responder_id}</span>`
          : '<span style="color: var(--text-light);">Unassigned</span>';

        tr.innerHTML = `
          <td class="num"><strong>#${r.id}</strong></td>
          <td>Site #${r.site_id}</td>
          <td>${responderName}</td>
          <td class="num">${formatDuration(r.response_business_minutes)}</td>
          <td>${targetPill}</td>
          <td>${latePill}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Update Pagination Bar with Total Pages
    const totalFiltered = getFilteredRequestsCount();
    const totalPages = Math.max(1, Math.ceil(totalFiltered / selectedLimit));
    const currentPage = pageIndex + 1;
    document.getElementById("pagination-info").textContent = `Page ${currentPage} of ${totalPages} • Showing ${rows.length} rows`;
    document.getElementById("btn-page-prev").disabled = (pageIndex === 0);
    document.getElementById("btn-page-next").disabled = (nextCursor === null);
  } catch (err) {
    tbody.classList.remove("is-loading");
    if (err.name === "AbortError") return;
    tbody.innerHTML = `<tr><td colspan="6" class="inline-msg error">Network error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function goToNextPage() {
  if (!nextCursor) return;
  pageIndex++;
  if (pageIndex >= cursorStack.length) {
    cursorStack.push(nextCursor);
  } else {
    cursorStack[pageIndex] = nextCursor;
  }
  loadRequestsPage();
}

function goToPrevPage() {
  if (pageIndex <= 0) return;
  pageIndex--;
  loadRequestsPage();
}

/* --- HELPERS --- */
function formatDuration(mins) {
  if (mins === null || mins === undefined) return "—";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

