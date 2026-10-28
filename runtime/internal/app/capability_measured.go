package app

// measuredDeliverables lists deliverables for which this repository records a
// real-host verification (not merely the existence of an API). Keep each entry
// tied to concrete evidence; see docs/toolchain-integration/evidence/.
//
// 2026-10-28, EasyEDA Pro 4.1.78 + connector 0.1.4, acceptance board
// (zhigou-integrated-dual-button-led-20261027), evidence under
// docs/toolchain-integration/evidence/manufacture-spike/:
//   - export.gerber: 9-layer Gerber zip (GTL/GBL/GTO/GBO/GTS/GBS/GTP/GKO/GDL), artifact inspected
//   - export.cpl:    UTF-16 TSV, 9 rows matching the 9-device BOM
//   - export.3d:     OBJ 209 KB + STEP 5.0 MB (ISO-10303-21), non-empty and parsed
//
// export.drill intentionally stays unmeasured: the acceptance board has zero
// vias, so no drill file was produced and the with-vias path is unverified.
func measuredDeliverables() map[string]bool {
	return map[string]bool{
		"export.gerber": true,
		"export.cpl":    true,
		"export.3d":     true,
	}
}
