// 用 @babel/standalone 把 selene_browser.jsx 转译成纯 JS（无 JSX、无 import/export）
const Babel = require('@babel/standalone');
const fs = require('fs');

const src = fs.readFileSync('selene_browser.jsx', 'utf8');
const out = Babel.transform(src, {
  presets: [['react', { runtime: 'classic' }]],
  compact: false,
}).code;

fs.writeFileSync('selene_browser.js', out);
console.log('TRANSPILED_BYTES', Buffer.byteLength(out, 'utf8'));
console.log('HAS_IMPORT', out.includes('import '));
console.log('HAS_EXPORT', out.includes('export '));
