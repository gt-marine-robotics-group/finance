let session = null;

async function request(s, path, value) {
  const response = await fetch(s.base + path, {
    method: value === undefined ? "GET" : "POST",
    headers: {Authorization: `Bearer ${s.token}`, "X-MRG-Extension": chrome.runtime.id},
    ...(value === undefined ? {} : {body: JSON.stringify(value)})
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `CLI connection returned ${response.status}`);
  return data;
}

async function productTab(s) {
  if (s.tabId === null) throw new Error("No product tab; rerun the screenshot command.");
  return chrome.tabs.get(s.tabId);
}

async function inPage(s, func, args = []) {
  await productTab(s);
  const results = await chrome.scripting.executeScript({target: {tabId: s.tabId}, func, args});
  if (results.length !== 1 || results[0].result === undefined) {
    throw new Error("Could not read the product page. Check extension site access and let the page load.");
  }
  return results[0].result;
}

async function execute(s, command) {
  switch (command.operation) {
    case "navigate": {
      const url = new URL(command.url);
      if (!["https:", "http:"].includes(url.protocol)) throw new Error("Product URL must use HTTP(S)");
      if (s.tabId === null) {
        const tab = await chrome.tabs.create({windowId: s.windowId, url: url.href, active: true});
        s.tabId = tab.id;
      } else {
        await chrome.tabs.update(s.tabId, {url: url.href, active: true});
      }
      const tab = await productTab(s);
      await chrome.windows.update(tab.windowId, {focused: true});
      return null;
    }
    case "page":
      return inPage(s, includeHTML => ({url: location.href, title: document.title,
        ready: document.readyState, html: includeHTML ? document.documentElement.outerHTML : ""}),
      [Boolean(command.include_html)]);
    case "query":
      return inPage(s, selector => Array.from(document.querySelectorAll(selector)).slice(0, 200).map(element => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const attributes = Object.fromEntries(Array.from(element.attributes, a => [a.name, a.value]));
        attributes.innerHTML = element.tagName === "SCRIPT" ? element.innerHTML : "";
        attributes.innerText = element.innerText || "";
        attributes.textContent = element.textContent || "";
        return {text: element.innerText || "", attributes,
          visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0};
      }), [command.selector]);
    case "capture": {
      const tab = await productTab(s);
      await chrome.tabs.update(tab.id, {active: true});
      await chrome.windows.update(tab.windowId, {focused: true});
      // Avoid Chrome's two-captures-per-second limit on challenge/retry captures.
      await new Promise(resolve => setTimeout(resolve, Math.max(0, 600 - (Date.now() - s.lastCapture))));
      const before = await chrome.tabs.get(tab.id);
      const image = await chrome.tabs.captureVisibleTab(tab.windowId, {format: "png"});
      s.lastCapture = Date.now();
      const after = await chrome.tabs.get(tab.id);
      const active = await chrome.tabs.query({windowId: tab.windowId, active: true});
      if (active.length !== 1 || active[0].id !== tab.id || !before.active || before.url !== after.url) {
        throw new Error("The product tab changed during capture. Leave it visible and retry.");
      }
      return {image, url: after.url};
    }
    default:
      throw new Error("Unsupported evidence operation");
  }
}

async function poll(s) {
  while (session === s) {
    try {
      // This checks the connection tab remains open and keeps the MV3 worker active.
      await chrome.tabs.get(s.connectionTabId);
      const command = await request(s, "/command");
      if (!command) continue;
      let result;
      try {
        result = {id: command.id, ok: true, value: await execute(s, command)};
      } catch (error) {
        result = {id: command.id, ok: false, error: error.message};
      }
      await request(s, "/result", result);
    } catch (error) {
      if (session === s) session = null;
      break; // CLI has finished, or the connection tab was closed. No background retries.
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type !== "connect" || !sender.tab || sender.id !== chrome.runtime.id) return;
  (async () => {
    const url = new URL(sender.url);
    if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || url.pathname !== "/"
        || message.base !== url.origin || message.protocol !== 1 || !/^[A-Za-z0-9_-]{40,60}$/.test(message.token)) {
      throw new Error("Invalid CLI connection page");
    }
    if (session && (session.base !== message.base || session.token !== message.token)) {
      throw new Error("Another screenshot session is connected. Finish it before connecting this one.");
    }
    if (!session) {
      const s = {base: message.base, token: message.token, windowId: sender.tab.windowId,
        connectionTabId: sender.tab.id, tabId: null, lastCapture: 0};
      await request(s, "/connect", {protocol: 1});
      session = s;
      poll(s);
    }
    respond({ok: true});
  })().catch(error => respond({ok: false, error: error.message}));
  return true;
});
