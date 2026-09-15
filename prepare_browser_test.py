"""Download public JS dependencies to a temporary cache for isolated UI tests."""
from pathlib import Path
import tempfile
import urllib.request


def main():
    root = Path(tempfile.gettempdir()) / 'selene-browser-test-assets'
    root.mkdir(exist_ok=True)
    assets = {
        'react.js': 'https://unpkg.com/react@18.3.1/umd/react.production.min.js',
        'react-dom.js': 'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js',
        'prop-types.js': 'https://unpkg.com/prop-types@15.8.1/prop-types.min.js',
        'recharts.js': 'https://unpkg.com/recharts@2.15.4/umd/Recharts.js',
    }
    for name, url in assets.items():
        urllib.request.urlretrieve(url, root / name)
        print(name, (root / name).stat().st_size)


if __name__ == '__main__':
    main()
