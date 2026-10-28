"""Offline first-board bring-up planner.

The planner turns a versioned design-intent / evidence JSON document into an
ordered, executable-by-a-human (never by this tool) bring-up plan, and provides
a separate evaluator for result records.  It never connects to instruments,
never flashes firmware, never powers a board, never calls EDA tools and never
executes shell commands.

Run from the ``design-hardware/scripts`` directory::

    python -m bringup_planner validate --input plan-input.json
    python -m bringup_planner plan --input plan-input.json --out out/
    python -m bringup_planner explain --input plan-input.json --step I2-...
    python -m bringup_planner evaluate --plan out/plan.json \
        --results results.json --out out/

A passing plan/evaluation is an offline document check only.  It is not a
hardware, safety, EMC or thermal qualification.
"""

TOOL_NAME = 'bringup_planner'
TOOL_VERSION = '1.0.0'

INPUT_SCHEMA = 'bringup-plan-input/v1'
PLAN_SCHEMA = 'bringup-plan/v1'
RESULT_SCHEMA = 'bringup-result/v1'
EVALUATION_SCHEMA = 'bringup-evaluation/v1'
DEVICE_FACTS_SCHEMA = 'bringup-device-facts/v1'

# Exit codes are part of the CLI contract (documented in contract.md).
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_INVALID_INPUT = 2
EXIT_INCOMPLETE = 3

# First-release supported envelope.  These are scope gates, not device
# defaults: values are only used to decide "supported / needs a specialist".
SUPPORTED_MAX_OPERATING_DC_V = 30.0
SUPPORTED_MAX_ABSOLUTE_DC_V = 60.0
SUPPORTED_OPERATIONS = (
    'visual_inspection',
    'deenergized_continuity',
    'powered_dc_measurement',
    'digital_interface',
    'analog_measurement',
    'low_side_load',
)
UNSUPPORTED_SUPPLY_CLASSES = (
    'mains_ac',
    'high_voltage_dc',
    'battery_charging',
    'rf_certification',
    'mixed_energy',
)
