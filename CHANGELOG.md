# Changelog

## 1.1.0-rc3 — 2026-11-02
QGIS plugin for forest inventory and UAV data analysis, integrating sampling plot clusters, DSM/DTM canopy height measurements, manual tree crown delineation, crown area and maximum diameter measurements, optional deep learning species classification from RGB imagery, and georeferenced CSV export for Fazenda ECO. These workflows provide structural forest data to support forest carbon research, aboveground carbon (AGC) modelling, and climate studies using external models.

Changes in this version:

- Improved validation and error handling when removing previous classification results, helping prevent duplicate samples during conglomerate reclassification.
- Updated integration checks to remain active under optimized Python.
- Reworked interface tests to import the actual plugin module using isolated API adapters.
- Passed 31 automated tests in normal and optimized Python.
- Documented eight successful QGIS integration checks reported by the author after RC3 installation.
- Preserved canopy height methods, crown measurements, classification settings, and CSV schemas.

Scientific scope: AGC estimation and climate projections require external models and appropriate field validation. This version provides supporting measurements and exports; it does not calculate AGC or run climate projections directly.

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
