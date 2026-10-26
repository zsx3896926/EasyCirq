#!/usr/bin/env python3
"""Entry point for the offline design engine.

Usage: python design_engine_cli.py <command> [options]
See design_engine/cli.py --help and references/design-engine.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_engine.cli import main

if __name__ == '__main__':
    sys.exit(main())
