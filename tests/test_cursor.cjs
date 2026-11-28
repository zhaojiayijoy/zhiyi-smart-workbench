const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../static-web/assets/js/cursor.js'), 'utf8');

function environment({ enabled = false, reduce = false, fine = true } = {}) {
  function target() {
    const listeners = new Map();
    return {
      listeners,
      addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(fn); },
      removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
      emit(type, event = {}) { for (const fn of [...(listeners.get(type) || [])]) fn(event); }
    };
  }
  function element() {
    const classes = new Set();
    return Object.assign(target(), {
      classList: { add: (...names) => names.forEach(n => classes.add(n)),
        remove: (...names) => names.forEach(n => classes.delete(n)),
        contains: name => classes.has(name),
        toggle(name, on) { if (on) classes.add(name); else classes.delete(name); } },
      style: { setProperty() {}, removeProperty() {} },
      setAttribute() {}, remove() { nodes.delete(this); },
      getBoundingClientRect: () => ({ left: 0, top: 0, right: 100, bottom: 100 }),
      closest: () => null
    });
  }
  const nodes = new Set(), frames = new Map(), cards = [], controls = { lookCursor: element() };
  const media = [Object.assign(target(), { matches: fine }), Object.assign(target(), { matches: reduce })];
  let nextFrame = 0, observer;
  const document = Object.assign(target(), { hidden: false, readyState: 'complete',
    documentElement: element(), body: { appendChild(el) { nodes.add(el); } },
    hasFocus: () => true, createElement: element, querySelectorAll: () => cards,
    getElementById: id => controls[id] || null });
  const window = Object.assign(target(), {
    matchMedia: query => query.includes('reduced') ? media[1] : media[0],
    requestAnimationFrame(fn) { const id = ++nextFrame; frames.set(id, fn); return id; },
    cancelAnimationFrame(id) { frames.delete(id); }, MutationObserver: true
  });
  const store = new Map(enabled ? [['edu.cursor', 'on']] : []);
  class MutationObserver {
    constructor(fn) { this.fn = fn; observer = this; }
    observe() { this.active = true; }
    disconnect() { this.active = false; }
  }
  vm.runInNewContext(source, { window, document, MutationObserver,
    localStorage: { getItem: key => store.get(key) || null, setItem: (key, value) => store.set(key, value) } });
  function flush() {
    let count = 0;
    while (frames.size && count < 200) {
      const current = [...frames.values()]; frames.clear();
      current.forEach(fn => fn()); count++;
    }
    assert.equal(frames.size, 0, 'animation must converge while stationary');
    return count;
  }
  function move(x = 40, y = 40, el = element()) { document.emit('mousemove', { clientX: x, clientY: y, target: el }); }
  return { window, document, media, nodes, frames, cards, controls, store, flush, move, element,
    mutate() { observer.fn(); }, observer: () => observer };
}

test('effects are opt-in and have no idle frames before first movement', () => {
  const e = environment();
  assert.equal(e.nodes.size, 0);
  assert.equal(e.frames.size, 0);
  e.window.EduCursor.setEnabled(true);
  assert.equal(e.nodes.size, 2);
  assert.equal(e.frames.size, 0);
  e.move();
  assert.ok(e.flush() > 0);
  e.move(200, 300);
  assert.ok(e.flush() < 80);
});

test('dynamic reduced-motion and fine-pointer changes stop and restart cleanly', () => {
  const e = environment({ enabled: true, reduce: true });
  assert.equal(e.nodes.size, 0);
  assert.equal(e.controls.lookCursor.disabled, true);
  e.media[1].matches = false; e.media[1].emit('change');
  assert.equal(e.nodes.size, 2);
  e.media[0].matches = false; e.media[0].emit('change');
  assert.equal(e.nodes.size, 0);
  e.media[0].matches = true; e.media[0].emit('change');
  e.move();
  assert.equal(e.frames.size, 1);
  e.media[1].matches = true; e.media[1].emit('change');
  assert.equal(e.nodes.size, 0);
  assert.equal(e.frames.size, 0);
  assert.equal(e.document.listeners.get('mousemove').size, 0);
});

test('repeated toggles remove all active listeners and observers', () => {
  const e = environment({ enabled: true });
  for (let i = 0; i < 10; i++) {
    e.window.EduCursor.setEnabled(false);
    for (const set of e.document.listeners.values()) assert.equal(set.size, 0);
    for (const type of ['blur', 'focus', 'resize']) assert.equal(e.window.listeners.get(type).size, 0);
    assert.equal(e.observer().active, false);
    e.window.EduCursor.setEnabled(true);
    assert.equal(e.document.listeners.get('mouseout').size, 1);
    assert.equal(e.window.listeners.get('resize').size, 1);
    assert.equal(e.nodes.size, 2);
  }
});

test('blur, hidden pages, keyboard focus and native text zones cancel frames', () => {
  const e = environment({ enabled: true });
  e.move(); e.window.emit('blur');
  assert.equal(e.frames.size, 0);
  e.move(); assert.equal(e.frames.size, 0);
  e.window.emit('focus'); e.move();
  e.document.hidden = true; e.document.emit('visibilitychange');
  assert.equal(e.frames.size, 0);
  e.document.hidden = false; e.document.emit('visibilitychange');
  assert.equal(e.frames.size, 0);
  e.move(); e.document.emit('keydown', { key: 'Tab' });
  assert.equal(e.frames.size, 0);
  e.move(); e.move(80, 80, { closest: () => ({ tagName: 'INPUT' }) });
  assert.equal(e.frames.size, 0);
  assert.equal(e.document.documentElement.classList.contains('tc-cursor-hidden'), true);
  const css = fs.readFileSync(path.join(__dirname, '../static-web/assets/css/site.css'), 'utf8');
  assert.ok(!/cursor\s*:\s*none/.test(css), 'native pointer must remain available');
});

test('new cards and scrolling update highlights without pointer movement', () => {
  const e = environment({ enabled: true });
  e.move(); e.flush();
  const card = e.element(); e.cards.push(card); e.mutate(); e.flush();
  assert.equal(card.classList.contains('is-spotlit'), true);
  card.getBoundingClientRect = () => ({ left: 900, top: 900, right: 1000, bottom: 1000 });
  e.document.emit('scroll'); e.flush();
  assert.equal(card.classList.contains('is-spotlit'), false);
  e.window.EduCursor.setEnabled(false);
  assert.equal(e.nodes.size, 0);
});

test('control and storage updates persist opt-in without duplicate startup', () => {
  const e = environment();
  e.controls.lookCursor.checked = true; e.controls.lookCursor.emit('change');
  assert.equal(e.store.get('edu.cursor'), 'on');
  e.window.emit('storage', { key: 'edu.cursor' });
  assert.equal(e.document.listeners.get('mousemove').size, 1);
  e.store.delete('edu.cursor'); e.window.emit('storage', { key: null });
  assert.equal(e.nodes.size, 0);
  assert.equal(e.controls.lookCursor.checked, false);
});
