"""Tests for the offline placement-intent CLI (HMT + CCG PoC).

The suite deliberately does **not** import the implementation package.  Every
assertion goes through a real child process::

    python -m placement_intent validate|plan|explain --input ...

with ``PYTHONPATH`` pointing at ``easycirq/scripts`` and
``PYTHONDONTWRITEBYTECODE=1``.  This avoids the cross-package shadowing problem
that ``python -m unittest discover -s tests`` has historically hit when a test
package shares its name with an implementation package (see
``tests/change_impact/__init__.py`` for the aliasing alternative used
elsewhere).

No ``sys.path`` manipulation happens at import time; the helper in
``support.py`` only attaches ``PYTHONPATH`` to the subprocess environment.
"""
