// Clash of Clans Farming Bot — Web UI Client Controller

const BUTTON_METADATA = [
  { key: "attack_button", name: "Attack Button", desc: "Orange Attack button on village screen" },
  { key: "find_match", name: "Find Match", desc: "Attack menu Find a Match button" },
  { key: "next_button", name: "Next Button", desc: "Scouting view Next button (bottom-right)" },
  { key: "surrender_button", name: "Surrender Button", desc: "Battle white-flag Surrender button" },
  { key: "confirm_surrender", name: "Confirm Surrender", desc: "Okay / confirmation popup button" },
  { key: "return_home", name: "Return Home", desc: "Battle-end screen Return Home button" },
  { key: "train_button", name: "Train Button", desc: "Village train troops button (bottom-right)" },
  { key: "quick_train", name: "Quick Train", desc: "Army screen Quick Train button" },
  { key: "builder_face", name: "Builder Menu Icon", desc: "Top-bar builder icon to open suggested upgrades" },
  { key: "suggested_upgrades", name: "Suggested Upgrades Header", desc: "Header of the builder drop-down list" },
  { key: "all_builders_busy", name: "All Builders Busy", desc: "Notice when 0 builders are currently available" },
  { key: "upgrade_button", name: "Upgrade Action Button", desc: "Green Upgrade button below building info" },
  { key: "confirm_upgrade_gold", name: "Confirm Gold Upgrade", desc: "Confirmation button for Gold upgrades" },
  { key: "confirm_upgrade_elixir", name: "Confirm Elixir Upgrade", desc: "Confirmation button for Elixir upgrades" },
  { key: "confirm_upgrade_hero", name: "Confirm Hero Upgrade", desc: "Confirmation button for Hero upgrades" },
  { key: "confirm_upgrade_de", name: "Confirm Dark Elixir Upgrade", desc: "Confirmation button for DE upgrades" },
  { key: "btn_lab_confirm", name: "Lab Research Confirm", desc: "Confirmation button for Lab troop/spell research" },
  { key: "lab_busy", name: "Laboratory Busy", desc: "Notice when research is active in the Lab" },
  { key: "close_modal", name: "Close Dialog (X)", desc: "Close X button to dismiss upgrade and info modals" },
  { key: "collect_gold", name: "Collect Gold", desc: "Gold mine collector bubble icon" },
  { key: "collect_elixir", name: "Collect Elixir", desc: "Elixir collector bubble icon" },
  { key: "shield_info", name: "Shield Info", desc: "Top bar shield/guard status icon" },
  { key: "battle_end", name: "Battle End", desc: "Battle victory/defeat indicator" },
  { key: "btn_lab_confirm_de", name: "Lab Research DE Confirm", desc: "Lab confirmation for Dark Elixir research" },
  { key: "zero_builders", name: "Zero Builders Counter", desc: "Zero free builders number display" },
  { key: "confirm_text", name: "Confirm Text", desc: "Generic confirmation text button" },
  { key: "upgrade_button_dim", name: "Upgrade Disabled", desc: "Grayed-out upgrade button when unaffordable" },
];

let currentConfig = null;
let currentCropTarget = null; // { name, type }
let cropCoords = null;        // [x, y, w, h] in 1280x720 canvas

// ----------------------------------------------------------------------------
// Initialization & Tab Navigation
// ----------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupBotControls();
  setupScreenTools();
  setupCropModal();
  setupSettings();
  setupLogs();

  // Initial loads
  fetchStatus();
  fetchDevices();
  fetchTemplates();
  fetchConfig();
  fetchLogs();

  // Polling loops
  setInterval(fetchStatus, 1000);
  setInterval(fetchLogs, 2000);
  setInterval(() => {
    if (document.getElementById("chk-auto-refresh").checked) {
      refreshScreenImage();
    }
  }, 2000);
});

function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById("pane-" + btn.dataset.tab);
      if (targetPane) targetPane.classList.add("active");

      if (btn.dataset.tab === "studio") fetchTemplates();
      if (btn.dataset.tab === "settings") fetchConfig();
    });
  });
}

// ----------------------------------------------------------------------------
// Status & Polling
// ----------------------------------------------------------------------------
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (!data.ok) return;

    // Update Phase Badge
    const badge = document.getElementById("phase-badge");
    badge.textContent = (data.phase || "IDLE").toUpperCase();
    if (data.phase === "Idle") {
      badge.style.color = "var(--text-secondary)";
      badge.style.borderColor = "var(--border)";
    } else if (data.phase === "Paused") {
      badge.style.color = "var(--warning)";
      badge.style.borderColor = "var(--warning)";
    } else {
      badge.style.color = "var(--success)";
      badge.style.borderColor = "var(--success)";
    }

    // Button states
    document.getElementById("btn-start").disabled = data.is_running && !data.is_paused;
    document.getElementById("btn-pause").disabled = !data.is_running;
    document.getElementById("btn-pause").textContent = data.is_paused ? "▶ RESUME" : "⏸ PAUSE";
    document.getElementById("btn-stop").disabled = !data.is_running;

    // Connection badge
    const connBadge = document.getElementById("conn-status");
    if (data.device) {
      connBadge.className = "status-badge status-online";
      connBadge.textContent = "● " + data.device;
    } else {
      connBadge.className = "status-badge status-offline";
      connBadge.textContent = "● No Device";
    }

    // Stats
    const s = data.stats || {};
    document.getElementById("stat-gold").textContent = (s.loot_gold || 0).toLocaleString();
    document.getElementById("stat-elixir").textContent = (s.loot_elixir || 0).toLocaleString();
    document.getElementById("stat-dark").textContent = (s.loot_dark || 0).toLocaleString();
    document.getElementById("stat-searches").textContent = (s.searches || 0).toLocaleString();
    document.getElementById("stat-skips").textContent = (s.skips || 0).toLocaleString();
    document.getElementById("stat-attacks").textContent = (s.attacks || 0).toLocaleString();
    if (document.getElementById("stat-buildings")) {
      document.getElementById("stat-buildings").textContent = (s.buildings_upgraded || 0).toLocaleString();
    }
    if (document.getElementById("stat-lab")) {
      document.getElementById("stat-lab").textContent = (s.lab_researches || 0).toLocaleString();
    }

    // Format uptime
    const sec = s.uptime_sec || 0;
    const hrs = String(Math.floor(sec / 3600)).padStart(2, "0");
    const mins = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
    const secs = String(sec % 60).padStart(2, "0");
    document.getElementById("stat-uptime").textContent = `${hrs}:${mins}:${secs}`;
  } catch (err) {
    console.debug("Status poll failed:", err);
  }
}

// ----------------------------------------------------------------------------
// Bot Execution Controls & ADB
// ----------------------------------------------------------------------------
function setupBotControls() {
  const btnUp = document.getElementById("btn-upgrade-village");
  if (btnUp) {
    btnUp.addEventListener("click", async () => {
      btnUp.disabled = true;
      btnUp.textContent = "⏳ Running Upgrades...";
      try {
        const res = await fetch("/api/village/upgrade", { method: "POST" });
        const data = await res.json();
        alert(data.message || "Village upgrade cycle initiated");
      } catch (err) {
        alert("Upgrade failed: " + err);
      } finally {
        btnUp.disabled = false;
        btnUp.textContent = "🔨 Upgrade Village Now";
        fetchStatus();
      }
    });
  }

  document.getElementById("btn-start").addEventListener("click", async () => {
    const statusRes = await fetch('/api/status');
    const statusData = await statusRes.json();
    if (statusData.is_running && statusData.is_paused) {
        // Bot is paused, resume instead of start
        await fetch('/api/bot/pause', { method: 'POST' });
    } else {
        const res = await fetch('/api/bot/start', { method: 'POST' });
        const data = await res.json();
        if (!data.ok) alert('Cannot start bot: ' + (data.error || 'Unknown error'));
    }
    fetchStatus();
  });

  document.getElementById("btn-pause").addEventListener("click", async () => {
    await fetch("/api/bot/pause", { method: "POST" });
    fetchStatus();
  });

  document.getElementById("btn-stop").addEventListener("click", async () => {
    await fetch("/api/bot/stop", { method: "POST" });
    fetchStatus();
  });

  document.getElementById("btn-reset-stats").addEventListener("click", async () => {
    if (confirm("Reset session statistics counters?")) {
      await fetch("/api/bot/reset", { method: "POST" });
      fetchStatus();
    }
  });

  document.getElementById("btn-scan").addEventListener("click", fetchDevices);

  document.getElementById("btn-connect").addEventListener("click", async () => {
    const addr = document.getElementById("connect-addr").value.trim();
    if (!addr) return;
    const res = await fetch("/api/devices/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: addr })
    });
    const data = await res.json();
    alert(data.message || (data.ok ? "Connected!" : "Connection failed"));
    fetchDevices();
  });

  document.getElementById("device-select").addEventListener("change", async (e) => {
    const serial = e.target.value;
    if (!serial) return;
    await fetch("/api/devices/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serial })
    });
    fetchStatus();
  });
}

async function fetchDevices() {
  try {
    const res = await fetch("/api/devices");
    const data = await res.json();
    const sel = document.getElementById("device-select");
    sel.innerHTML = "";
    if (data.devices && data.devices.length > 0) {
      data.devices.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.serial;
        opt.textContent = `${d.serial} (${d.state})`;
        sel.appendChild(opt);
      });
    } else {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No devices detected";
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error("Failed to list devices:", e);
  }
}

// ----------------------------------------------------------------------------
// Screen Tools & Display
// ----------------------------------------------------------------------------
function setupScreenTools() {
  document.getElementById("chk-overlay").addEventListener("change", refreshScreenImage);

  document.getElementById("btn-grab").addEventListener("click", async () => {
    const res = await fetch("/api/screen/grab", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      refreshScreenImage();
    } else {
      alert("Grab failed: " + (data.error || ""));
    }
  });

  document.getElementById("btn-test-ocr").addEventListener("click", async () => {
    const res = await fetch("/api/test/ocr", { method: "POST" });
    const data = await res.json();
    if (data.ok && data.loot) {
      const l = data.loot;
      const g = l.gold >= 0 ? l.gold.toLocaleString() : "UNREAD";
      const e = l.elixir >= 0 ? l.elixir.toLocaleString() : "UNREAD";
      const d = l.dark >= 0 ? l.dark.toLocaleString() : "UNREAD";
      alert(`Scouted Base Loot:\n\n• Gold: ${g}\n• Elixir: ${e}\n• Dark Elixir: ${d}`);
    } else {
      alert("OCR test failed: " + (data.error || ""));
    }
  });

  document.getElementById("btn-test-buttons").addEventListener("click", async () => {
    const res = await fetch("/api/test/buttons", { method: "POST" });
    const data = await res.json();
    if (data.ok && data.matches) {
      const keys = Object.keys(data.matches);
      if (keys.length === 0) {
        alert("No loaded button templates matched the current screen.");
      } else {
        const lines = keys.map(k => `• ${k} (score: ${data.matches[k].score.toFixed(2)})`);
        alert("Visible Buttons Found on Screen:\n\n" + lines.join("\n"));
      }
    } else {
      alert("Button scan failed: " + (data.error || ""));
    }
  });

  document.getElementById("btn-emergency-return").addEventListener("click", async () => {
    const res = await fetch("/api/emergency/return_home", { method: "POST" });
    const data = await res.json();
    alert(data.message || "Signal sent");
  });
}

function refreshScreenImage() {
  const overlay = document.getElementById("chk-overlay").checked ? "1" : "0";
  const img = document.getElementById("screen-img");
  img.src = `/api/screen.png?overlay=${overlay}&t=${Date.now()}`;
}

// ----------------------------------------------------------------------------
// Template Studio & Calibration
// ----------------------------------------------------------------------------
async function fetchTemplates() {
  try {
    const res = await fetch("/api/templates");
    const data = await res.json();
    if (!data.ok) return;

    // Populate buttons list
    const btnContainer = document.getElementById("templates-container");
    btnContainer.innerHTML = "";
    const tpls = data.templates || {};

    BUTTON_METADATA.forEach(meta => {
      const st = tpls[meta.key] || {};
      const exists = !!st.exists;
      const imgPath = st.path ? '/' + st.path.replace(/\\/g, '/') : '';
      const thumbHtml = exists
        ? `<img src="${imgPath}?t=${Date.now()}" style="height:38px; max-width:70px; object-fit:contain; border-radius:4px; border:1px solid var(--border); background:#111; margin-right:12px;" title="${meta.name} preview" alt="${meta.name}" />`
        : `<div style="width:38px; height:38px; border-radius:4px; border:1px dashed var(--border); display:flex; align-items:center; justify-content:center; margin-right:12px; font-size:0.8rem; color:var(--text-muted);">?</div>`;

      const row = document.createElement("div");
      row.className = "template-item";
      row.innerHTML = `
        <div style="display:flex; align-items:center;">
          ${thumbHtml}
          <div>
            <div style="font-weight:700; color:var(--text-primary); display:flex; align-items:center; gap:8px;">
              ${meta.name}
              <span class="${exists ? 'badge-ready' : 'badge-missing'}">
                ${exists ? 'Ready' : 'Missing'}
              </span>
              ${st.size ? `<span style="font-size:0.75rem; font-weight:normal; color:var(--text-muted);">(${st.size[0]}×${st.size[1]}px)</span>` : ''}
            </div>
            <div style="font-size:0.8rem; color:var(--text-muted);">${meta.desc}</div>
          </div>
        </div>
        <button class="btn-secondary" style="padding:4px 10px; font-size:0.85rem;" onclick="openCropModal('${meta.key}', 'button', '${meta.name}')">
          Crop
        </button>
      `;
      btnContainer.appendChild(row);
    });

    // Populate digits (0-9)
    const digitsContainer = document.getElementById("digits-container");
    digitsContainer.innerHTML = "";
    const digits = data.digits || {};

    for (let d = 0; d < 10; d++) {
      const ch = String(d);
      const exists = !!digits[ch];
      const digitThumbHtml = exists
        ? `<img src="/assets/digits/${ch}.png?t=${Date.now()}" style="height:28px; width:28px; object-fit:contain; margin:4px auto; display:block; filter:invert(1);" alt="${ch}" />`
        : `<div style="height:28px; width:28px; margin:4px auto; display:flex; align-items:center; justify-content:center; color:var(--danger); font-size:1.2rem;">?</div>`;

      const card = document.createElement("div");
      card.className = "digit-card";
      card.innerHTML = `
        <div style="font-weight:700; color:${exists ? 'var(--text-primary)' : 'var(--danger)'};">'${ch}'</div>
        ${digitThumbHtml}
        <div style="font-size:0.75rem; color:${exists ? 'var(--success)' : 'var(--danger)'};">${exists ? 'Ready' : 'Missing'}</div>
        <button class="btn-secondary" style="padding:2px 6px; font-size:0.75rem; margin-top:4px;" onclick="openCropModal('${ch}', 'digit', 'Digit ${ch}')">
          Crop
        </button>
      `;
      digitsContainer.appendChild(card);
    }
  } catch (err) {
    console.error("Failed to fetch templates:", err);
  }
}

// ----------------------------------------------------------------------------
// Interactive Canvas Crop Modal
// ----------------------------------------------------------------------------
function setupCropModal() {
  const modal = document.getElementById("crop-modal");
  const canvas = document.getElementById("crop-canvas");
  const ctx = canvas.getContext("2d");

  let isDrawing = false;
  let startX = 0, startY = 0;
  let imgObj = new Image();

  window.openCropModal = (targetKey, targetType, title) => {
    currentCropTarget = { name: targetKey, type: targetType };
    cropCoords = null;
    document.getElementById("modal-crop-title").textContent = `Crop: ${title}`;
    document.getElementById("modal-crop-coords").textContent = "Selected: None";
    document.getElementById("btn-modal-save").disabled = true;

    imgObj = new Image();
    imgObj.crossOrigin = "anonymous";
    imgObj.onload = () => {
      canvas.width = imgObj.naturalWidth || 1280;
      canvas.height = imgObj.naturalHeight || 720;
      ctx.drawImage(imgObj, 0, 0);
      modal.classList.add("open");
    };
    imgObj.src = `/api/screen.png?overlay=0&t=${Date.now()}`;
  };

  document.getElementById("btn-modal-close").addEventListener("click", () => modal.classList.remove("open"));
  document.getElementById("btn-modal-cancel").addEventListener("click", () => modal.classList.remove("open"));

  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    startX = (e.clientX - rect.left) * scaleX;
    startY = (e.clientY - rect.top) * scaleY;
    isDrawing = true;
  });

  canvas.addEventListener("mousemove", (e) => {
    if (!isDrawing) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const curX = (e.clientX - rect.left) * scaleX;
    const curY = (e.clientY - rect.top) * scaleY;

    ctx.drawImage(imgObj, 0, 0);
    ctx.strokeStyle = "#00ffcc";
    ctx.lineWidth = 3;
    ctx.strokeRect(startX, startY, curX - startX, curY - startY);
  });

  canvas.addEventListener("mouseup", (e) => {
    if (!isDrawing) return;
    isDrawing = false;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const endX = (e.clientX - rect.left) * scaleX;
    const endY = (e.clientY - rect.top) * scaleY;

    const x = Math.min(startX, endX);
    const y = Math.min(startY, endY);
    const w = Math.abs(endX - startX);
    const h = Math.abs(endY - startY);

    if (w > 4 && h > 4) {
      cropCoords = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];
      document.getElementById("modal-crop-coords").textContent = `Selected: ${cropCoords[2]}x${cropCoords[3]}px @ (${cropCoords[0]}, ${cropCoords[1]})`;
      document.getElementById("btn-modal-save").disabled = false;
    }
  });

  document.getElementById("btn-modal-save").addEventListener("click", async () => {
    if (!cropCoords || !currentCropTarget) return;

    const res = await fetch("/api/templates/crop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: currentCropTarget.name,
        type: currentCropTarget.type,
        roi: cropCoords
      })
    });
    const data = await res.json();
    if (data.ok) {
      alert(data.message || "Template saved successfully!");
      modal.classList.remove("open");
      fetchTemplates();
      fetchConfig();
    } else {
      alert("Failed to save crop: " + (data.error || ""));
    }
  });

  document.getElementById("btn-calibrate-gold").addEventListener("click", () => {
    openCropModal("gold", "loot_box", "Gold Loot Number Region");
  });

  document.getElementById("btn-save-boxes").addEventListener("click", async () => {
    try {
      const g = JSON.parse(document.getElementById("box-gold").value);
      const e = JSON.parse(document.getElementById("box-elixir").value);
      const d = JSON.parse(document.getElementById("box-dark").value);
      if (!currentConfig) await fetchConfig();
      if (!currentConfig.vision) currentConfig.vision = {};
      currentConfig.vision.loot_boxes = { gold: g, elixir: e, dark: d };

      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: currentConfig })
      });
      const data = await res.json();
      alert(data.message || (data.ok ? "Loot boxes saved!" : "Save failed"));
      refreshScreenImage();
    } catch (err) {
      alert("Invalid JSON format in loot boxes: " + err);
    }
  });
}

// ----------------------------------------------------------------------------
// Settings
// ----------------------------------------------------------------------------
async function fetchConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    if (!data.ok || !data.config) return;
    currentConfig = data.config;

    const f = currentConfig.farming || {};
    const t = currentConfig.timing || {};
    const v = currentConfig.vision || {};

    document.getElementById("cfg-min-gold").value = f.min_gold || 400000;
    document.getElementById("cfg-min-elixir").value = f.min_elixir || 400000;
    document.getElementById("cfg-min-dark").value = f.min_dark || 2000;
    document.getElementById("cfg-max-searches").value = f.max_searches || 60;
    document.getElementById("cfg-surrender").value = f.surrender_after_sec || 55;

    document.getElementById("cfg-collect").checked = f.collect_resources !== false;
    document.getElementById("cfg-train").checked = f.train_army !== false;
    document.getElementById("cfg-shield").checked = f.check_shield !== false;

    document.getElementById("cfg-min-tap").value = t.min_tap_delay || 0.4;
    document.getElementById("cfg-max-tap").value = t.max_tap_delay || 1.2;
    document.getElementById("cfg-jitter").value = t.jitter_px || 4;
    document.getElementById("cfg-break-interval").value = t.long_break_every_min || 45;
    document.getElementById("cfg-threshold").value = v.match_threshold || 0.82;

    const u = currentConfig.upgrades || {};
    if (document.getElementById("cfg-upg-enabled")) {
      document.getElementById("cfg-upg-enabled").checked = u.enabled !== false;
      document.getElementById("cfg-upg-bld").checked = u.upgrade_buildings !== false;
      document.getElementById("cfg-upg-hero").checked = u.upgrade_heroes !== false;
      document.getElementById("cfg-upg-lab").checked = u.upgrade_lab !== false;
      document.getElementById("cfg-upg-wall").checked = u.upgrade_walls !== false;
      document.getElementById("cfg-reserve-gold").value = u.reserve_gold || 200000;
      document.getElementById("cfg-reserve-elixir").value = u.reserve_elixir || 200000;
    }

    const lb = v.loot_boxes || {};
    if (lb.gold) document.getElementById("box-gold").value = JSON.stringify(lb.gold);
    if (lb.elixir) document.getElementById("box-elixir").value = JSON.stringify(lb.elixir);
    if (lb.dark) document.getElementById("box-dark").value = JSON.stringify(lb.dark);
  } catch (err) {
    console.error("Failed to load config:", err);
  }
}

function setupSettings() {
  document.getElementById("btn-save-settings").addEventListener("click", async () => {
    if (!currentConfig) return;
    const safeInt = (id, fallback) => {
        const v = parseInt(document.getElementById(id).value, 10);
        return isNaN(v) ? fallback : v;
    };
    const safeFloat = (id, fallback) => {
        const v = parseFloat(document.getElementById(id).value);
        return isNaN(v) ? fallback : v;
    };
    if (!currentConfig.farming) currentConfig.farming = {};
    if (!currentConfig.timing) currentConfig.timing = {};
    if (!currentConfig.vision) currentConfig.vision = {};
    if (!currentConfig.upgrades) currentConfig.upgrades = {};

    currentConfig.farming.min_gold = safeInt("cfg-min-gold", 400000);
    currentConfig.farming.min_elixir = safeInt("cfg-min-elixir", 400000);
    currentConfig.farming.min_dark = safeInt("cfg-min-dark", 2000);
    currentConfig.farming.max_searches = safeInt("cfg-max-searches", 60);
    currentConfig.farming.surrender_after_sec = safeInt("cfg-surrender", 55);

    currentConfig.farming.collect_resources = document.getElementById("cfg-collect").checked;
    currentConfig.farming.train_army = document.getElementById("cfg-train").checked;
    currentConfig.farming.check_shield = document.getElementById("cfg-shield").checked;

    currentConfig.timing.min_tap_delay = safeFloat("cfg-min-tap", 0.4);
    currentConfig.timing.max_tap_delay = safeFloat("cfg-max-tap", 1.2);
    currentConfig.timing.jitter_px = safeInt("cfg-jitter", 4);
    currentConfig.timing.long_break_every_min = safeInt("cfg-break-interval", 45);
    currentConfig.vision.match_threshold = safeFloat("cfg-threshold", 0.82);

    if (document.getElementById("cfg-upg-enabled")) {
      currentConfig.upgrades.enabled = document.getElementById("cfg-upg-enabled").checked;
      currentConfig.upgrades.upgrade_buildings = document.getElementById("cfg-upg-bld").checked;
      currentConfig.upgrades.upgrade_heroes = document.getElementById("cfg-upg-hero").checked;
      currentConfig.upgrades.upgrade_lab = document.getElementById("cfg-upg-lab").checked;
      currentConfig.upgrades.upgrade_walls = document.getElementById("cfg-upg-wall").checked;
      currentConfig.upgrades.reserve_gold = safeInt("cfg-reserve-gold", 200000);
      currentConfig.upgrades.reserve_elixir = safeInt("cfg-reserve-elixir", 200000);
    }

    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: currentConfig })
    });
    const data = await res.json();
    alert(data.message || (data.ok ? "Settings saved and reloaded!" : "Save error"));
  });
}

// ----------------------------------------------------------------------------
// Activity Logs
// ----------------------------------------------------------------------------
function setupLogs() {
  document.getElementById("btn-clear-logs").addEventListener("click", async () => {
    document.getElementById("log-console").innerHTML = "";
    try {
      await fetch("/api/logs/clear", { method: "POST" });
    } catch (e) {
      console.error("Failed to clear server logs:", e);
    }
  });

  document.getElementById("btn-copy-logs").addEventListener("click", () => {
    const text = document.getElementById("log-console").innerText;
    navigator.clipboard.writeText(text).then(() => {
      alert("Logs copied to clipboard!");
    });
  });
}

async function fetchLogs() {
  try {
    const res = await fetch("/api/logs");
    const data = await res.json();
    if (!data.ok || !data.logs) return;

    const consoleBox = document.getElementById("log-console");
    const atBottom = consoleBox.scrollHeight - consoleBox.scrollTop <= consoleBox.clientHeight + 40;

    consoleBox.innerHTML = "";
    data.logs.forEach(entry => {
      const line = document.createElement("div");
      line.className = `log-line log-${entry.level}`;
      line.textContent = `${entry.time} [${entry.level}] ${entry.message}`;
      consoleBox.appendChild(line);
    });

    if (atBottom) {
      consoleBox.scrollTop = consoleBox.scrollHeight;
    }
  } catch (err) {
    console.debug("Failed to fetch logs:", err);
  }
}
