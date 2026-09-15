const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : ['2026-09-19T12:00:00'])); }
}
const react = {
  useState: value => [value, () => {}],
  useEffect: () => {},
  createContext: value => ({ value, Provider: 'provider' }),
  useContext: context => context.value,
  createElement: (type, props, ...children) => ({ type, props, children }),
};
const context = vm.createContext({
  window: { React: react, Recharts: {} }, Date: FixedDate, console,
  document: { getElementById: () => ({}) },
  ReactDOM: { createRoot: () => ({ render: () => {} }) },
});
vm.runInContext(fs.readFileSync('selene_browser.js', 'utf8'), context);
assert.equal(vm.runInContext("cycleDayFromStart('2026-08-21', 28)", context), 30);
assert.equal(vm.runInContext("cycleDayFromStart('', 28)", context), 0);
assert.equal(vm.runInContext("phaseFromTable(22, {'22':'luteal'}).name === PHASES[3].name", context), true);
assert.equal(vm.runInContext("phaseFromTable(0, {}).name === UNKNOWN_PHASE.name", context), true);
assert.equal(vm.runInContext('!!Selene()', context), true);
assert.equal(vm.runInContext('!!TodayCard({day: 0})', context), true);
assert.equal(vm.runInContext('!!MoonRing({day: 30, total: 28})', context), true);
console.log('Frontend checks passed: no rollover, server phase mapping, empty-state rendering.');
