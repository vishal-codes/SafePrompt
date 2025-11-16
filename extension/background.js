// background.js
const MENU_ID = "safeprompt-redact";
const API_URL = "http://127.0.0.1:8000/redact";

// Create context menu on install/update; restrict to normal web pages
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Redact with SafePrompt",
    contexts: ["selection"],
    documentUrlPatterns: ["http://*/*", "https://*/*"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  const selected = (info.selectionText || "").trim();
  if (!selected) {
    log("No selection.");
    return;
  }

  try {
    // Call backend and get the redacted text (without <safe> tags)
    const { redacted, placeholders, latency } = await callApi(selected);
    const copied = await copyViaInjection(tab.id, redacted);
    if (copied) {
      const extra = placeholders.length
        ? ` (${placeholders.length} placeholder${placeholders.length === 1 ? "" : "s"})`
        : "";
      await showAlert(tab.id, `SafePrompt: copied to clipboard ✅${extra}`);
      log(`Copied ok. latency=${latency}ms, placeholders=`, placeholders);
    } else {
      log("Injection blocked; opening result in a new tab.");
      openResultTab(redacted);
    }
  } catch (err) {
    log("Error:", err?.message || String(err));
    if (tab?.id) {
      try { await showAlert(tab.id, "SafePrompt: redaction failed ❌"); } catch {}
    }
  }
});

async function callApi(text) {
  const res = await fetch(API_URL, {
    method: "POST",
    mode: "cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  let data;
  const ctype = (res.headers.get("content-type") || "").toLowerCase();
  if (ctype.includes("application/json")) {
    data = await res.json();
    if (!data || typeof data.redacted_text !== "string") {
      throw new Error("Invalid JSON shape from backend");
    }
    return {
      redacted: data.redacted_text,
      placeholders: Array.isArray(data.placeholders) ? data.placeholders : [],
      latency: typeof data.latency_ms === "number" ? data.latency_ms : null,
    };
  } else {
    const body = await res.text();
    const inner = body.replaceAll("<safe>", "").replaceAll("</safe>", "").trim();
    return { redacted: inner, placeholders: [], latency: null };
  }
}

async function copyViaInjection(tabId, text) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      args: [text],
      func: (clipText) => {
        try {
          const ta = document.createElement("textarea");
          ta.value = clipText;
          ta.setAttribute("readonly", "");
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          const ok = document.execCommand("copy");
          ta.remove();
          return !!ok;
        } catch {
          return false;
        }
      },
    });
    return !!result;
  } catch {
    return false;
  }
}

async function showAlert(tabId, msg) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      args: [msg],
      func: (m) => alert(m),
    });
  } catch {
    // ignore if alerts are blocked
  }
}

function openResultTab(text) {
  const url = "data:text/plain;charset=utf-8," + encodeURIComponent(text);
  chrome.tabs.create({ url });
}

function log(...args) {
  console.log("[SafePrompt]", ...args);
}
