"""Layout engine v2 — offline schematic placement (easycirq-sch-layout-v2/v1).

The package is intentionally import-light: submodules are NOT imported here, so
``import tools.layout2.device_metrics`` never pulls in EDA code, never reads an
asset file, and never opens a client connection. Each module owns one job
(see ``docs/method/layout-engine-v2-contract.md`` §2):

* ``page_template``      — page size / usable regions / title-block keep-out
* ``text_metrics``       — text bbox estimation and collision checks
* ``device_metrics``     — measured device geometry and halo expansion
* ``hard_rules``         — the section-0 invariants as findings + verdict
* ``pagination``         — module -> page allocation
* ``zone_solver``        — module placement inside usable regions
* ``label_solver``       — net-label/text placement around pins
* ``layout_engine``      — offline orchestration into page plans
* ``benchmark``          — synthetic corpora, batch solve and scoring

Everything except ``sch_layout_apply2`` must stay EDA-free so the whole plan can
be produced and validated offline. Real measurements are written back to
``easycirq/assets/`` by single, serial runners such as
``tools/layout2/measure_device_metrics.py``.
"""
