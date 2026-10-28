const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'k10-simulator.html'), 'utf8');
const script = html.match(/<script id="simulator-script">([\s\S]*?)<\/script>/)[1];
const tick = () => new Promise(resolve => setImmediate(resolve));

class Element {
  constructor(id = '') {
    this.id = id; this.textContent = ''; this.value = ''; this.children = [];
    this.dataset = {}; this.classes = new Set(); this.handlers = {}; this.disabled = false;
    this.classList = { toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name) };
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  fire(name, event = {}) { return this.handlers[name]?.({ preventDefault() {}, ...event }); }
  setAttribute(name, value) { this[name] = value; }
  append(...items) { for (const item of items) { item.parent = this; this.children.push(item); } }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  get firstElementChild() { return this.children[0]; }
  remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
  querySelector(selector) { return selector === '.point-name' ? this.pointName : null; }
}

function page({ protocol = 'http:', fetch, voices = [], speech = true } = {}) {
  const ids = ['screen-mode', 'screen-service', 'screen-step', 'screen-title', 'screen-body', 'screen-helper',
    'map-status', 'speaker-status', 'speech-toggle', 'speech-toggle-label', 'protocol-log', 'query-form',
    'query-input', 'button-a', 'button-b', 'connection-status', 'chat-history', 'new-chat', 'pending-status', 'submit-button'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements['speech-toggle'].checked = true;
  const quick = new Element(); quick.dataset.query = '我想报名参加书法班';
  const points = ['小区入口', '社区中心', '卫生站', '活动室', '服务大厅', '便民驿站'].map((name, i) => {
    const point = new Element(); point.dataset.led = String(i + 1); point.pointName = new Element(); point.pointName.textContent = name; return point;
  });
  const meter = Array.from({length: 3}, () => new Element());
  const document = {
    handlers: {}, getElementById: id => elements[id], createElement: () => new Element(),
    querySelectorAll: selector => ({'.quick-action': [quick], '.map-point': points, '#step-meter span': meter})[selector] || [],
    addEventListener(name, fn) { this.handlers[name] = fn; },
  };
  const spoken = [];
  class Utterance { constructor(text) { this.text = text; } }
  const synth = { cancel() {}, getVoices() { return voices; }, addEventListener() {}, speak(item) { spoken.push(item); } };
  const window = { location: {protocol}, ...(speech ? {speechSynthesis: synth, SpeechSynthesisUtterance: Utterance} : {}) };
  const context = vm.createContext({document, window, fetch, SpeechSynthesisUtterance: Utterance, Date, console});
  vm.runInContext(script, context);
  return {elements, quick, points, document, spoken};
}

function response(data, status = 200) { return {ok: status < 400, status, json: async () => data}; }
function state(session, service = false) {
  return {session_id: session, reply: service ? '开始书法班指引。' : '', speech: service ? '开始书法班指引。请前往活动室。' : '', sources: [], error: '',
    device: { mode: service ? 'showing' : 'idle', service_id: service ? 'calligraphy' : null, led: service ? 4 : 0,
      location: service ? '活动室' : '', step_index: 0, step_count: service ? 3 : 0,
      screen: {mode: service ? '服务指引' : '待机', service: service ? '书法班' : '等待咨询', step: '第 1 / 3 步',
        title: '前往活动室', body: '请前往活动室。', helper: '演示数据'}},
    protocol: [{direction: 'RX', line: service ? 'LED|4' : 'LED|0'}]};
}

test('direct file opening shows service startup guidance without calling a model', async () => {
  let calls = 0;
  const p = page({protocol: 'file:', fetch: async () => { calls++; }});
  await tick();
  assert.equal(calls, 0);
  assert.match(p.elements['connection-status'].textContent, /启动/);
  assert.equal(p.elements['submit-button'].disabled, true);
});

test('a real API response updates chat, screen, LED and the protocol log', async () => {
  const calls = [];
  const p = page({fetch: async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/health')) return response({provider: 'ollama', status: 'ready', detail: '本地模型已就绪。'});
    if (url.endsWith('/sessions')) return response(state('s1'));
    return response(state('s1', true));
  }});
  await tick(); await tick();
  await p.quick.fire('click'); await tick();
  assert.equal(p.elements['screen-service'].textContent, '书法班');
  assert.equal(p.points[3].classes.has('is-active'), true);
  assert.equal(p.elements['chat-history'].children.length, 2);
  assert.ok(calls.some(([url]) => url.endsWith('/s1/messages')));
  assert.ok(p.elements['protocol-log'].children.some(row => row.children[2].textContent === 'LED|4'));
});

test('a late model response cannot change a newly created conversation', async () => {
  let resolveOld;
  let count = 0;
  const p = page({fetch: async url => {
    if (url.endsWith('/health')) return response({provider: 'ollama', status: 'ready', detail: '就绪'});
    if (url.endsWith('/sessions')) return response(state('s' + (++count)));
    return new Promise(resolve => { resolveOld = resolve; });
  }});
  await tick(); await tick();
  p.quick.fire('click'); await tick();
  await p.elements['new-chat'].fire('click'); await tick();
  resolveOld(response(state('s1', true))); await tick(); await tick();
  assert.equal(p.elements['screen-mode'].textContent, '待机');
  assert.equal(p.elements['chat-history'].children.length, 0);
  assert.equal(p.points.some(point => point.classes.has('is-active')), false);
});

test('waiting for a reply keeps the input focusable but prevents edits', async () => {
  let finish;
  const p = page({fetch: async url => {
    if (url.endsWith('/health')) return response({provider:'ollama',status:'ready',detail:'就绪'});
    if (url.endsWith('/sessions')) return response(state('s1'));
    return new Promise(resolve => { finish = resolve; });
  }});
  await tick(); await tick();
  p.quick.fire('click'); await tick();
  assert.equal(p.elements['query-input'].disabled, false);
  assert.equal(p.elements['query-input'].readOnly, true);
  assert.equal(p.elements['submit-button'].disabled, true);
  finish(response(state('s1', true))); await tick(); await tick();
  assert.equal(p.elements['query-input'].readOnly, false);
});

test('remote voices are never used', async () => {
  const p = page({voices: [{lang:'zh-CN', localService:false}], fetch: async url => response(url.endsWith('/health') ? {provider:'ollama',status:'ready',detail:'就绪'} : state('s1', !url.endsWith('/sessions')))});
  await tick(); await tick();
  await p.quick.fire('click'); await tick();
  assert.equal(p.spoken.length, 0);
  assert.equal(p.elements['speech-toggle'].disabled, true);
  assert.match(p.elements['speaker-status'].textContent, /本地中文语音/);
});

test('local speech can be switched off and late callbacks do not change its status', async () => {
  const p = page({voices: [{lang:'zh-CN', localService:true}], fetch: async url => response(url.endsWith('/health') ? {provider:'ollama',status:'ready',detail:'就绪'} : state('s1', !url.endsWith('/sessions')))});
  await tick(); await tick();
  await p.quick.fire('click'); await tick();
  assert.equal(p.spoken.length, 1);
  assert.equal(p.spoken[0].text, '开始书法班指引。请前往活动室。');
  p.elements['speech-toggle'].checked = false;
  p.elements['speech-toggle'].fire('change');
  p.spoken[0].onerror();
  assert.equal(p.elements['speaker-status'].textContent, '播报已关闭');
  assert.equal(p.elements['screen-service'].textContent, '书法班');
});

test('A and B keyboard shortcuts do not intercept text inputs', async () => {
  const events = [];
  const p = page({fetch: async (url, options) => {
    if (url.endsWith('/health')) return response({provider:'ollama',status:'ready',detail:'就绪'});
    if (url.endsWith('/events')) events.push(JSON.parse(options.body).event);
    return response(state('s1'));
  }});
  await tick(); await tick();
  p.document.handlers.keydown({key:'a', target:{tagName:'INPUT'}, preventDefault(){}});
  await tick();
  assert.deepEqual(events, []);
  p.document.handlers.keydown({key:'b', target:{tagName:'BODY'}, preventDefault(){}});
  await tick(); await tick();
  assert.deepEqual(events, ['BUTTON_B']);
});

test('unsupported speech synthesis leaves text and controls available', async () => {
  const p = page({speech:false, fetch: async url => response(url.endsWith('/health') ? {provider:'ollama',status:'ready',detail:'就绪'} : state('s1', !url.endsWith('/sessions')))});
  await tick(); await tick();
  await p.quick.fire('click'); await tick();
  assert.equal(p.elements['screen-service'].textContent, '书法班');
  assert.equal(p.elements['speech-toggle'].disabled, true);
  assert.match(p.elements['speaker-status'].textContent, /不支持/);
});

test('markup keeps keyboard focus, responsive layout and the original eight examples', () => {
  assert.match(html, /focus-visible/);
  assert.match(html, /max-width:\s*650px/);
  assert.equal((html.match(/class="quick-action"/g) || []).length, 8);
  for (const query of ['我想报名参加书法班', '我想参加太极晨练', '哪里可以免费量血压', '我想咨询社保',
    '我想咨询高龄津贴', '老人助餐点在哪里', '家里水电坏了怎么报修', '我想办理护照']) {
    assert.ok(html.includes(`data-query="${query}"`));
  }
  assert.doesNotMatch(html, /<script[^>]+src=|<link[^>]+href=/i);
});
