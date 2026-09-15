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
  let tree = render('Selene()');
  let mood = component(tree, 'MoodLogger');
  await mood.props.onLog('2026-08-21', 2);
  await mood.props.onLog('2026-09-18', 8);
  tree = render('Selene()');
  mood = component(tree, 'MoodLogger');
  assert.deepEqual({ ...mood.props.moodLog }, { '2026-08-21': 2, '2026-09-18': 8 });
  failNext = true;
  await mood.props.onLog('2026-08-21', 10);
  tree = render('Selene()');
  assert.equal(component(tree, 'MoodLogger').props.moodLog['2026-08-21'], 2);
  const symptoms = component(tree, 'SymptomLogger');
  await Promise.all([
    symptoms.props.onToggle('2026-08-21', 'a'),
    symptoms.props.onToggle('2026-08-21', 'b'),
  ]);
  tree = render('Selene()');
  assert.deepEqual([...component(tree, 'SymptomLogger').props.symptomLog['2026-08-21']], ['a', 'b']);
  assert.equal(requests[0].body.date, '2026-08-21');

  // Browse to August, select the 21st, and use the actual mood button callback.
  slots = [];
  context.saved = [];
  const calendar = "LogPage({moodLog:{'2026-08-21':2},symptomLog:{},dateInfo:{},periodStart:'2026-09-18',onLog:async (d,s)=>{saved.push([d,s]);return true;},onToggle:()=>{}})";
  tree = render(calendar);
  find(tree, node => node.type === 'button' && node.props['aria-label'] === '\u4e0a\u4e2a\u6708').props.onClick();
  tree = render(calendar);
  find(tree, node => node.type === 'button' && node.props.key === 21).props.onClick();
  tree = render(calendar);
  const historic = component(tree, 'MoodLogger');
  assert.equal(historic.props.logDate, '2026-08-21');
  context.historicProps = { ...historic.props, moodLog: {} };
  slots = [];
  tree = render('MoodLogger(historicProps)');
  await find(tree, node => node.type === 'button' && node.props.key === 8).props.onClick();
  assert.equal(context.saved[0][0], '2026-08-21');
  assert.equal(context.saved[0][1], 8);
  assert.equal(evaluate("moodEntries({'2026-09-18':8,'2026-08-21':2})[0].date"), '2026-08-21');
  assert.equal(evaluate("phaseAverages({}, {})[0].avg"), null);
  assert.equal(evaluate("phaseAverages({'2026-08-21':2,'2026-09-18':8},{'2026-08-21':{phase:'menstrual'},'2026-09-18':{phase:'menstrual'}})[0].avg"), 5);
  console.log('Date UI checks passed: historical selection, cross-cycle storage, failed save retention, queued symptom changes, real statistics.');
})().catch(error => { console.error(error); process.exitCode = 1; });
