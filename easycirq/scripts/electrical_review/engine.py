"""Review orchestration: validate, run R1-R6, build the deterministic report."""
from .contract import validate
from .report import build_report, make_results
from .rules import RUNNERS


def review(data, input_meta, coverage_extra=None, assumptions=None):
    normalized = validate(data)
    results = make_results()
    for runner, result in zip(RUNNERS, results):
        runner(normalized, result)
    report_meta = dict(input_meta)
    report_meta["intent_supplied"] = bool(
        normalized["_meta"].get("intent_supplied"))
    report_meta["measurement"] = normalized["_meta"].get("measurement")
    report = build_report(normalized, results, report_meta,
                          coverage_extra=coverage_extra,
                          assumptions=assumptions)
    return normalized, report
