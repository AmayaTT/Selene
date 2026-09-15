"""Serve the same browser entry points from both REST applications."""
from pathlib import Path
from fastapi.responses import FileResponse


def register(app):
    root = Path(__file__).resolve().parent

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(root / 'index.html', headers={'Cache-Control': 'no-cache'})

    @app.get('/selene_browser.js', include_in_schema=False)
    def browser_js():
        return FileResponse(root / 'selene_browser.js', headers={'Cache-Control': 'no-cache'})
