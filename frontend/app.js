/**
 * MedLens - Main Application Logic
 * Camera scanning, vault, interactions, knowledge graph, and risk scoring.
 */

const API_BASE = window.location.origin;
const state = {
    vault: JSON.parse(localStorage.getItem("medlens_vault") || "[]"),
    cameraStream: null,
    autoScanActive: false,
    autoScanTimer: null,
    autoScanCooldown: false,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    tabs: $$(".tab"),
    tabContents: $$(".tab-content"),
    cameraFeed: $("#camera-feed"),
    cameraCanvas: $("#camera-canvas"),
    cameraError: $("#camera-error"),
    btnCapture: $("#btn-capture"),
    fileInput: $("#file-input"),
    textInput: $("#text-input"),
    btnSearch: $("#btn-search"),
    resultsArea: $("#results-area"),
    resultsList: $("#results-list"),
    ocrTextDisplay: $("#ocr-text-display"),
    loading: $("#loading"),
    vaultList: $("#vault-list"),
    vaultEmpty: $("#vault-empty"),
    vaultBadge: $("#vault-badge"),
    riskSection: $("#risk-section"),
    riskResult: $("#risk-result"),
    matrixResults: $("#matrix-results"),
    matrixEmpty: $("#matrix-empty"),
    analyticsStats: $("#analytics-stats"),
    dangerRanking: $("#danger-ranking"),
    vaultGraphSection: $("#vault-graph-section"),
    vaultGraphAnalysis: $("#vault-graph-analysis"),
    graphCanvas: $("#graph-canvas"),
    modal: $("#drug-modal"),
    modalBackdrop: $("#modal-backdrop"),
    modalClose: $("#modal-close"),
    modalBody: $("#modal-body"),
};

// ============ Tab Navigation ============

els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        els.tabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        els.tabContents.forEach((c) => c.classList.remove("active"));
        $(`#${target}-section`).classList.add("active");

        if (target === "vault") { renderVault(); }
        if (target === "matrix") { renderMatrix(); }
        if (target === "analytics") { loadAnalytics(); }
    });
});

// ============ Camera ============

async function initCamera() {
    try {
        // Try back camera first, fall back to any camera
        let constraints = { video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } } };
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (e) {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
        }
        state.cameraStream = stream;
        els.cameraFeed.srcObject = stream;
        els.cameraError.style.display = "none";

        // Wait for video to actually start playing
        await new Promise((resolve) => {
            els.cameraFeed.onloadeddata = resolve;
            if (els.cameraFeed.readyState >= 2) resolve();
        });
        state.cameraReady = true;
        console.log("Camera ready:", els.cameraFeed.videoWidth, "x", els.cameraFeed.videoHeight);
    } catch (err) {
        console.log("Camera not available:", err.message);
        state.cameraReady = false;
        els.cameraError.style.display = "flex";
        const overlay = $(".camera-overlay");
        if (overlay) overlay.style.display = "none";
    }
}

function captureFrame() {
    const video = els.cameraFeed;
    const canvas = els.cameraCanvas;
    // Guard: make sure video is actually streaming with real dimensions
    if (!video.srcObject || !state.cameraReady || video.videoWidth === 0 || video.videoHeight === 0) {
        return Promise.resolve(null);
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92));
}

// ============ Auto-Scan Mode ============

let autoScanCount = 0;

function toggleAutoScan() {
    if (state.autoScanActive) {
        stopAutoScan();
    } else {
        startAutoScan();
    }
}

function startAutoScan() {
    if (!state.cameraReady || !state.cameraStream) {
        showToast("Camera not ready yet. Please wait or use upload.");
        return;
    }
    state.autoScanActive = true;
    autoScanCount = 0;
    const btn = $("#btn-autoscan");
    if (btn) {
        btn.innerHTML = '<span class="btn-icon">⏹</span> Stop Scanning...';
        btn.classList.add("active-scan");
    }
    $(".camera-container").classList.add("auto-scanning");
    updateScanHint("Scanning... Hold medicine strip in frame");
    showToast("Auto-scan ON. Hold medicine in the frame.");

    // Start scanning loop
    autoScanLoop();
}

function stopAutoScan() {
    state.autoScanActive = false;
    if (state.autoScanTimer) { clearTimeout(state.autoScanTimer); state.autoScanTimer = null; }
    const btn = $("#btn-autoscan");
    if (btn) {
        btn.innerHTML = '<span class="btn-icon">🔄</span> Auto-Scan';
        btn.classList.remove("active-scan");
    }
    $(".camera-container").classList.remove("auto-scanning");
    updateScanHint("Place medicine strip or bottle inside the frame");
}

function updateScanHint(text) {
    const hint = $(".scan-hint");
    if (hint) hint.textContent = text;
}

async function autoScanLoop() {
    if (!state.autoScanActive) return;
    autoScanCount++;

    try {
        const blob = await captureFrame();
        if (!blob) {
            // Camera not ready yet, retry after a delay
            if (state.autoScanActive) {
                updateScanHint("Waiting for camera...");
                state.autoScanTimer = setTimeout(autoScanLoop, 2000);
            }
            return;
        }

        updateScanHint(`Scanning... (attempt ${autoScanCount})`);

        // Send to API silently (no loading overlay)
        const formData = new FormData();
        formData.append("file", blob, "autoscan.jpg");
        const res = await fetch(`${API_BASE}/api/scan/image`, { method: "POST", body: formData });
        const data = await res.json();

        // Show what OCR detected even if no match
        if (data.extracted_text && data.extracted_text.trim()) {
            updateScanHint(`Read: "${data.extracted_text.substring(0, 50)}..." (attempt ${autoScanCount})`);
        } else {
            updateScanHint(`No text found yet, scanning... (attempt ${autoScanCount})`);
        }

        if (data.success && data.matches && data.matches.length > 0) {
            // Found a drug! Show results and stop
            stopAutoScan();
            displayResults(data);
            showToast(`Found: ${data.matches[0].drug_info.generic_name}`);
            // Vibrate on mobile to signal detection
            if (navigator.vibrate) navigator.vibrate(200);
            return;
        }
    } catch (err) {
        console.log("Auto-scan cycle error:", err.message);
        updateScanHint(`Retry... (attempt ${autoScanCount})`);
    }

    // Schedule next scan if still active (every 3 seconds)
    if (state.autoScanActive) {
        state.autoScanTimer = setTimeout(autoScanLoop, 3000);
    }
}

// ============ Scanning ============

els.btnCapture.addEventListener("click", async () => {
    const blob = await captureFrame();
    if (!blob) {
        showToast("Camera not running. Upload a photo or type the name.");
        return;
    }
    await scanImage(blob);
});

els.fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) await scanImage(file);
    e.target.value = "";
});

els.btnSearch.addEventListener("click", () => {
    const text = els.textInput.value.trim();
    if (text) scanText(text);
});

els.textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        const text = els.textInput.value.trim();
        if (text) scanText(text);
    }
});

async function scanImage(imageBlob) {
    showLoading(true);
    try {
        const formData = new FormData();
        formData.append("file", imageBlob, "scan.jpg");
        const res = await fetch(`${API_BASE}/api/scan/image`, { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Scan failed");
        displayResults(data);
    } catch (err) {
        console.error("Image scan error:", err);
        showToast("Could not scan the image. Try typing the medicine name instead.");
    } finally { showLoading(false); }
}

async function scanText(text) {
    showLoading(true);
    try {
        const res = await fetch(`${API_BASE}/api/scan/text`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Search failed");
        displayResults(data);
    } catch (err) {
        console.error("Text scan error:", err);
        showToast("Something went wrong. Please try again.");
    } finally { showLoading(false); }
}

// ============ Display Results ============

function displayResults(data) {
    els.resultsArea.style.display = "block";
    els.ocrTextDisplay.textContent = data.extracted_text ? `Detected text: "${data.extracted_text}"` : "";

    if (!data.matches || data.matches.length === 0) {
        els.resultsList.innerHTML = `<div class="result-card"><p style="color:var(--text-muted);text-align:center;padding:20px;">No medicines found. Try a clearer photo or type the name.</p></div>`;
        return;
    }

    els.resultsList.innerHTML = data.matches.map((match, i) => {
        const drug = match.drug_info;
        const isInVault = state.vault.some((v) => v.drug_key === match.drug_key);
        const mlBadge = match.source === "ml_ner" ? '<span class="ml-badge">ML NER</span>' : '';

        return `
            <div class="result-card" style="animation-delay:${i * 0.1}s">
                <div class="result-drug-name">${drug.generic_name}${mlBadge}</div>
                <div class="result-match-info">Matched "${match.matched_term}" with ${match.confidence}% confidence</div>
                <div class="confidence-bar"><div class="confidence-fill" style="width:${match.confidence}%"></div></div>
                <span class="result-category">${drug.category}</span>
                <p class="result-description">${drug.description}</p>
                <p class="result-brands"><strong>Also sold as:</strong> ${drug.brand_names.join(", ")}</p>
                <div class="result-actions">
                    <button class="btn btn-small btn-success" onclick="addToVault('${match.drug_key}')" ${isInVault ? 'disabled style="opacity:0.5"' : ""}>
                        ${isInVault ? "Already saved" : "Add to My Meds"}
                    </button>
                    <button class="btn btn-small btn-secondary" onclick="showDrugDetail('${match.drug_key}')">Full details</button>
                    <button class="btn btn-small btn-speak" onclick="speakDrug('${match.drug_key}')">🔊 Read aloud</button>
                </div>
                <div id="interactions-${match.drug_key}"></div>
            </div>`;
    }).join("");

    data.matches.forEach((match) => { if (state.vault.length > 0) checkInteractionsForResult(match.drug_key); });
    els.resultsArea.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function checkInteractionsForResult(drugKey) {
    const vaultKeys = state.vault.map((v) => v.drug_key);
    if (vaultKeys.length === 0) return;
    try {
        const res = await fetch(`${API_BASE}/api/interactions/check`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ drug_key: drugKey, vault_keys: vaultKeys }),
        });
        const data = await res.json();
        const container = $(`#interactions-${drugKey}`);
        if (!container) return;

        if (data.interactions.length === 0) {
            container.innerHTML = `<div class="interaction-alert minor" style="margin-top:12px"><div class="alert-severity minor">All clear</div><div class="alert-title">No interactions found with your saved medications</div></div>`;
            return;
        }
        container.innerHTML = data.interactions.map((i) => `
            <div class="interaction-alert ${i.severity.toLowerCase()}">
                <div class="alert-severity ${i.severity.toLowerCase()}">${i.severity}</div>
                <div class="alert-title">Interacts with ${i.interacting_drug_name}</div>
                <div class="alert-description">${i.description}</div>
                <div class="alert-recommendation">What to do: ${i.recommendation}</div>
            </div>`).join("");
    } catch (err) { console.error("Interaction check failed:", err); }
}

// ============ Vault ============

function addToVault(drugKey) {
    if (state.vault.some((v) => v.drug_key === drugKey)) return;
    fetch(`${API_BASE}/api/drug/${drugKey}`).then((r) => r.json()).then((data) => {
        state.vault.push({ drug_key: drugKey, generic_name: data.drug_info.generic_name, category: data.drug_info.category, added_at: new Date().toISOString() });
        saveVault(); updateVaultBadge();
        showToast(`${data.drug_info.generic_name} added to your medications.`);
        const btn = document.querySelector(`[onclick="addToVault('${drugKey}')"]`);
        if (btn) { btn.textContent = "Already saved"; btn.disabled = true; btn.style.opacity = "0.5"; }
        document.querySelectorAll("[id^='interactions-']").forEach((el) => {
            checkInteractionsForResult(el.id.replace("interactions-", ""));
        });
    });
}

function removeFromVault(drugKey) {
    const drug = state.vault.find((v) => v.drug_key === drugKey);
    state.vault = state.vault.filter((v) => v.drug_key !== drugKey);
    saveVault(); updateVaultBadge(); renderVault();
    if (drug) showToast(`${drug.generic_name} removed.`);
}

function saveVault() { localStorage.setItem("medlens_vault", JSON.stringify(state.vault)); }

function updateVaultBadge() {
    const count = state.vault.length;
    els.vaultBadge.textContent = count;
    els.vaultBadge.style.display = count > 0 ? "flex" : "none";
}

function renderVault() {
    els.vaultList.querySelectorAll(".vault-item").forEach((el) => el.remove());
    if (state.vault.length === 0) { els.vaultEmpty.style.display = "block"; els.riskSection.style.display = "none"; return; }
    els.vaultEmpty.style.display = "none";
    els.riskSection.style.display = "block";

    state.vault.forEach((item) => {
        const div = document.createElement("div");
        div.className = "vault-item";
        div.innerHTML = `
            <div class="vault-item-info" onclick="showDrugDetail('${item.drug_key}')">
                <div class="vault-item-name">${item.generic_name}</div>
                <div class="vault-item-category">${item.category}</div>
            </div>
            <button class="btn btn-small btn-danger" onclick="removeFromVault('${item.drug_key}')">Remove</button>`;
        els.vaultList.appendChild(div);
    });
}

// ============ Risk Scoring ============

async function calculateRisk() {
    const ageGroup = $("#age-group").value;
    const condSelect = $("#conditions");
    const conditions = Array.from(condSelect.selectedOptions).map((o) => o.value);
    const vaultKeys = state.vault.map((v) => v.drug_key);

    if (vaultKeys.length < 2) { showToast("Add at least 2 medications first."); return; }

    try {
        const res = await fetch(`${API_BASE}/api/risk/score`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vault_keys: vaultKeys, age_group: ageGroup, conditions }),
        });
        const data = await res.json();

        els.riskResult.innerHTML = `
            <div class="risk-score-value" style="color:${data.risk_color}">${data.overall_score}</div>
            <div class="risk-level-label" style="color:${data.risk_color}">${data.risk_level} RISK</div>
            <div class="risk-meter"><div class="risk-meter-fill" style="width:${data.overall_score}%;background:${data.risk_color}"></div></div>
            <div class="risk-factors">
                ${data.factors.map((f) => `<div class="risk-factor">- ${f}</div>`).join("")}
            </div>
            <div class="risk-recommendation">${data.recommendation}</div>
            <div style="margin-top:12px;font-size:11px;color:var(--text-muted)">
                Model breakdown: base severity ${data.breakdown.base_severity}, polypharmacy x${data.breakdown.polypharmacy_multiplier},
                age x${data.breakdown.age_multiplier}, conditions x${data.breakdown.condition_multiplier},
                density x${data.breakdown.density_multiplier}
            </div>`;
    } catch (err) { console.error("Risk scoring failed:", err); showToast("Risk calculation failed."); }
}

// ============ Matrix ============

async function renderMatrix() {
    if (state.vault.length < 2) { els.matrixEmpty.style.display = "block"; els.matrixResults.innerHTML = ""; return; }
    els.matrixEmpty.style.display = "none";
    try {
        const res = await fetch(`${API_BASE}/api/interactions/matrix`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vault_keys: state.vault.map((v) => v.drug_key) }),
        });
        const data = await res.json();
        if (data.interactions.length === 0) {
            els.matrixResults.innerHTML = `<div class="matrix-safe"><span class="matrix-safe-icon">✅</span><p>No known interactions between your ${state.vault.length} medications. You're good!</p></div>`;
            return;
        }
        els.matrixResults.innerHTML = data.interactions.map((i) => `
            <div class="matrix-card">
                <div class="matrix-pair">${i.drug_a_name} + ${i.drug_b_name}</div>
                <span class="matrix-severity ${i.severity.toLowerCase()}">${i.severity}</span>
                <p class="matrix-desc">${i.description}</p>
                <div class="matrix-rec">What to do: ${i.recommendation}</div>
            </div>`).join("");
    } catch (err) { els.matrixResults.innerHTML = `<p style="color:var(--text-muted);text-align:center;">Could not load interactions.</p>`; }
}

// ============ Analytics / Knowledge Graph ============

async function loadAnalytics() {
    try {
        const res = await fetch(`${API_BASE}/api/analytics/graph`);
        const data = await res.json();

        // Stats cards
        const s = data.stats;
        els.analyticsStats.innerHTML = `
            <div class="stat-card"><div class="stat-value">${s.node_count}</div><div class="stat-label">Drugs in Database</div></div>
            <div class="stat-card"><div class="stat-value">${s.edge_count}</div><div class="stat-label">Known Interactions</div></div>
            <div class="stat-card"><div class="stat-value">${s.avg_degree}</div><div class="stat-label">Avg Interactions/Drug</div></div>
            <div class="stat-card"><div class="stat-value">${(s.density * 100).toFixed(1)}%</div><div class="stat-label">Network Density</div></div>`;

        // Danger ranking
        els.dangerRanking.innerHTML = `<h3>Highest-Risk Drugs (by centrality)</h3>` +
            s.danger_ranking.slice(0, 8).map((d, i) => `
                <div class="danger-item">
                    <div>
                        <div class="danger-item-name">${i + 1}. ${d.drug_name}</div>
                        <div class="danger-item-stats">${d.interaction_count} interactions, betweenness: ${d.betweenness}</div>
                    </div>
                    <div class="danger-item-score">${(d.degree_centrality * 100).toFixed(0)}%</div>
                </div>`).join("");

        // Draw knowledge graph
        drawGraph(data.nodes, data.edges);

        // Vault subgraph if enough meds
        if (state.vault.length >= 2) {
            els.vaultGraphSection.style.display = "block";
            const vRes = await fetch(`${API_BASE}/api/analytics/vault-graph`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vault_keys: state.vault.map((v) => v.drug_key) }),
            });
            const vData = await vRes.json();
            if (vData.has_data) {
                els.vaultGraphAnalysis.innerHTML = `
                    <div class="vault-graph-stat">
                        <div style="font-size:13px;font-weight:600;">Your ${vData.drug_count} medications have ${vData.interaction_count} interactions</div>
                        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">Risk density: ${vData.risk_density_pct}% of possible drug pairs interact</div>
                        ${vData.highest_risk_drug.name ? `<div style="font-size:12px;color:var(--severity-serious);margin-top:4px;">Highest risk: ${vData.highest_risk_drug.name} (${vData.highest_risk_drug.interaction_count} interactions in your list)</div>` : ''}
                    </div>
                    ${vData.risk_paths.map((p) => `
                        <div class="matrix-card">
                            <div class="matrix-pair">${p.from} + ${p.to}</div>
                            <span class="matrix-severity ${p.severity.toLowerCase()}">${p.severity}</span>
                            <p class="matrix-desc">${p.description}</p>
                        </div>`).join("")}`;
            }
        }
    } catch (err) { console.error("Analytics load failed:", err); }
}

function drawGraph(nodes, edges) {
    const canvas = els.graphCanvas;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Force-directed layout (simple spring simulation)
    const positions = {};
    nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length;
        const r = Math.min(W, H) * 0.35;
        positions[n.id] = { x: W / 2 + r * Math.cos(angle), y: H / 2 + r * Math.sin(angle) };
    });

    // Run a few iterations of force layout
    for (let iter = 0; iter < 80; iter++) {
        // Repulsion between all nodes
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = positions[nodes[i].id], b = positions[nodes[j].id];
                let dx = b.x - a.x, dy = b.y - a.y;
                let dist = Math.sqrt(dx * dx + dy * dy) || 1;
                let force = 800 / (dist * dist);
                a.x -= (dx / dist) * force;
                a.y -= (dy / dist) * force;
                b.x += (dx / dist) * force;
                b.y += (dy / dist) * force;
            }
        }
        // Attraction along edges
        edges.forEach((e) => {
            const a = positions[e.source], b = positions[e.target];
            if (!a || !b) return;
            let dx = b.x - a.x, dy = b.y - a.y;
            let dist = Math.sqrt(dx * dx + dy * dy) || 1;
            let force = (dist - 60) * 0.01;
            a.x += (dx / dist) * force;
            a.y += (dy / dist) * force;
            b.x -= (dx / dist) * force;
            b.y -= (dy / dist) * force;
        });
        // Center gravity
        nodes.forEach((n) => {
            const p = positions[n.id];
            p.x += (W / 2 - p.x) * 0.01;
            p.y += (H / 2 - p.y) * 0.01;
            p.x = Math.max(30, Math.min(W - 30, p.x));
            p.y = Math.max(30, Math.min(H - 30, p.y));
        });
    }

    // Draw edges
    edges.forEach((e) => {
        const a = positions[e.source], b = positions[e.target];
        if (!a || !b) return;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = e.color || "rgba(100,116,139,0.3)";
        ctx.lineWidth = e.width || 1;
        ctx.stroke();
    });

    // Draw nodes
    nodes.forEach((n) => {
        const p = positions[n.id];
        const r = Math.min(n.size || 8, 20);
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
        grad.addColorStop(0, "#3b82f6");
        grad.addColorStop(1, "#1e40af");
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,0.2)";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Labels for high-degree nodes
        if (n.degree >= 3) {
            ctx.fillStyle = "rgba(241,245,249,0.8)";
            ctx.font = "9px Inter, sans-serif";
            ctx.textAlign = "center";
            ctx.fillText(n.label.split(" ")[0], p.x, p.y + r + 12);
        }
    });
}

// ============ Drug Detail Modal ============

async function showDrugDetail(drugKey) {
    try {
        const res = await fetch(`${API_BASE}/api/drug/${drugKey}`);
        const data = await res.json();
        const drug = data.drug_info;
        els.modalBody.innerHTML = `
            <div class="modal-drug-name">${drug.generic_name}</div>
            <span class="result-category">${drug.category}</span>
            <div class="modal-section"><div class="modal-section-title">What it does</div><p>${drug.description}</p></div>
            <div class="modal-section"><div class="modal-section-title">Brand names</div><p>${drug.brand_names.join(", ")}</p></div>
            <div class="modal-section"><div class="modal-section-title">Usual dosage</div><p>${drug.common_dosage}</p><p style="margin-top:4px;color:var(--severity-serious)">Max daily: ${drug.max_daily_dose}</p></div>
            <div class="modal-section"><div class="modal-section-title">Side effects</div><ul>${drug.side_effects.map((s) => `<li>${s}</li>`).join("")}</ul></div>
            <div class="modal-section"><div class="modal-section-title">Warnings</div><ul>${drug.warnings.map((w) => `<li>${w}</li>`).join("")}</ul></div>
            <div class="result-actions" style="margin-top:20px"><button class="btn btn-small btn-speak" onclick="speakDrugDetail('${drugKey}')">🔊 Read this aloud</button></div>`;
        els.modal.style.display = "flex";
    } catch (err) { console.error("Drug detail fetch failed:", err); }
}

els.modalClose.addEventListener("click", () => { els.modal.style.display = "none"; window.speechSynthesis.cancel(); });
els.modalBackdrop.addEventListener("click", () => { els.modal.style.display = "none"; window.speechSynthesis.cancel(); });

// ============ Text-to-Speech ============

function speakDrug(drugKey) {
    fetch(`${API_BASE}/api/drug/${drugKey}`).then((r) => r.json()).then((data) => {
        const d = data.drug_info;
        speak(`${d.generic_name}. ${d.description}. Common side effects include ${d.side_effects.join(", ")}.`);
    });
}

function speakDrugDetail(drugKey) {
    fetch(`${API_BASE}/api/drug/${drugKey}`).then((r) => r.json()).then((data) => {
        const d = data.drug_info;
        speak(`${d.generic_name}. Also known as ${d.brand_names.slice(0, 3).join(", ")}. ${d.description} The usual dose is ${d.common_dosage}. Side effects to watch for: ${d.side_effects.join(", ")}. Important: ${d.warnings.join(". ")}.`);
    });
}

function speak(text) {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = 0.9; u.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    const pref = voices.find((v) => v.lang.startsWith("en") && v.name.includes("Google"));
    if (pref) u.voice = pref;
    window.speechSynthesis.speak(u);
}

// ============ Toast ============

function showToast(message) {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    toast.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--bg-card);color:var(--text-primary);padding:12px 24px;border-radius:12px;font-size:13px;font-family:var(--font);box-shadow:0 8px 32px rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);z-index:300;animation:slideUp 0.3s ease;max-width:90%;text-align:center;`;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = "0"; toast.style.transition = "opacity 0.3s"; setTimeout(() => toast.remove(), 300); }, 3000);
}

function showLoading(show) { els.loading.style.display = show ? "flex" : "none"; }

// Global functions
window.addToVault = addToVault;
window.removeFromVault = removeFromVault;
window.showDrugDetail = showDrugDetail;
window.speakDrug = speakDrug;
window.speakDrugDetail = speakDrugDetail;
window.calculateRisk = calculateRisk;
window.toggleAutoScan = toggleAutoScan;

// ============ Init ============

document.addEventListener("DOMContentLoaded", () => {
    initCamera();
    updateVaultBadge();
    if (window.speechSynthesis) {
        window.speechSynthesis.getVoices();
        window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
});
