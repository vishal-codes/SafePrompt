const MENU_ID = "safeprompt-redact";
const API_URL = "http://127.0.0.1:8000/redact";

// Create context menu on install/update; restrict to normal web pages
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Redact with SafePrompt",
    contexts: ["selection"],
    documentUrlPatterns: ["http://*/*", "https://*/*"]
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
    const safe = await callApi(selected);
    const copied = await copyViaInjection(tab.id, safe);
    if (copied) {
      await showAlert(tab.id, "SafePrompt: copied to clipboard ✅");
      log("Copied ok.");
    } else {
      log("Injection blocked; opening result in a new tab.");
      openResultTab(safe);
    }
  } catch (err) {
    log("Error:", err?.message || String(err));
  }
});

async function callApi(text) {
  const res = await fetch(API_URL, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ text })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.text();
  // Ensure exactly one pair of tags
  const inner = body.replaceAll("<safe>", "").replaceAll("</safe>", "").trim();
  return inner
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
        } catch (e) {
          return false;
        }
      }
    });
    return !!result;
  } catch (e) {
    // Injection fails on restricted pages (chrome://, store, pdf viewer, etc.)
    return false;
  }
}

async function showAlert(tabId, msg) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      args: [msg],
      func: (m) => alert(m)
    });
  } catch (e) {
    // ignore if alerts are blocked
  }
}

function openResultTab(safeText) {
  const url = "data:text/plain;charset=utf-8," + encodeURIComponent(safeText);
  chrome.tabs.create({ url });
}

function log(...args) {
  console.log("[SafePrompt]", ...args);
}

