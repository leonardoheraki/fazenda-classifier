# Fazenda Classifier

Fazenda Classifier is an experimental QGIS plugin for forest inventory. Use it to sample canopy height across plots, measure individual tree crowns from drone imagery, and export georeferenced measurements for analysis in Fazenda ECO or other software.

**Version 1.1.2** · Public inventory edition based on RC17 · Leonardo Heraki · [GPL-2.0-or-later](LICENSE)

## Sampling plots and individual trees

| Workflow | How it works | Output |
| --- | --- | --- |
| Sampling plot | Place, move, and rotate a 100 × 100 m plot before sampling. In each of its 100 sampling windows (1 × 10 m), the plugin finds the highest pixel in the digital surface model (DSM) and subtracts the digital terrain model (DTM) elevation at that same location. | A CSV with one row per sampling point, including height, coordinates, coordinate reference systems, and a validity flag. |
| Individual tree | Select a tree location and trace its crown on the map. The plugin calculates height as DSM minus DTM at the selected point, measures the projected crown area (m²), and finds the greatest distance between two crown vertices (m). Review the tree list before exporting. | A CSV with one row per tree. With an RGB orthophoto, you can also save a georeferenced GeoTIFF masked to each crown at the original image resolution. |

The plot workflow samples **locations**. Several windows can fall within one crown, so counting valid height samples does not give a tree count. The individual-tree workflow records the trees you select. Give each tree a field ID if you plan to join its measurements to field observations.

Crown GeoTIFFs are written to a temporary directory. The tree CSV stores their paths. Copy the images to permanent storage if you need them after the session.

## Installation and inputs

1. Obtain the installable package `fazenda_classifier_1.1.2.zip`. To build it from this repository, run `python scripts/build_plugin.py` from the repository root. The script writes the ZIP to `dist/`.
2. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**, select the package, and install it. Restart QGIS and check that the plugin panel shows **1.1.2**.
3. Use a projected working coordinate reference system with units in metres. Load the DSM and DTM for height measurements, and an RGB orthophoto to export crown images. Check that both elevation rasters use metres and compatible vertical datums. The plugin transforms horizontal coordinates only.

The declared compatibility range is **QGIS 3.36–3.99**. The inventory workflows use QGIS, NumPy, and GDAL. The public edition runs without deep learning libraries and includes neither a species classifier nor trained model weights.

## Using the measurements in Fazenda ECO

For plot analysis, choose the Fazenda ECO CSV profile. It requires at least five valid, finite, positive height measurements per sampling unit. The full sampling report also includes invalid observations, so you can inspect why a plot fell below that threshold. Missing heights remain blank.

For analyses that depend on species, join an independently obtained identification to the tree report using the tree ID. Maximum crown span describes the crown outline. Diameter at breast height (DBH) measures the stem. Estimates of DBH, biomass, and aboveground carbon (AGC), as well as the H5 plot statistic and climate projections, are outside the scope of this plugin.

## Testing and documentation

Version 1.1.2 passed **42 unit tests and 5 QGIS integration tests** on Linux with QGIS 3.40.6 and synthetic data. The tests cover plot placement and rotation, height sampling, crown measurements, GeoTIFF output, and CSV export. Assess measurement accuracy for your study area against independent field data.

- [User guide (Portuguese)](fazenda_classifier/README.txt)
- [CSV fields, units, and export profiles (Portuguese)](fazenda_classifier/CSV_FAZENDA_ECO.md)
- [Test results and reproduction instructions (Portuguese)](fazenda_classifier/VALIDACAO_PUBLICA.txt)
- [QGIS plugin directory](https://plugins.qgis.org/plugins/fazenda_classifier/)
- [Report an issue](https://github.com/leonardoheraki/fazenda-classifier/issues)
