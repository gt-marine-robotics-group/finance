// Only this loopback connection page can pair a capture session.
const token = document.querySelector('meta[name="mrg-finance-token"]')?.content;
const protocol = Number(document.querySelector('meta[name="mrg-finance-protocol"]')?.content);
if (token && protocol === 1 && location.hostname === "127.0.0.1" && location.pathname === "/") {
  chrome.runtime.sendMessage({type: "connect", token, base: location.origin, protocol}, response => {
    const status = document.getElementById("status");
    if (status) status.textContent = response?.ok
      ? "Connected. Return to the Terminal; keep this tab open."
      : `Connection failed: ${response?.error || chrome.runtime.lastError?.message || "reload the extension"}`;
  });
}
