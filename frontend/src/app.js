// Vanilla JS on purpose. No build step means no node_modules in the image, no
// npm advisories cluttering the vulnerability scan, and a frontend container
// that is nginx plus three static files.
//
// The API is reached at a same-origin /api path. nginx proxies it to the
// backend, so the browser never learns the backend's address and there is no
// CORS preflight in the deployed setup.

// Link endpoints live under /api on the backend. The operational endpoints
// (/health, /ready, /version) deliberately do not — Kubernetes probes want them
// at the root, so they are reached here without the prefix and nginx passes
// them through unchanged.
const API = "/api";
const VERSION_URL = "/version";
const POLL_MS = 3000;

const $ = (id) => document.getElementById(id);

const form = $("shorten-form");
const targetInput = $("target-url");
const codeInput = $("custom-code");
const submitBtn = $("submit-btn");
const resultBox = $("result");
const shortLink = $("short-link");
const copyBtn = $("copy-btn");
const errorBox = $("error");
const recentBox = $("recent");
const recentList = $("recent-list");

const session = [];

// --- create ---------------------------------------------------------------

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hide(errorBox);
  submitBtn.disabled = true;
  submitBtn.textContent = "Shortening…";

  const body = { target_url: targetInput.value.trim() };
  const custom = codeInput.value.trim();
  if (custom) body.custom_code = custom;

  try {
    const response = await fetch(`${API}/links`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      // FastAPI's 422 detail is an array of field errors; a 409 is a plain
      // string. Handle both rather than rendering "[object Object]".
      throw new Error(formatDetail(payload.detail, response.status));
    }

    showResult(payload);
    remember(payload);
    form.reset();
  } catch (err) {
    show(errorBox, err.message || "Request failed");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Shorten";
  }
});

function formatDetail(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "input";
    return `${field}: ${first.msg}`;
  }
  return `Request failed (HTTP ${status})`;
}

function showResult(link) {
  // The backend builds short_url from BASE_URL, which is correct for the API's
  // own notion of itself but wrong when the browser reached us through an
  // ingress on a different hostname. Rebuild it against the current origin.
  const url = `${window.location.origin}/${link.code}`;
  shortLink.textContent = url;
  shortLink.href = url;
  show(resultBox);
}

copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(shortLink.textContent);
    copyBtn.textContent = "Copied";
  } catch {
    // Clipboard API needs a secure context; plain http on a LAN address will
    // reject it. Failing silently would look like a broken button.
    copyBtn.textContent = "Copy failed";
  }
  setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
});

function remember(link) {
  session.unshift(link);
  recentList.innerHTML = "";
  for (const item of session.slice(0, 8)) {
    const li = document.createElement("li");

    const a = document.createElement("a");
    a.href = `/${item.code}`;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = `/${item.code}`;

    const span = document.createElement("span");
    span.className = "target";
    // textContent, not innerHTML — the target URL is user input and this is
    // exactly where a stored-XSS bug would live.
    span.textContent = item.target_url;

    li.append(a, span);
    recentList.append(li);
  }
  show(recentBox);
}

// --- status bar -----------------------------------------------------------

const statusDot = $("status-dot");
const statusText = $("status-text");
const statusVersion = $("status-version");
const statusPod = $("status-pod");

let lastVersion = null;

async function poll() {
  try {
    const response = await fetch(VERSION_URL, { cache: "no-store" });
    if (!response.ok) throw new Error();
    const info = await response.json();

    statusDot.className = "dot up";
    statusText.textContent = "backend up";

    const version = `${info.version} (${info.git_sha.slice(0, 7)})`;
    if (lastVersion !== null && lastVersion !== version) {
      // A visible flash at the exact moment a rolling update swaps pods.
      statusVersion.classList.remove("changed");
      void statusVersion.offsetWidth; // force reflow so the animation restarts
      statusVersion.classList.add("changed");
    }
    lastVersion = version;

    statusVersion.textContent = version;
    statusPod.textContent = info.hostname;
  } catch {
    statusDot.className = "dot down";
    statusText.textContent = "backend unreachable";
  }
}

poll();
setInterval(poll, POLL_MS);

// --- helpers --------------------------------------------------------------

function show(el, text) {
  if (text !== undefined) el.textContent = text;
  el.hidden = false;
}

function hide(el) {
  el.hidden = true;
}
