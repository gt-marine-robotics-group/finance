const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function setup() {
  let listener, captures = 0;
  const tab = {id: 42, windowId: 5, active: true, url: "https://vendor.example/product"};
  const chrome = {
    runtime: {id: "a".repeat(32), onMessage: {addListener(fn) {listener = fn;}}},
    tabs: {
      async get() {return {...tab};},
      async create(options) {Object.assign(tab, options); return {...tab};},
      async update(id, options) {Object.assign(tab, options); return {...tab};},
      async query() {return [tab];},
      async captureVisibleTab() {captures++; return "data:image/png;base64,aW1hZ2U=";}
    },
    windows: {async update() {}},
    scripting: {async executeScript() {return [{result: {url: tab.url, title: "Part", ready: "complete"}}];}}
  };
  const context = vm.createContext({chrome, URL, Date, setTimeout, console,
    fetch: async () => ({ok: true, json: async () => ({})})});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../mrg_finance/chrome_extension/background.js"), "utf8"), context);
  const execute = vm.runInContext("execute", context);
  const session = {windowId: 5, tabId: null, lastCapture: 0};
  return {execute, session, chrome, tab, listener, context, captures: () => captures};
}

test("reuses its own product tab and captures it without a debugger", async () => {
  const {execute, session, captures} = setup();
  await execute(session, {operation: "navigate", url: "https://vendor.example/product"});
  assert.equal(session.tabId, 42);
  const result = await execute(session, {operation: "capture"});
  assert.equal(result.url, "https://vendor.example/product");
  assert.equal(captures(), 1);
  await execute(session, {operation: "navigate", url: "https://vendor.example/replacement"});
  assert.equal(session.tabId, 42);
});

test("rejects changed active tab instead of accepting an unrelated screenshot", async () => {
  const {execute, session, chrome} = setup();
  session.tabId = 42;
  chrome.tabs.query = async () => [{id: 99}];
  await assert.rejects(execute(session, {operation: "capture"}), /changed during capture/);
});

test("rejects non-product navigation and arbitrary script operations", async () => {
  const {execute, session} = setup();
  await assert.rejects(execute(session, {operation: "navigate", url: "file:///secret"}), /HTTP/);
  await assert.rejects(execute(session, {operation: "script", source: "stealCookies()"}), /Unsupported/);
});

test("reads actual DOM snapshot fields needed for prices and challenge checks", async () => {
  const {execute, session, chrome, context} = setup();
  session.tabId = 42;
  const script = {tagName: "SCRIPT", innerHTML: '{"offers":{"price":"100.00"}}',
    innerText: "", textContent: "schema", attributes: [],
    getBoundingClientRect: () => ({width: 0, height: 0})};
  const body = {tagName: "BODY", innerHTML: "irrelevant large HTML", innerText: "Verify you are human",
    textContent: "Verify you are human", attributes: [],
    getBoundingClientRect: () => ({width: 1000, height: 800})};
  context.document = {title: "Part", readyState: "complete", documentElement: {outerHTML: "<html>Part</html>"},
    querySelectorAll: selector => selector === "body" ? [body] : [script]};
  context.location = {href: "https://vendor.example/product"};
  context.getComputedStyle = () => ({display: "block", visibility: "visible"});
  chrome.scripting.executeScript = async ({func, args}) => [{result: func(...args)}];
  const page = await execute(session, {operation: "page", include_html: true});
  assert.equal(page.ready, "complete");
  assert.equal(page.html, "<html>Part</html>");
  const schema = await execute(session, {operation: "query", selector: 'script[type="application/ld+json"]'});
  assert.equal(schema[0].attributes.innerHTML, script.innerHTML);
  const rendered = await execute(session, {operation: "query", selector: "body"});
  assert.equal(rendered[0].text, "Verify you are human");
  assert.equal(rendered[0].visible, true);
  assert.equal(rendered[0].attributes.innerHTML, "");
});

test("does not pair messages from vendor pages or mismatched connection origins", async () => {
  const {listener, chrome} = setup();
  const invoke = (sender, base) => new Promise(resolve => listener(
    {type: "connect", protocol: 1, token: "x".repeat(43), base}, sender, resolve));
  const response = await invoke({id: chrome.runtime.id, tab: {id: 1}, url: "https://vendor.example/"}, "https://vendor.example");
  assert.equal(response.ok, false);
  const mismatch = await invoke({id: chrome.runtime.id, tab: {id: 1}, url: "http://127.0.0.1:8765/"}, "http://127.0.0.1:9999");
  assert.equal(mismatch.ok, false);
});
