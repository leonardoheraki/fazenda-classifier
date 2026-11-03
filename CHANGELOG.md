# Changelog

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
