# Changelog

## 1.1.0-rc8 — 2026-11-05

- Rename the native plot workflow to Parcela and show Dimensões (100 m × 100 m)
  and Subparcelas (1 m × 10 m).
- Represent the 100 original height-sampling windows as individual 1 × 10 m
  subplot polygons. Retain all 100 sampling centers and the existing raster
  height algorithm. Use a separate owned layer, subparcelas_1x10_M37, preserving
  legacy strip layers and their data. New subplot IDs are SP_001 to SP_100.
- After completing a crown, offer Add another tree or Finalize list. Keep
  independent snapshots of each crown, height, classification, ID and optional UA.
- Add a review table, selected-row removal and a new-list action. Block duplicate
  IDs within a UA, protect completed drafts and warn before discarding unexported
  records. Cancelling save retains the complete list.
- Export all finalized trees to one ECO CSV, one tree per row, with unchanged
  columns, units and precision. A rejected tree blocks the complete ECO export;
  the full diagnostic report keeps every row and now includes tree IDs and UA.

Validation: 79 automated tests, including six HTTP checks against Fazenda ECO
revision 9, and 25 native QGIS 3.40.6 checks. A CSV produced through the native tree
buttons contained three distinct trees and was ingested by the app with HTTP 200.
No trained weights or author field data are distributed. CNN inference, raster
height calculation, crown metrics and the app's allometric equations are unchanged.


Publication: compatible with Fazenda ECO revision 9. The app receives crown CSVs in Árvore por copa and its processed DBH output in Inventário por DAP. Trained model weights remain external.
