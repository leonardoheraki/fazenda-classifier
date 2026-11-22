"""Real GeoTIFF pixels, masks, native grid and atomic failure checks (GDAL)."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
except ImportError:
    gdal = None

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("crown_patches_under_test", ROOT / "crown_patches.py")
crowns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crowns)


@unittest.skipIf(gdal is None, "GDAL é fornecido no Python do QGIS")
class CrownTiffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / "original.tif"
        self.output = self.folder / "copa.tif"
        self.transform = (542000, .05, 0, 7192000, 0, -.05)
        self.srs = osr.SpatialReference()
        self.srs.ImportFromEPSG(31982)

    def make_source(self, *, alpha=False, wide=False, nodata=False, rotated=False):
        if rotated:
            self.transform = (542000, .07, .015, 7192000, .01, -.04)
        bands = 4 if alpha else 3
        data_type = gdal.GDT_UInt16 if wide else gdal.GDT_Byte
        rows, cols = np.indices((320, 360))
        base = (rows + cols) % 200 + 20
        self.values = np.stack([base + i for i in range(3)]).astype(np.uint16 if wide else np.uint8)
        if wide:
            self.values += 10000
        if alpha:
            a = np.full((1, 320, 360), 255, dtype=np.uint8)
            a[:, 80:90, 80:90] = 0
            self.values = np.concatenate([self.values, a])
        if nodata:
            self.values[:, 80:90, 80:90] = 0
        source = gdal.GetDriverByName("GTiff").Create(str(self.source), 360, 320, bands, data_type)
        source.SetGeoTransform(self.transform)
        source.SetProjection(self.srs.ExportToWkt())
        interpretations = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand, gdal.GCI_AlphaBand)
        for i in range(bands):
            band = source.GetRasterBand(i+1)
            band.WriteArray(self.values[i])
            band.SetColorInterpretation(interpretations[i])
            if nodata:
                band.SetNoDataValue(0)
        band = source = None
        self.initial_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def polygon(self, coordinates=((32, 24), (272, 24), (32, 224))):
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in (*coordinates, coordinates[0]):
            ring.AddPoint_2D(*gdal.ApplyGeoTransform(self.transform, x, y))
        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)
        return polygon.ExportToWkb()

    def export(self, **options):
        return crowns.write_native_crown_tiff(str(self.source), self.polygon(), self.output,
                                             tree_id="ARV_001", reference_tiff="arvore_1.tif", **options)

    def test_native_samples_are_exact_and_neighbours_are_zero_and_masked(self):
        self.make_source()
        result = self.export()
        self.assertEqual((result["width"], result["height"]), (240, 200))
        output = gdal.Open(str(self.output))
        self.assertEqual(output.GetGeoTransform(), (542001.6, .05, 0, 7191998.8, 0, -.05))
        self.assertEqual(output.GetSpatialRef().GetAuthorityCode(None), "31982")
        self.assertEqual(output.GetMetadata("IMAGE_STRUCTURE")["COMPRESSION"], "LZW")
        self.assertEqual(output.GetMetadataItem("FAZENDA_RESAMPLING"), "none_native_pixel_window")
        self.assertEqual(output.GetMetadataItem("FAZENDA_TREE_ID"), "ARV_001")
        self.assertEqual(output.GetMetadataItem("FAZENDA_REFERENCE_TIFF"), "arvore_1.tif")
        values = output.ReadAsArray()
        mask = output.GetRasterBand(1).GetMaskBand().ReadAsArray()
        self.assertTrue(np.any(mask == 0) and np.any(mask == 255))
        self.assertEqual(mask[0, 0], 255)
        self.assertEqual(mask[-1, -1], 0)
        expected = self.values[:, 24:224, 32:272]
        np.testing.assert_array_equal(values[:, mask != 0], expected[:, mask != 0])
        self.assertTrue(np.all(values[:, mask == 0] == 0))
        self.assertTrue(output.GetRasterBand(1).GetMaskFlags() & gdal.GMF_PER_DATASET)
        output = None
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.initial_hash)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["copa.tif", "original.tif"])

    def test_uint16_bit_depth_is_not_scaled_to_rgb_byte(self):
        self.make_source(wide=True)
        self.export()
        output = gdal.Open(str(self.output))
        self.assertEqual(output.GetRasterBand(1).DataType, gdal.GDT_UInt16)
        self.assertGreater(output.ReadAsArray().max(), 10000)
        self.assertEqual(int(output.GetRasterBand(1).ReadAsArray()[0, 0]), int(self.values[0, 24, 32]))
        output = None

    def test_rotated_nonsquare_source_pixels_keep_the_affine_grid(self):
        self.make_source(rotated=True)
        result = self.export()
        self.assertEqual((result["width"], result["height"]), (240, 200))
        output = gdal.Open(str(self.output))
        origin = gdal.ApplyGeoTransform(self.transform, 32, 24)
        expected = (origin[0], .07, .015, origin[1], .01, -.04)
        np.testing.assert_allclose(output.GetGeoTransform(), expected, rtol=0, atol=1e-8)
        np.testing.assert_array_equal(output.ReadAsArray()[:, 0, 0], self.values[:, 24, 32])
        output = None

    def test_original_alpha_and_nodata_are_respected(self):
        for alpha, nodata in ((True, False), (False, True)):
            with self.subTest(alpha=alpha, nodata=nodata):
                self.make_source(alpha=alpha, nodata=nodata)
                self.export()
                output = gdal.Open(str(self.output))
                self.assertEqual(output.RasterCount, 4 if alpha else 3)
                self.assertEqual(int(output.GetRasterBand(1).GetMaskBand().ReadAsArray()[56, 48]), 0)
                self.assertTrue(np.all(output.ReadAsArray()[:, 56, 48] == 0))
                if alpha:
                    self.assertEqual(output.GetRasterBand(4).GetColorInterpretation(), gdal.GCI_AlphaBand)
                output = None

    def test_outside_crown_and_empty_source_do_not_replace_an_existing_file(self):
        self.make_source()
        self.output.write_bytes(b"previous crown")
        with self.assertRaisesRegex(ValueError, "ultrapassa"):
            crowns.write_native_crown_tiff(str(self.source), self.polygon(((-1, 20), (40, 20), (20, 40))), self.output)
        self.assertEqual(self.output.read_bytes(), b"previous crown")
        source = gdal.Open(str(self.source), gdal.GA_Update)
        for i in range(1, 4):
            band = source.GetRasterBand(i)
            band.Fill(0)
            band.SetNoDataValue(0)
        band = source = None
        with self.assertRaisesRegex(ValueError, "centros de pixels válidos"):
            self.export()
        self.assertEqual(self.output.read_bytes(), b"previous crown")
        self.assertFalse(any(p.name.startswith(".copa_tiff_") for p in self.folder.iterdir()))

    def test_failure_during_final_rename_keeps_previous_file(self):
        self.make_source()
        self.output.write_bytes(b"previous crown")
        with patch.object(crowns.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.export()
        self.assertEqual(self.output.read_bytes(), b"previous crown")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["copa.tif", "original.tif"])

    def test_source_cannot_be_used_as_destination(self):
        self.make_source()
        with self.assertRaisesRegex(ValueError, "substituir a ortofoto"):
            crowns.write_native_crown_tiff(str(self.source), self.polygon(), self.source)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.initial_hash)


if __name__ == "__main__":
    unittest.main()
