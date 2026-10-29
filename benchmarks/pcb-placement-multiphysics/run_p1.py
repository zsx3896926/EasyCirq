#!/usr/bin/env python3
"""Entry point for the P1 multi-physics placement experiment.

    python run_p1.py            # full experiment (~1-2 min)
    python run_p1.py --quick    # smoke configuration
"""

import sys

from mp_place.experiment import main

if __name__ == "__main__":
    sys.exit(main())
