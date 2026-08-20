# -*- coding: utf-8 -*-
# 把 selene_browser.jsx 内联进 index.html，绕开 Babel 外部脚本加载的坑
import io

def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()

def write(p, s):
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(s)

jsx = read('selene_browser.jsx')

assert '</script>' not in jsx, 'JSX contains </script>, unsafe to inline!'

html = u'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Selene</title>
<style>html,body,#root{height:100%;margin:0}body{background:#F4F1EE;font-family:system-ui,sans-serif}</style>
</head>
<body>
<div id="root"></div>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<script src="https://unpkg.com/recharts@2/umd/Recharts.min.js"></script>
<script type="text/babel" data-presets="react">
__JSX__
</script>
</body>
</html>'''

html = html.replace('__JSX__', jsx)
write('index.html', html)
print('INLINE_OK', len(html))
print('HAS_CLOSING_SCRIPT_TAG', '</script>' in jsx)
