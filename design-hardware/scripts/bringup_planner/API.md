"""Module contract for the bringup_planner capability owners.

Internal API (frozen 2026-10-27):

* ``ctx`` is ``model.PlanContext`` (see model.py).  It exposes the normalised
  input, lookups and bookkeeping:
    - ``ctx.project``, ``ctx.domains``, ``ctx.assemblies``, ``ctx.interfaces``,
      ``ctx.testpoints``, ``ctx.equipment``, ``ctx.conditions``, ``ctx.facts``,
      ``ctx.policy``, ``ctx.evidence``;
    - ``ctx.scope`` (scope gate), ``ctx.dag`` (domain graph with ``order``),
      ``ctx.supply_conflicts``;
    - ``ctx.add_step(step)`` — always build steps with
      ``steps.make_step(...)`` so the shared fields are complete;
    - ``ctx.add_gap(code, topic, detail, needed=[], severity='warning')``;
    - ``ctx.add_unknown(code, topic, detail, needed=[], blocks=[])``;
    - ``ctx.add_equipment_gap(code, equipment, capability, detail)``;
    - ``ctx.add_tree(dict)`` (faults only; append to ``ctx.trees`` directly is
      also accepted);
    - lookups: ``ctx.domain(id)``, ``ctx.domain_for_net(net)``,
      ``ctx.testpoints_for(net)``, ``ctx.testpoint(id)``,
      ``ctx.interface(id)``, ``ctx.fact(id)``, ``ctx.fact_value(id, key)``,
      ``ctx.supplies()``, ``ctx.multimeters()``, ``ctx.oscilloscopes()``,
      ``ctx.declared_ops()``, ``ctx.supports_operation(op)``.
* ``ctx.scope['energize_allowed']`` is False for needs_information /
  unsupported / needs_specialist: never emit a ready powered step then.
  Blocked steps may still be emitted with the missing information listed.
* Step ids are stable and derived from ids, never from iteration order or
  free text: e.g. ``I1-OFF-001``, ``I2-SEQ-<domain>``,
  ``I3-V-<domain>``, ``I4-<interface>-<n>``.
* Aggregated lists are sorted in the normalised model, so iterate them in
  order and the output is deterministic.
* Allowed files per owner are listed in the task prompt.  Do not edit shared
  core files (model/plan/cli/render/dag/steps/scope) without telling the Lead.
"""
