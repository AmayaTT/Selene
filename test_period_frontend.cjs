const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Execute the shipped bundle with a small stateful hook harness. It exercises
// the real component callbacks; it is not a substitute for browser visual QA.
let slots = [], cursor = 0, requests = [], failNext = false;
const react = {
  useState(initial) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = initial;
    return [slots[i], value => { slots[i] = typeof value === 'function' ? value(slots[i]) : value; }];
  },
  useRef(initial) { return this.useState({ current: initial })[0]; },
  useEffect() {},
  createContext: value => ({ value, Provider: 'provider' }),
  useContext: context => context.value,
  createElement: (type, props, ...children) => ({ type, props: props || {}, children }),
};
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : ['2026-09-19T12:00:00'])); }
}
const context = vm.createContext({
  window: { React: react, Recharts: {} }, Date: FixedDate, console,
  document: { getElementById: () => ({}) },
  ReactDOM: { createRoot: () => ({ render() {} }) },
  setTimeout() {},
  fetch: async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url, body });
    const ok = !failNext;
    failNext = false;
    return { ok, json: async () => ({ success: true, ...body, day: 1, phase: 'menstrual' }) };
  },
});
vm.runInContext(fs.readFileSync('selene_browser.js', 'utf8'), context);
const evaluate = expression => vm.runInContext(expression, context);
function render(expression) { cursor = 0; return evaluate(expression); }
function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  for (const child of (Array.isArray(node) ? node : node.children || [])) {
    const found = find(child, predicate);
    if (found) return found;
  }
  return null;
}
const component = (tree, name) => find(tree, node => node.type?.name === name);

(async () => {
  context.updates = [];
  context.config = { periodId: 1, periodStart: '2026-08-21', undoAction: { request_id: 'previous' } };
  const expression = 'PeriodActions({config,onChange:async r=>updates.push(r)})';
  const button = (tree, text) => find(tree, n => n.type === 'button' && n.children.includes(text));
  const input = (tree, label) => find(tree, n => n.type === 'input' && n.props['aria-label'] === label);
  let tree = render(expression);
  assert.equal(input(tree, '实际开始日期').props.value, '2026-09-19');
  input(tree, '实际开始日期').props.onChange({ target: { value: '2026-09-18' } });
  tree = render(expression);
  failNext = true;
  await button(tree, '记录开始').props.onClick();
  assert.equal(context.updates.length, 0);
  tree = render(expression);
  assert.equal(input(tree, '实际开始日期').props.value, '2026-09-18');
  await Promise.all([button(tree, '记录开始').props.onClick(), button(tree, '记录开始').props.onClick()]);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].body.request_id, requests[1].body.request_id);
  assert.equal(context.updates.length, 1);
  tree = render(expression);
  input(tree, '实际结束日期').props.onChange({ target: { value: '2026-08-20' } });
  tree = render(expression);
  await button(tree, '记录结束').props.onClick();
  assert.equal(requests.length, 2);
  input(tree, '实际结束日期').props.onChange({ target: { value: '2026-08-26' } });
  tree = render(expression);
  await button(tree, '记录结束').props.onClick();
  assert.equal(requests[2].body.period_id, 1);
  assert.equal(requests[2].body.date, '2026-08-26');
  tree = render(expression);
  await button(tree, '撤销上次记录').props.onClick();
  assert.equal(requests[3].url, '/period/undo');
  assert.equal(requests[3].body.request_id, 'previous');
  slots = [];
  context.config = {};
  tree = render(expression);
  assert.equal(button(tree, '记录结束').props.disabled, true);
  slots = [];
  tree = render('Selene()');
  assert.ok(component(tree, 'PeriodActions'));
  assert.ok(component(tree, 'PeriodStatus'));
  assert.equal(find(tree, n => n.type === 'input' && n.props.type === 'range'), null);
  console.log('Period UI passed: retained dates, retry identity, duplicate click guard, end validation, undo, pending state.');
})().catch(error => { console.error(error); process.exitCode = 1; });

