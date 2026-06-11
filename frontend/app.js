/**
 * MedLens - Main Application Logic
 * Handles camera, scanning, vault management, and interaction checking.
 */

const API_BASE = window.location.origin;

// ── State ───────────────────────────────────────────────────────────────────

const state = {
    vault: JSON.parse(localStorage.getItem("medlens_vault") || "[]"),
    cameraStream: null,
    currentLanguage: "en-US",
};

// ── DOM References ──────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    tabs: $$(".tab"),
    tabContents: $$(".tab-content"),
    cameraFeed: $("#camera-feed"),
    cameraCanvas: $("#camera-canvas"),
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
    matrixResults: $("#matrix-results"),
    matrixEmpty: $("#matrix-empty"),
    modal: $("#drug-modal"),
    modalBackdrop: $("#modal-backdrop"),
    modalClose: $("#modal-close"),
    modalBody: $("#modal-body"),
};

// ── Tab Navigation ──────────────────────────────────────────────────────────

els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        const target = tab.dataset.tab;

        els.tabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");

        els.tabContents.forEach((c) => c.classList.remove("active"));
        $(`#${target}-section`).classList.add("active");

        if (target === "vault") renderVault();
        if (target === "matrix") renderMatrix();
    });
});

// ── Camera ──────────────────────────────────────────────────────────────────

async function initCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
        });
        state.cameraStream = stream;
        els.cameraFeed.srcObject = stream;
    } catch (err) {
        console.log("Camera not available:", err.message);
        // Camera is optional, text input always works
    }
}

function captureFrame() {
    const video = els.cameraFeed;
    const canvas = els.cameraCanvas;

    if (!video.srcObject) return null;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    return new Promise((resolve) => {
        canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9);
    });
}

// ── Scanning ────────────────────────────────────────────────────────────────

els.btnCapture.addEventListener("click", async () => {
    const blob = await captureFrame();
    if (!blob) {
        showToast("Camera is not running. Try uploading a photo or typing the name.");
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

        const res = await fetch(`${API_BASE}/api/scan/image`, {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Scan failed");

        displayResults(data);
    } catch (err) {
        console.error("Image scan error:", err);
        showToast("Could not scan the image. Try typing the medicine name instead.");
    } finally {
        showLoading(false);
    }
}

async function scanText(text) {
    showLoading(true);
    try {
        const res = await fetch(`${API_BASE}/api/scan/text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Search failed");

        displayResults(data);
    } catch (err) {
        console.error("Text scan error:", err);
        showToast("Something went wrong. Please try again.");
    } finally {
        showLoading(false);
    }
}

// ── Display Results ─────────────────────────────────────────────────────────

function displayResults(data) {
    els.resultsArea.style.display = "block";
    els.ocrTextDisplay.textContent = data.extracted_text
        ? `Detected text: "${data.extracted_text}"`
        : "";

    if (!data.matches || data.matches.length === 0) {
        els.resultsList.innerHTML = `
            <div class="result-card">
                <p style="color: var(--text-muted); text-align: center; padding: 20px;">
                    No medicines found. Try a clearer photo or type the name manually.
                </p>
            </div>
        `;
        return;
    }

    els.resultsList.innerHTML = data.matches.map((match, i) => {
        const drug = match.drug_info;
        const isInVault = state.vault.some((v) => v.drug_key === match.drug_key);

        return `
            <div class="result-card" style="animation-delay: ${i * 0.1}s">
                <div class="result-drug-name">${drug.generic_name}</div>
                <div class="result-match-info">
                    Matched "${match.matched_term}" with ${match.confidence}% confidence
                </div>
                <div class="confidence-bar">
                    <div class="confidence-fill" style="width: ${match.confidence}%"></div>
                </div>
                <span class="result-category">${drug.category}</span>
                <p class="result-description">${drug.description}</p>
                <p class="result-brands">
                    <strong>Also sold as:</strong> ${drug.brand_names.join(", ")}
                </p>
                <div class="result-actions">
                    <button class="btn btn-small btn-success" onclick="addToVault('${match.drug_key}')"
                        ${isInVault ? 'disabled style="opacity:0.5"' : ""}>
                        ${isInVault ? "Already saved" : "Add to My Meds"}
                    </button>
                    <button class="btn btn-small btn-secondary" onclick="showDrugDetail('${match.drug_key}')">
                        Full details
                    </button>
                    <button class="btn btn-small btn-speak" onclick="speakDrug('${match.drug_key}')">
                        🔊 Read aloud
                    </button>
                </div>
                <div id="interactions-${match.drug_key}"></div>
            </div>
        `;
    }).join("");

    // Check interactions for each match against vault
    data.matches.forEach((match) => {
        if (state.vault.length > 0) {
            checkInteractionsForResult(match.drug_key);
        }
    });

    // Scroll to results
    els.resultsArea.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function checkInteractionsForResult(drugKey) {
    const vaultKeys = state.vault.map((v) => v.drug_key);
    if (vaultKeys.length === 0) return;

    try {
        const res = await fetch(`${API_BASE}/api/interactions/check`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ drug_key: drugKey, vault_keys: vaultKeys }),
        });

        const data = await res.json();
        const container = $(`#interactions-${drugKey}`);
        if (!container) return;

        if (data.interactions.length === 0) {
            container.innerHTML = `
                <div class="interaction-alert minor" style="margin-top: 12px">
                    <div class="alert-severity minor">All clear</div>
                    <div class="alert-title">No interactions found with your saved medications</div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.interactions.map((interaction) => `
            <div class="interaction-alert ${interaction.severity.toLowerCase()}">
                <div class="alert-severity ${interaction.severity.toLowerCase()}">${interaction.severity}</div>
                <div class="alert-title">Interacts with ${interaction.interacting_drug_name}</div>
                <div class="alert-description">${interaction.description}</div>
                <div class="alert-recommendation">What to do: ${interaction.recommendation}</div>
            </div>
        `).join("");

    } catch (err) {
        console.error("Interaction check failed:", err);
    }
}

// ── Vault Management ────────────────────────────────────────────────────────

function addToVault(drugKey) {
    if (state.vault.some((v) => v.drug_key === drugKey)) {
        showToast("This medicine is already in your list.");
        return;
    }

    // Fetch drug info to store
    fetch(`${API_BASE}/api/drug/${drugKey}`)
        .then((r) => r.json())
        .then((data) => {
            state.vault.push({
                drug_key: drugKey,
                generic_name: data.drug_info.generic_name,
                category: data.drug_info.category,
                added_at: new Date().toISOString(),
            });
            saveVault();
            updateVaultBadge();
            showToast(`${data.drug_info.generic_name} added to your medications.`);

            // Re-render results to update button state
            const btn = document.querySelector(`[onclick="addToVault('${drugKey}')"]`);
            if (btn) {
                btn.textContent = "Already saved";
                btn.disabled = true;
                btn.style.opacity = "0.5";
            }

            // Re-check interactions since vault changed
            const matches = document.querySelectorAll("[id^='interactions-']");
            matches.forEach((el) => {
                const key = el.id.replace("interactions-", "");
                checkInteractionsForResult(key);
            });
        });
}

function removeFromVault(drugKey) {
    const drug = state.vault.find((v) => v.drug_key === drugKey);
    state.vault = state.vault.filter((v) => v.drug_key !== drugKey);
    saveVault();
    updateVaultBadge();
    renderVault();
    if (drug) showToast(`${drug.generic_name} removed.`);
}

function saveVault() {
    localStorage.setItem("medlens_vault", JSON.stringify(state.vault));
}

function updateVaultBadge() {
    const count = state.vault.length;
    els.vaultBadge.textContent = count;
    els.vaultBadge.style.display = count > 0 ? "flex" : "none";
}

function renderVault() {
    if (state.vault.length === 0) {
        els.vaultEmpty.style.display = "block";
        els.vaultList.querySelectorAll(".vault-item").forEach((el) => el.remove());
        return;
    }

    els.vaultEmpty.style.display = "none";

    // Remove old vault items (keep the empty placeholder)
    els.vaultList.querySelectorAll(".vault-item").forEach((el) => el.remove());

    state.vault.forEach((item) => {
        const div = document.createElement("div");
        div.className = "vault-item";
        div.innerHTML = `
            <div class="vault-item-info" onclick="showDrugDetail('${item.drug_key}')" style="cursor:pointer">
                <div class="vault-item-name">${item.generic_name}</div>
                <div class="vault-item-category">${item.category}</div>
            </div>
            <button class="btn btn-small btn-danger" onclick="removeFromVault('${item.drug_key}')">
                Remove
            </button>
        `;
        els.vaultList.appendChild(div);
    });
}

// ── Interaction Matrix ──────────────────────────────────────────────────────

async function renderMatrix() {
    if (state.vault.length < 2) {
        els.matrixEmpty.style.display = "block";
        els.matrixResults.innerHTML = "";
        return;
    }

    els.matrixEmpty.style.display = "none";

    try {
        const res = await fetch(`${API_BASE}/api/interactions/matrix`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vault_keys: state.vault.map((v) => v.drug_key) }),
        });

        const data = await res.json();

        if (data.interactions.length === 0) {
            els.matrixResults.innerHTML = `
                <div class="matrix-safe">
                    <span class="matrix-safe-icon">✅</span>
                    <p>No known interactions between your ${state.vault.length} saved medications. You're good!</p>
                </div>
            `;
            return;
        }

        els.matrixResults.innerHTML = data.interactions.map((interaction) => `
            <div class="matrix-card">
                <div class="matrix-pair">${interaction.drug_a_name} + ${interaction.drug_b_name}</div>
                <span class="matrix-severity ${interaction.severity.toLowerCase()}">${interaction.severity}</span>
                <p class="matrix-desc">${interaction.description}</p>
                <div class="matrix-rec">What to do: ${interaction.recommendation}</div>
            </div>
        `).join("");

    } catch (err) {
        console.error("Matrix fetch failed:", err);
        els.matrixResults.innerHTML = `<p style="color: var(--text-muted); text-align: center;">Could not load interactions. Make sure the server is running.</p>`;
    }
}

// ── Drug Detail Modal ───────────────────────────────────────────────────────

async function showDrugDetail(drugKey) {
    try {
        const res = await fetch(`${API_BASE}/api/drug/${drugKey}`);
        const data = await res.json();
        const drug = data.drug_info;

        els.modalBody.innerHTML = `
            <div class="modal-drug-name">${drug.generic_name}</div>
            <span class="result-category">${drug.category}</span>

            <div class="modal-section">
                <div class="modal-section-title">What it does</div>
                <p>${drug.description}</p>
            </div>

            <div class="modal-section">
                <div class="modal-section-title">Brand names</div>
                <p>${drug.brand_names.join(", ")}</p>
            </div>

            <div class="modal-section">
                <div class="modal-section-title">Usual dosage</div>
                <p>${drug.common_dosage}</p>
                <p style="margin-top:4px; color: var(--severity-serious)">
                    Maximum daily dose: ${drug.max_daily_dose}
                </p>
            </div>

            <div class="modal-section">
                <div class="modal-section-title">Side effects to watch for</div>
                <ul>
                    ${drug.side_effects.map((s) => `<li>${s}</li>`).join("")}
                </ul>
            </div>

            <div class="modal-section">
                <div class="modal-section-title">Important warnings</div>
                <ul>
                    ${drug.warnings.map((w) => `<li>${w}</li>`).join("")}
                </ul>
            </div>

            <div class="result-actions" style="margin-top: 20px">
                <button class="btn btn-small btn-speak" onclick="speakDrugDetail('${drugKey}')">
                    🔊 Read this aloud
                </button>
            </div>
        `;

        els.modal.style.display = "flex";
    } catch (err) {
        console.error("Drug detail fetch failed:", err);
    }
}

els.modalClose.addEventListener("click", () => {
    els.modal.style.display = "none";
    window.speechSynthesis.cancel();
});

els.modalBackdrop.addEventListener("click", () => {
    els.modal.style.display = "none";
    window.speechSynthesis.cancel();
});

// ── Text-to-Speech ──────────────────────────────────────────────────────────

function speakDrug(drugKey) {
    fetch(`${API_BASE}/api/drug/${drugKey}`)
        .then((r) => r.json())
        .then((data) => {
            const drug = data.drug_info;
            const text = `${drug.generic_name}. ${drug.description}. Common side effects include ${drug.side_effects.join(", ")}.`;
            speak(text);
        });
}

function speakDrugDetail(drugKey) {
    fetch(`${API_BASE}/api/drug/${drugKey}`)
        .then((r) => r.json())
        .then((data) => {
            const drug = data.drug_info;
            const text = [
                `${drug.generic_name}.`,
                `Also known as ${drug.brand_names.slice(0, 3).join(", ")}.`,
                drug.description,
                `The usual dose is ${drug.common_dosage}.`,
                `Side effects to watch for: ${drug.side_effects.join(", ")}.`,
                `Important: ${drug.warnings.join(". ")}.`,
            ].join(" ");
            speak(text);
        });
}

function speak(text) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = state.currentLanguage;
    utterance.rate = 0.9;
    utterance.pitch = 1;

    // Try to find a good voice
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find((v) => v.lang.startsWith("en") && v.name.includes("Google"));
    if (preferred) utterance.voice = preferred;

    window.speechSynthesis.speak(utterance);
}

// ── Toast Notifications ─────────────────────────────────────────────────────

function showToast(message) {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--bg-card);
        color: var(--text-primary);
        padding: 12px 24px;
        border-radius: 12px;
        font-size: 13px;
        font-family: var(--font);
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.08);
        z-index: 300;
        animation: slideUp 0.3s ease;
        max-width: 90%;
        text-align: center;
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.3s";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ── Utility ─────────────────────────────────────────────────────────────────

function showLoading(show) {
    els.loading.style.display = show ? "flex" : "none";
}

// ── Make functions available globally ────────────────────────────────────────
window.addToVault = addToVault;
window.removeFromVault = removeFromVault;
window.showDrugDetail = showDrugDetail;
window.speakDrug = speakDrug;
window.speakDrugDetail = speakDrugDetail;

// ── Initialize ──────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    initCamera();
    updateVaultBadge();

    // Pre-load voices for TTS
    if (window.speechSynthesis) {
        window.speechSynthesis.getVoices();
        window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
});
