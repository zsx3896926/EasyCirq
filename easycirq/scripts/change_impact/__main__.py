"""``python -m change_impact`` entry point."""
from __future__ import annotations

import sys


def _main():
    try:
        from .cli import main
    except ImportError:  # pragma: no cover - direct script execution
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from change_impact.cli import main
    return main()


if __name__ == '__main__':
    sys.exit(_main())
