const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const source = name => fs.readFileSync(path.join(root, 'static-web/assets/js', name), 'utf8');

test('login opens directly with student-number initial password guidance', () => {
  const login = fs.readFileSync(path.join(root, 'static-web/login.html'), 'utf8');
  assert.doesNotMatch(login, /loginIntro|login-intro\.mp4|管理员配置|教师分配|激活密码/);
  assert.match(login, /学生初始密码为学号后 6 位/);
  assert.match(login, /userEl\.focus\(\)/);
});

function apiContext(port = '8701') {
  const calls = [];
  const context = {window: {}, location: {hostname: '127.0.0.1', port,
    protocol: 'http:', origin: `http://127.0.0.1:${port}`},
    URLSearchParams,
    localStorage: {getItem: key => key === 'edu.token' ? 'test-token' : null},
    fetch: async (url, options) => {
      calls.push({url, options});
      return {ok: true, text: async () => JSON.stringify({ok: true, items: []})};
    }};
  vm.runInNewContext(source('api.js'), context);
  return {api: context.window.EduAPI, calls};
}

test('rehearsal client uses configured origin and authorization on every call', async () => {
  const {api, calls} = apiContext();
  await api.rehearsals.list(12);
  await api.rehearsals.get(5);
  await api.rehearsals.create({courseId: 12});
  await api.rehearsals.demo({courseId: 12});
  await api.rehearsals.patch(5, 'patch/1', 'apply');
  assert.equal(calls.length, 5);
  for (const call of calls) {
    assert.ok(call.url.startsWith('http://127.0.0.1:8701/api/rehearsals'));
    assert.equal(call.options.headers.Authorization, 'Bearer test-token');
  }
  assert.match(calls[4].url, /patch%2F1\/apply$/);
  assert.equal(JSON.parse(calls[3].options.body).courseId, 12);
  await assert.rejects(api.rehearsals.patch(5, 'p', 'delete'));
});

test('separate static preview retains API port mapping', () => {
  assert.equal(apiContext('8765').api.base, 'http://127.0.0.1:8700/api');
});

test('student overview accepts safe pagination arguments', async () => {
  const {api, calls} = apiContext();
  await api.student.overview(7, 50, 25);
  assert.equal(calls[0].url, 'http://127.0.0.1:8701/api/student/overview?offset=50&limit=25&project_id=7');
});

test('demo button uses demo service and escapes model content', async () => {
  const nodes = new Map();
  const listeners = {};
  const notices = [];
  const poison = '<img src=x onerror="alert(1)">';
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML: '', textContent: '', style: {},
      classList: {add() {}, remove() {}}, addEventListener() {}});
    return nodes.get(selector);
  };
  const session = {id: 7, course_id: 12, status: 'completed', is_demo: true,
    personas: ['novice'], timeline: [{stageId: 's', name: poison, objective: poison, minutes: 5}],
    events: [{stageId: 's', personaId: 'novice', content: poison, evidence: poison,
      teacherRisk: poison, suggestedResponse: poison}],
    risks: [{title: poison, level: poison, type: poison, evidence: poison, impact: poison, patches: [poison]}],
    patches: [{patchId: poison, targetArtifact: poison, targetSection: poison,
      reason: poison, before: poison, after: poison, status: 'pending'}],
    summary: {topWeakKnowledgePoint: poison, largestTimeRiskStage: poison}};
  let demos = 0;
  const API = {notify: msg => notices.push(msg), rehearsals: {
    demo: async () => { demos++; return {ok: true, id: 7}; },
    create: async () => { throw new Error('Real model path must not run'); },
    get: async () => ({ok: true, item: session}),
    list: async () => ({ok: true, items: []})}};
  const Edu = {isLive: () => false, getSelectedCourse: () => ({id: 12}), onCourseChange() {}};
  const document = {readyState: 'complete',
    querySelector: selector => selector === '#rhHistory .rh-history-item' ? null : node(selector),
    querySelectorAll: () => [],
    addEventListener: (name, fn) => { listeners[name] = fn; }};
  vm.runInNewContext(source('rehearsal.js'), {window: {EduAPI: API, Edu}, EduAPI: API, Edu, document,
    setTimeout, clearTimeout, console});
  listeners.click({target: {closest: () => ({id: 'rhDemo'})}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(demos, 1);
  for (const selector of ['#rhTimeline', '#rhRisks', '#rhPatches', '#rhSum']) {
    assert.ok(!node(selector).innerHTML.includes('<img'), selector);
    assert.ok(node(selector).innerHTML.includes('&lt;img'), selector);
  }
  assert.ok(!node('#rhPatches').innerHTML.includes('data-action="apply"'));
  assert.ok(notices.length > 0);
});

test('switching courses clears results and ignores delayed lesson responses', async () => {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML: '', textContent: '', style: {},
      classList: {add() {}, remove() {}}, addEventListener() {}});
    return nodes.get(selector);
  };
  let selected = {id: 12, name: 'Course A'};
  let change;
  let resolveOld;
  const calls = [];
  const oldLessons = new Promise(resolve => { resolveOld = resolve; });
  const API = {notify() {}, tasks: {list: id => id === 12 ? oldLessons : Promise.resolve([])},
    rehearsals: {list: async id => { calls.push(id); return {ok: true, items: []}; }}};
  const Edu = {isLive: () => true, getSelectedCourse: () => selected,
    onCourseChange: fn => { change = fn; }};
  const document = {readyState: 'complete', querySelector: node, querySelectorAll: () => [],
    addEventListener() {}};
  vm.runInNewContext(source('rehearsal.js'), {window: {EduAPI: API, Edu}, EduAPI: API, Edu, document,
    setTimeout, clearTimeout, console});
  node('#rhTimeline').innerHTML = 'OLD_RESULT';
  selected = {id: 13, name: 'Course B'};
  await change();
  resolveOld([{prompt: 'OLD_LESSON'}]);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(node('#rhTimeline').innerHTML, '');
  assert.ok(!node('#rhLessonPkg').textContent.includes('OLD_LESSON'));
  assert.deepEqual(calls, [13]);
  assert.equal(node('#rhProgressWrap').style.display, 'none');
});

test('late demo result does not reopen a previous course', async () => {
  const nodes = new Map();
  const listeners = {};
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML: '', textContent: '', style: {},
      addEventListener() {}});
    return nodes.get(selector);
  };
  let selected = {id: 12};
  let finish;
  let reads = 0;
  const API = {notify() {}, rehearsals: {demo: () => new Promise(resolve => { finish = resolve; }),
    get: async () => { reads++; throw Error('Stale detail should not be loaded'); }}};
  const Edu = {isLive: () => false, getSelectedCourse: () => selected, onCourseChange() {}};
  const document = {readyState: 'complete', querySelector: node, querySelectorAll: () => [],
    addEventListener: (event, fn) => { listeners[event] = fn; }};
  vm.runInNewContext(source('rehearsal.js'), {window: {EduAPI: API, Edu}, EduAPI: API, Edu, document,
    setTimeout, clearTimeout, console});
  listeners.click({target: {closest: () => ({id: 'rhDemo'})}});
  selected = {id: 13};
  finish({ok: true, id: 7});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reads, 0);
  assert.equal(node('#rhRun').disabled, false);
  assert.equal(node('#rhDemo').disabled, false);
});
