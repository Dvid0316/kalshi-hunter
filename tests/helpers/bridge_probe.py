"""Boot the data bridge without any QML and report what the UI would show. Used by test_app_runtime.py."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QCoreApplication                     # noqa: E402

from desktop.bridge import Bridge                               # noqa: E402
from desktop.repository import Repository                       # noqa: E402


def main() -> int:
    app = QCoreApplication([])
    bridge = Bridge(Repository(), sample=False)

    def pump(pred, what, timeout=60.0):
        end = time.time() + timeout
        while time.time() < end:
            app.processEvents()
            if pred():
                return
            time.sleep(0.02)
        raise SystemExit(f'timed out waiting for {what}')

    bridge.load()
    pump(lambda: bridge.ui['ready'] and not bridge.ui['loading'], 'initial load')
    for page in ('Markets', 'Positions', 'History', 'Journal'):
        bridge.navigate(page)
        pump(lambda: not bridge.ui['loading'], f'page {page}')
    out = dict(ready=bool(bridge.ui['ready']), overview_loaded=bool(bridge.overview.get('counts')),
               markets_loaded=bool(bridge.markets['rows']), errors=dict(bridge.ui['errors']))
    bridge.close()
    print(json.dumps(out), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
