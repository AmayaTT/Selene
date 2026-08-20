# -*- coding: utf-8 -*-
import io

def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()

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
<script crossorigin src="https://unpkg.com/prop-types@15.8.1/prop-types.min.js"></script>
<script crossorigin src="https://unpkg.com/recharts@2/umd/Recharts.js"></script>
<script src="selene_browser.js"></script>
</body>
</html>'''

with io.open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('INDEX_WRITTEN', len(html))
