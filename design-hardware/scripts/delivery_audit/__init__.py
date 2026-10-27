"""Offline delivery-audit tool (independent CLI package).

Run from ``design-hardware/scripts``::

    python -m delivery_audit inspect --input <dir-or.zip>
    python -m delivery_audit manifest --input <dir-or.zip> --out manifest.json
    python -m delivery_audit audit --input <dir-or.zip> --profile pcb-fabrication \
        --declarations declarations.json --out audit/

The package only reads the input and never calls EDA, the network or an
external executor.  See ``docs/parallel-delivery-audit/contract.md``.
"""

TOOL_NAME = "delivery-audit"
TOOL_VERSION = "0.1.0"
