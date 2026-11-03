# Changelog

## 1.1.0-rc4 — 2026-11-03

Forest inventory and UAV measurements supporting external forest carbon, AGC,
and climate research; no AGC equation or climate projection is executed here.

- Require stable PyTorch >= 2.10.0 before importing torchvision or opening weights;
  block affected, preview and unrecognized versions without installing packages.
- Create a unique temporary workspace per run; validate UA identifiers and never
  use them as paths or recursively delete directories from previous runs.
- Write only to marked in-memory outputs; do not adopt existing files or older
  unmarked layers merely because their display names match.
- Prepare all new species samples before replacing the previous result layer;
  preserve other UAs and stop without replacement after crop, inference or write failure.
- Preserve active edit sessions and restore the previous memory layer if the
  project-layer replacement fails.
- Add regression checks for these boundaries and a simulated repeated 625-sample flow.
- Add isolated QGIS integration and optional real-model inference runners.
- Preserve height methods, crown metrics, LeNet architecture, preprocessing,
  class order, confidence threshold and CSV column schemas.

Validation: 52 automated checks passed in normal and optimized Python. Native QGIS
and real-model tests of RC4 remain pending; do not infer security certification
or botanical accuracy from these checks.

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
