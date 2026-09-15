"""Opt-in real browser + REST + MCP acceptance against a disposable database.

Run: python test_release_e2e.py
Requires Playwright, installed Edge, and four JS test assets described in RELEASE.md.
No production database or Memora requests are used.
"""
import asyncio
import json
import socket
import tempfile
import threading
import time
from contextlib import contextmanager, ExitStack
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import uvicorn
import db
import selene_rest
import selene_server


async def parked(*args, **kwargs):
    await asyncio.Event().wait()


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Test server failed to start')
            time.sleep(.05)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


async def mcp_query(base, name):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(base + '/mcp') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, {})
            assert not result.isError, result
            return json.loads(next(c.text for c in result.content if c.type == 'text'))


def query(base, name):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(mcp_query(base, name))).result(timeout=20)


def run():
    from playwright.sync_api import sync_playwright, expect
    assets = Path(tempfile.gettempdir()) / 'selene-browser-test-assets'
    mapping = {'react@': 'react.js', 'react-dom@': 'react-dom.js', 'prop-types@': 'prop-types.js', 'recharts@': 'recharts.js'}
    for name in mapping.values():
        if not (assets / name).is_file():
            raise RuntimeError(f'Missing test asset: {assets / name}; see RELEASE.md')
    with tempfile.TemporaryDirectory(prefix='selene-acceptance-') as temporary, ExitStack() as stack:
        stack.enter_context(patch.object(db, 'DB_PATH', str(Path(temporary) / 'test.db')))
        stack.enter_context(patch.object(selene_rest, '_feed_loop', parked))
        stack.enter_context(patch.object(selene_rest.reminder, 'reminder_loop', parked))
        stack.enter_context(patch.object(selene_rest.memora_client, 'recall', return_value=None))
        db.init_db()
        db.migrate_cycle_config()
        base = stack.enter_context(serve(selene_rest.app))
        mcp_base = stack.enter_context(serve(selene_server.selene.streamable_http_app()))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def script_route(route):
                    for key, name in mapping.items():
                        if '/' + key in route.request.url:
                            route.fulfill(path=str(assets / name), content_type='application/javascript')
                            return
                    route.abort()

                page.route('https://unpkg.com/**', script_route)
                page.goto(base)
                expect(page.get_by_role('button', name='记录开始', exact=True)).to_be_visible()
                today = date.today()
                start = (today - timedelta(days=30)).isoformat()
                end = (today - timedelta(days=25)).isoformat()
                new_start = today.isoformat()
                page.get_by_label('实际开始日期').fill(start)
                page.get_by_role('button', name='记录开始', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                page.get_by_label('实际结束日期').fill(end)
                page.get_by_role('button', name='记录结束', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                # The actual MCP transport must see the browser writes.
                status = query(mcp_base, 'selene_status')
                assert status['status']['start_date'] == start
                assert status['status']['end_date'] == end
                history = query(mcp_base, 'selene_history')
                assert history['records'][0]['end_date'] == end
                page.reload()
                expect(page.get_by_text('超过预计日期 2 天', exact=True)).to_be_visible()
                expect(page.get_by_text('已过 2 天', exact=True)).to_have_count(1)
                # Lost response after a committed write: retry must not duplicate.
                attempts = []

                def lose_response(route):
                    attempts.append(route.request.post_data_json['request_id'])
                    response = route.fetch()
                    if len(attempts) == 1:
                        route.abort('failed')
                    else:
                        route.fulfill(response=response)

                page.route('**/period/action', lose_response)
                page.get_by_label('实际开始日期').fill(new_start)
                page.get_by_role('button', name='记录开始', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('输入已保留')
                expect(page.get_by_label('实际开始日期')).to_have_value(new_start)
                page.get_by_role('button', name='记录开始', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                assert attempts[0] == attempts[1]
                page.unroute('**/period/action', lose_response)
                page.get_by_role('button', name='记录开始', exact=True).dblclick()
                expect(page.get_by_role('status')).to_contain_text('无需重复保存')
                assert len(db.get_periods()) == 2
                page.locator('summary').click()
                expect(page.locator('details')).to_contain_text(start)
                expect(page.locator('details')).to_contain_text(end)
                page.get_by_role('button', name='撤销上次记录', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已撤销')
                assert len(db.get_periods()) == 1
                assert db.get_periods()[0]['end_date'] == end
                page.reload()
                expect(page.get_by_role('button', name='记录开始', exact=True)).to_be_visible()
                page.get_by_role('button', name='记录开始', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                history = query(mcp_base, 'selene_history')
                assert len(history['records']) == 2
                assert history['records'][1]['start_date'] == start
                page.locator('summary').click()
                expect(page.locator('details')).to_contain_text(end)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                shot = Path(tempfile.gettempdir()) / 'selene-release-mobile.png'
                page.screenshot(path=str(shot), full_page=True)
                page.locator('details').evaluate("element => element.scrollIntoView({block: 'center'})")
                page.screenshot(path=str(shot.with_name('selene-release-history.png')))
                page.set_viewport_size({'width': 1280, 'height': 900})
                page.reload()
                expect(page.get_by_role('button', name='记录开始', exact=True)).to_be_visible()
                page.locator('summary').click()
                expect(page.locator('details')).to_contain_text(end)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                print('PASS: browser start/end -> real MCP -> reload -> new cycle -> history; retry, duplicate, undo; mobile no overflow.')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.get_by_text('记录', exact=True).click()
                historical_start = (today - timedelta(days=60)).isoformat()
                historical_end = (today - timedelta(days=55)).isoformat()
                page.get_by_label('选择月份').fill(historical_start[:7])
                page.locator(f'button[aria-label^="{historical_start} "]').click()
                expect(page.get_by_label('实际开始日期')).to_have_value(historical_start)
                page.get_by_role('button', name='记录开始', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                page.get_by_label('选择月份').fill(historical_end[:7])
                page.locator(f'button[aria-label^="{historical_end} "]').click()
                expect(page.get_by_label('实际结束日期')).to_have_value(historical_end)
                page.get_by_role('button', name='记录结束', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                expect(page.locator(f'button[aria-label^="{historical_end} "]')).to_contain_text('结束')
                assert db.get_periods()[0]['end_date'] == historical_end
                assert db.get_periods()[-1]['start_date'] == new_start
                page.get_by_role('button', name='撤销上次记录', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已撤销')
                assert db.get_periods()[0]['end_date'] == ''
                page.get_by_role('button', name='记录结束', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('已保存')
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=str(shot.with_name('selene-calendar-mobile.png')), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                print('PASS: month picker -> historical day -> start/end -> correct old cycle -> undo; calendar markers and mobile layout.')
                print(f'Screenshot: {shot}')
            finally:
                browser.close()


if __name__ == '__main__':
    run()
