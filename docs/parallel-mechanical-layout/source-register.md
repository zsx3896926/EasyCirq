# Source register — task G vendor mechanical facts

Checked 2026-10-27/28 for this parallel task only. It does **not** modify or
replace `design-hardware/references/source-register.md`. Only facts actually read
in the opened document are recorded; search snippets, distributor thumbnails and
unverified forum content are not used as dimensional evidence.

| ID | Part | Publisher | Document / revision | Scope actually read | Dimensions retained | URL | What it cannot prove |
|---|---|---|---|---|---|---|---|
| USB-GCT-4105 | GCT **USB4105-GF-A** USB 2.0 Type-C receptacle, top mount | Global Connector Technology (GCT), drawing hosted by Digi-Key | *USB Type C Receptacle for USB 2.0 SMT Type, PCB Top Mount*, drawing date 04/10/2019, revision **B3 24/02/23**, sheet 1/2, mm, X.XX ±0.15 | Sheet 1/2 text layer: component outline, recommended PCB layout, mating view. Sheet 2/2 is packaging only and was not used. | body 8.94 overall width; 7.35 front-to-back depth; 3.31 profile height; shell 8.34 +0.06/-0.02; plug max width 6.5 (mating view) | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5492/USB4105.pdf (product page https://gct.co/connector/usb4105) | Exact mating-face-to-PCB-edge distance, mating datum relative to SMT pads, plug height/insertion depth and panel-opening recommendation are **not** established by the extracted text; they stay unknown and any synthetic case marks them as synthetic. |
| BTN-OMRON-B3F | OMRON **B3F-1000** tactile switch, 6×6 mm flat plunger, silver contacts | OMRON | *B3F Tactile Switch* datasheet, 9 pages (no revision string in extracted text) | Page 1 model list; page 3 Operating Characteristics; page 4 6×6 mm Dimensions; page 4 tolerance note ±0.4 mm unless stated. Pages 2 and 5–9 unused. | body 6±0.2 × 6±0.2; height 4.3±0.2 (B3F-1000); pretravel 0.25 +0.2/−0.1 mm; OF 0.98±0.29 N; four pins 1±0.05 dia; pin pitch 6.5±0.1 / 4.5±0.1 | https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3f.pdf | Plunger/cap diameter (a 3.5 dia. value appears near the flat-plunger drawings but the extracted text cannot bind it to a feature with certainty), key-top (B32) clearance, panel opening and cap height above the body are **not** proven; they remain synthetic/unknown. |
| SCR-ISO4762-M3 | ISO 4762 / DIN 912 **M3** socket head cap screw (standard dimension table, not one OEM part number) | Engineering Hardware & Fasteners (ISO 4762 / DIN 912 compilation) | *M3 Socket Head Cap Screws Dimensions*, page undated; table cites ISO 4762 / DIN 912, ISO 273, ISO 724 | M3 dimensional row, M3 hole-size table, tightening-torque table | head dk 5.5; head height k 3.0; hex s 2.5; socket depth t min 1.3; clearance hole 3.4 (ISO 273 medium); pitch 0.5 | https://engineeringhardware.com/guide/size/m3-socket-head-cap-screws/ | This is a **standards compilation, not an OEM drawing**: tolerance class, washer OD/thickness and tool length are not read. The head diameter/height are used as a synthetic screw-head keep-out; tool length and washer stack must be declared by the project. |

Transcribed machine-readable facts (short excerpts, no OEM CAD and no full
datasheet text) are in
[`benchmarks/mechanical-layout/sources/`](../../benchmarks/mechanical-layout/sources/):

* `USB-GCT-4105.json`
* `BTN-OMRON-B3F.json`
* `SCR-ISO4762-M3.json`

## How the facts are used

* The synthetic benchmark cases use the USB body envelope (8.94 × 7.35 × 3.31 mm)
  as a declared connector body, and 6.5 mm as a declared plug cross-section
  width. The **depth/height of the plug**, the mating-face-to-PCB-edge distance
  and the enclosure opening are synthetic design assumptions. They are never
  described as vendor facts or user measurements.
* The synthetic panel case uses the B3F-1000 body 6 × 6 mm, height 4.3 mm and
  travel bound 0.15–0.45 mm; the key-top diameter, panel thickness and opening
  clearance are synthetic declarations.
* The M3 table shapes a declared screw-head disk (5.5 × 3.0 mm) and a 3.4 mm
  clearance hole; the tool cylinder and washer are explicit synthetic inputs.

## Provenance rules used by this task

* A vendor fact may justify a body outline, height or travel bound. It never
  justifies an assembly PASS on its own.
* A dimension without a declared `max` is typical-only; the tool reports
  `unknown` rather than treating it as a maximum.
* No user project, production system or client `epro2` archive was accessed.
  All benchmark documents are synthetic and marked `kind: synthetic`.
* No third-party CAD/STEP file is redistributed. The source JSONs contain only
  short transcribed facts and links.
