# Changelog

## 1.1.0-rc3 — 2026-11-02

- Resolve all 14 locally reproduced Bandit findings without rule suppressions.
- Replace optimizable assertions in the QGIS integration test with unittest checks.
- Import the actual UI module with isolated API adapters in headless tests,
  removing dynamically generated test code.
- Validate the UA field before removing previous species results and stop
  reclassification when the provider reports a deletion failure.
- Add regression coverage for selective cleanup, missing fields and deletion failure.
- Pass 31 unit tests in normal and optimized Python, and Bandit 1.9.4 with no findings.
- Retain the RC2 height methods, crown metrics, CNN settings and CSV schemas.

## 1.1.0-rc2 — 2026-11-02

- Associate tree measurements and classification with the selected tree.
- Clear previous results when a new tree is selected.
- Classify the selected RGB layer even when a vector layer is active in QGIS.
- Record missing, pending and failed inference explicitly.
- Use one tree CSV schema with crown area, vertices, selected point, methods and CRS.
- Require a valid crown polygon containing the selected tree point.
- Export working and RGB CRS for conglomerate species records.
- Add regression tests for tree state and CSV export.

## 1.1.0-rc1 — 2026-11-02

- Transform sample positions into each raster's horizontal CRS.
- Find actual DSM pixel centers in metric height windows and sample the DTM
  at the same physical location.
- Reject invalid working units, failed transforms, NoData and nonpositive heights.
- Export raster and working CRS provenance.
- Load optional CNN dependencies and user-supplied weights on demand.
- Use QGIS Qt imports and remove machine-specific temporary paths.
