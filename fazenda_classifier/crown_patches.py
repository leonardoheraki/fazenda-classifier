"""Native-resolution crown TIFFs for delimited tree crowns.

The input polygon is already in the raster CRS. Copy a source pixel window
without resampling; mask pixel centres outside the crown and source invalid data.
GDAL is imported only when needed (it is supplied with QGIS).
"""
import math
import os
import tempfile
from pathlib import Path


def write_native_crown_tiff(source_path, polygon_wkb, output_path, *,
                           raster_crs_wkt=None, tree_id="", reference_tiff=""):
    """Write one self-contained GeoTIFF atomically, without altering its source.

    Band count, pixel type, valid in-crown samples and affine pixel grid are
    retained. Invalid/outside pixels are zero-filled AND marked in an internal
    validity mask, so converting to RGB cannot bring neighbouring crowns back.
    No inference, scaling to 128 px or species assignment takes place here.
    """
    from osgeo import gdal, ogr, osr
    import numpy as np

    destination = Path(output_path)
    if os.path.realpath(str(source_path)) == os.path.realpath(str(destination)):
        raise ValueError("O TIFF da copa não pode substituir a ortofoto de origem.")
    if not destination.parent.is_dir():
        raise ValueError("A pasta temporária da copa não está disponível.")

    def write(staging):
        source = output = cut_mask = vectors = None
        source_band = target_band = output_mask = None
        try:
            source = gdal.OpenEx(str(source_path), gdal.OF_RASTER | gdal.OF_READONLY)
            if source is None or source.RasterCount < 3:
                raise ValueError("Não foi possível abrir a ortofoto RGB com GDAL.")
            transform = source.GetGeoTransform(can_return_null=True)
            inverse = gdal.InvGeoTransform(transform) if transform else None
            projection = raster_crs_wkt or source.GetProjection()
            if inverse is None or not projection:
                raise ValueError("A ortofoto precisa ter SRC e grade georreferenciada válidos.")
            data_type = source.GetRasterBand(1).DataType
            if any(source.GetRasterBand(i).DataType != data_type
                   for i in range(2, source.RasterCount + 1)):
                raise ValueError("As bandas da ortofoto têm tipos diferentes; o TIFF não será convertido.")
            crown = ogr.CreateGeometryFromWkb(bytes(polygon_wkb))
            if (crown is None or crown.IsEmpty() or not crown.IsValid()
                    or ogr.GT_Flatten(crown.GetGeometryType()) != ogr.wkbPolygon
                    or crown.GetArea() <= 0):
                raise ValueError("O polígono da copa é inválido.")
            pixels = [gdal.ApplyGeoTransform(inverse, *ring.GetPoint(i)[:2])
                      for ring in (crown.GetGeometryRef(r) for r in range(crown.GetGeometryCount()))
                      for i in range(ring.GetPointCount())]
            if not pixels or not all(math.isfinite(v) for p in pixels for v in p):
                raise ValueError("A copa contém coordenadas inválidas.")
            min_x, min_y = map(min, zip(*pixels))
            max_x, max_y = map(max, zip(*pixels))
            tolerance = 1e-6  # Floating-point noise in pixel coordinates only.
            if (min_x < -tolerance or min_y < -tolerance
                    or max_x > source.RasterXSize + tolerance
                    or max_y > source.RasterYSize + tolerance):
                raise ValueError("A copa ultrapassa a cobertura da ortofoto RGB; confira a delimitação.")
            x0 = max(0, math.floor(min_x + tolerance))
            y0 = max(0, math.floor(min_y + tolerance))
            x1 = min(source.RasterXSize, math.ceil(max_x - tolerance))
            y1 = min(source.RasterYSize, math.ceil(max_y - tolerance))
            width, height = x1 - x0, y1 - y0
            if width <= 0 or height <= 0:
                raise ValueError("A copa não contém uma janela válida de pixels da ortofoto.")
            origin = gdal.ApplyGeoTransform(transform, x0, y0)
            cropped_transform = (origin[0], transform[1], transform[2],
                                 origin[1], transform[4], transform[5])

            # A tiled disk mask and block reads also support large native crowns
            # without allocating the complete multi-band image in memory.
            driver = gdal.GetDriverByName("GTiff")
            cut_mask = driver.Create(str(staging / "mask.tif"), width, height, 1,
                                     gdal.GDT_Byte, options=["TILED=YES", "COMPRESS=LZW"])
            if cut_mask is None:
                raise RuntimeError("Não foi possível criar a máscara temporária da copa.")
            cut_mask.SetGeoTransform(cropped_transform)
            cut_mask.SetProjection(projection)
            spatial_ref = osr.SpatialReference()
            if spatial_ref.ImportFromWkt(projection) != 0:
                raise ValueError("O SRC da ortofoto RGB é inválido.")
            vectors = ogr.GetDriverByName("Memory").CreateDataSource("")
            layer = vectors.CreateLayer("crown", srs=spatial_ref, geom_type=ogr.wkbPolygon)
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(crown)
            if layer.CreateFeature(feature) != 0 or gdal.RasterizeLayer(
                    cut_mask, [1], layer, burn_values=[255]) != 0:
                raise RuntimeError("Não foi possível rasterizar a copa delimitada.")

            output = driver.Create(str(staging / "crown.tif"), width, height,
                                   source.RasterCount, data_type,
                                   options=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"])
            if output is None:
                raise RuntimeError("Não foi possível criar o TIFF temporário da copa.")
            output.SetGeoTransform(cropped_transform)
            output.SetProjection(projection)
            # Do not copy source statistics: they no longer describe the crop.
            output.SetMetadata({
                "FAZENDA_PATCH_TYPE": "copa_delimitada_resolucao_nativa",
                "FAZENDA_SOURCE": str(source_path),
                "FAZENDA_TREE_ID": str(tree_id),
                "FAZENDA_REFERENCE_TIFF": str(reference_tiff),
                "FAZENDA_CROWN_WKT": crown.ExportToWkt(),
                "FAZENDA_RESAMPLING": "none_native_pixel_window",
                "FAZENDA_MASK_RULE": "pixel_center_inside_crown_and_source_valid",
                "FAZENDA_SOURCE_WINDOW": f"{x0},{y0},{width},{height}",
            })
            # Explicit for GDAL < 3.9 as well; restore this thread's setting.
            setting = gdal.GetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK")
            try:
                gdal.SetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK", "YES")
                if output.CreateMaskBand(gdal.GMF_PER_DATASET) != 0:
                    raise RuntimeError("Não foi possível gravar a máscara interna do TIFF.")
            finally:
                gdal.SetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK", setting)
            output_mask = output.GetRasterBand(1).GetMaskBand()
            for index in range(1, source.RasterCount + 1):
                source_band = source.GetRasterBand(index)
                target_band = output.GetRasterBand(index)
                target_band.SetColorInterpretation(source_band.GetColorInterpretation())
                target_band.SetDescription(source_band.GetDescription())
                if source_band.GetScale() is not None:
                    target_band.SetScale(source_band.GetScale())
                if source_band.GetOffset() is not None:
                    target_band.SetOffset(source_band.GetOffset())
                target_band.SetUnitType(source_band.GetUnitType())

            valid_count = 0
            for row in range(0, height, 256):
                for column in range(0, width, 256):
                    nx, ny = min(256, width-column), min(256, height-row)
                    keep = cut_mask.GetRasterBand(1).ReadAsArray(column, row, nx, ny) != 0
                    for index in range(1, source.RasterCount + 1):
                        valid = source.GetRasterBand(index).GetMaskBand().ReadAsArray(
                            x0+column, y0+row, nx, ny)
                        if valid is None:
                            raise RuntimeError("Falha ao ler a validade dos pixels da ortofoto.")
                        keep &= valid != 0
                    valid_count += int(np.count_nonzero(keep))
                    if output_mask.WriteArray(np.where(keep, 255, 0).astype(np.uint8), column, row) != 0:
                        raise RuntimeError("Falha ao gravar a máscara interna da copa.")
                    for index in range(1, source.RasterCount + 1):
                        values = source.GetRasterBand(index).ReadAsArray(x0+column, y0+row, nx, ny)
                        if values is None:
                            raise RuntimeError("Falha ao ler os pixels da ortofoto.")
                        values[~keep] = 0
                        if output.GetRasterBand(index).WriteArray(values, column, row) != 0:
                            raise RuntimeError("Falha ao gravar os pixels da copa.")
            if not valid_count:
                raise ValueError("A copa não contém centros de pixels válidos da ortofoto RGB.")
            if output.FlushCache() not in (None, 0):
                raise RuntimeError("Falha ao concluir a gravação do TIFF da copa.")
            return dict(path=str(destination), width=width, height=height,
                        valid_pixels=valid_count, geotransform=cropped_transform)
        finally:
            # Release all TIFF handles before os.replace/cleanup on Windows.
            source_band = target_band = output_mask = None
            output = cut_mask = vectors = source = None

    with tempfile.TemporaryDirectory(prefix=".copa_tiff_", dir=destination.parent) as directory:
        staging = Path(directory)
        result = write(staging)
        os.replace(staging / "crown.tif", destination)
    return result
