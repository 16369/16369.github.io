const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../themes/default/assets/main.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
const response = data => ({ ok: true, json: () => Promise.resolve(data) });

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element(tag) {
  return {
    tag, children: [], hidden: true, textContent: '',
    appendChild(child) { this.children.push(child); },
    set innerHTML(value) { this.children = []; },
    querySelector(tagName) { return this.children.find(child => child.tag === tagName) || null; }
  };
}

function browser({ hostname = '16369.github.io', preview = false, fetch } = {}) {
  const events = {};
  const documentEvents = {};
  const results = element('div');
  const input = { value: '', blur() {}, addEventListener(name, callback) { events[name] = callback; } };
  const search = { getAttribute: () => '', contains: target => target === input };
  const intervals = new Map();
  const calls = [];
  let nextTimer = 0;
  let reloads = 0;
  const location = { protocol: 'https:', hostname, reload() { reloads++; } };
  const context = {
    document: {
      documentElement: { getAttribute: name => name === 'data-live-reload' && preview ? 'true' : null },
      getElementById: id => ({ 'search-input': input, 'search-results': results }[id] || null),
      querySelector: selector => selector === '.search' ? search : null,
      querySelectorAll: () => [],
      createElement: element,
      addEventListener(name, callback) { documentEvents[name] = callback; }
    },
    location, window: { location },
    setTimeout, clearTimeout,
    setInterval(callback, delay) { const id = ++nextTimer; intervals.set(id, { callback, delay }); return id; },
    clearInterval(id) { intervals.delete(id); },
    fetch(url, options) { calls.push(url); return fetch ? fetch(url, options) : Promise.resolve(response([])); }
  };
  vm.runInNewContext(source, context);
  return {
    input, results, events, documentEvents, intervals, calls, location,
    get reloads() { return reloads; },
    type(value) { input.value = value; events.input(); },
    tick() { for (const timer of intervals.values()) timer.callback(); }
  };
}

test('slow index renders the latest query when loading completes', async () => {
  const pending = deferred();
  const page = browser({ fetch: () => pending.promise });
  page.events.focus();
  page.type('old');
  page.type('new');
  assert.match(page.results.children[0].textContent, /正在搜索/);
  await settle();
  pending.resolve(response([{ title: 'old post', url: 'old.html' }, { title: 'new post', url: 'new.html' }]));
  await settle();
  assert.equal(page.calls.length, 1);
  assert.equal(page.results.hidden, false);
  assert.equal(page.results.children.length, 1);
  assert.equal(page.results.children[0].href, 'new.html');
});

for (const action of ['clear', 'escape', 'outside']) {
  test(`pending search stays closed after ${action}`, async () => {
    const pending = deferred();
    const page = browser({ fetch: () => pending.promise });
    page.type('hello');
    if (action === 'clear') page.type('');
    if (action === 'escape') page.events.keydown({ key: 'Escape' });
    if (action === 'outside') page.documentEvents.click({ target: {} });
    pending.resolve(response([{ title: 'hello', url: 'hello.html' }]));
    await settle();
    assert.equal(page.results.hidden, true);
    page.events.keydown({ key: 'Enter' });
    assert.equal(page.location.href, undefined);
  });
}

for (const failure of ['http', 'network', 'format']) {
  test(`search reports ${failure} failure and retries successfully`, async () => {
    let attempt = 0;
    const page = browser({ fetch: () => {
      if (attempt++ > 0) return Promise.resolve(response([{ title: 'hello', url: 'hello.html' }]));
      if (failure === 'http') return Promise.resolve({ ok: false });
      if (failure === 'format') return Promise.resolve(response({ invalid: true }));
      return Promise.reject(new Error('offline'));
    } });
    page.type('hello');
    await settle();
    assert.match(page.results.children[0].textContent, /暂时不可用/);
    page.type('hello');
    await settle();
    assert.equal(page.results.children[0].href, 'hello.html');
    page.events.keydown({ key: 'Enter' });
    assert.equal(page.location.href, 'hello.html');
  });
}

test('empty successful index displays no matches', async () => {
  const page = browser();
  page.type('hello');
  await settle();
  assert.match(page.results.children[0].textContent, /没有找到/);
});

test('production never polls, even if preview output was uploaded', () => {
  for (const preview of [false, true]) {
    const page = browser({ preview });
    page.tick();
    assert.equal(page.intervals.size, 0);
    assert.equal(page.calls.length, 0);
  }
});

test('localhost without preview mode does not poll', () => {
  const page = browser({ hostname: 'localhost' });
  assert.equal(page.intervals.size, 0);
});

test('preview reloads only after a version change', async () => {
  let version = '1';
  const page = browser({ hostname: '127.0.0.1', preview: true, fetch: () => Promise.resolve({ ok: true, text: () => Promise.resolve(version) }) });
  page.tick();
  await settle();
  page.tick();
  await settle();
  assert.equal(page.reloads, 0);
  version = '2';
  page.tick();
  await settle();
  assert.equal(page.reloads, 1);
});

test('preview stops polling after HTTP failure', async () => {
  const page = browser({ hostname: 'localhost', preview: true, fetch: () => Promise.resolve({ ok: false }) });
  page.tick();
  await settle();
  assert.equal(page.intervals.size, 0);
  page.tick();
  assert.deepEqual(page.calls, ['/__reload']);
});
