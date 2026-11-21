# -*- coding: utf-8 -*-
"""Index Calculator Pro Cloud & Shadow Intelligence (GDAL/NumPy runtime)."""
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                      QgsProcessingParameterRasterDestination, QgsProcessingException)



class _BaseCloudMask(QgsProcessingAlgorithm):
    IMAGE = 'IMAGE'
    QA = 'QA'
    MASK_OUT = 'MASK_OUT'
    CLEAN_OUT = 'CLEAN_OUT'


    def _write_outputs(self, image_path, qa_path, mask_array, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as exc:
            raise QgsProcessingException('GDAL/NumPy required in the QGIS Python environment: ' + str(exc))
        image_ds = gdal.Open(image_path, gdal.GA_ReadOnly)
        qa_ds = gdal.Open(qa_path, gdal.GA_ReadOnly)
        if image_ds is None or qa_ds is None:
            raise QgsProcessingException('Cannot open one or both raster inputs with GDAL.')
        if (image_ds.RasterXSize != qa_ds.RasterXSize or image_ds.RasterYSize != qa_ds.RasterYSize or
            image_ds.GetGeoTransform() != qa_ds.GetGeoTransform() or image_ds.GetProjection() != qa_ds.GetProjection()):
            raise QgsProcessingException('Image and QA/SCL raster grids must match exactly (CRS, extent, dimensions, geotransform). Align first.')
        mask_out = self.parameterAsOutputLayer(parameters, self.MASK_OUT, context)
        clean_out = self.parameterAsOutputLayer(parameters, self.CLEAN_OUT, context)
        driver = gdal.GetDriverByName('GTiff')
        mask_ds = driver.Create(mask_out, image_ds.RasterXSize, image_ds.RasterYSize, 1, gdal.GDT_Byte, options=['COMPRESS=LZW'])
        mask_ds.SetGeoTransform(image_ds.GetGeoTransform()); mask_ds.SetProjection(image_ds.GetProjection())
        mb = mask_ds.GetRasterBand(1); mb.WriteArray(mask_array.astype(np.uint8)); mb.SetNoDataValue(0)
        mask_ds.SetMetadata({'INDEX_CALCULATOR_PRO_MASK_CONVENTION':'1=clear/retained; 0=masked'})
        mask_ds.FlushCache(); mask_ds = None
        # Clean image is Float32 to support a consistent -9999 nodata sentinel across input types.
        clean_ds = driver.Create(clean_out, image_ds.RasterXSize, image_ds.RasterYSize, image_ds.RasterCount, gdal.GDT_Float32, options=['COMPRESS=LZW'])
        clean_ds.SetGeoTransform(image_ds.GetGeoTransform()); clean_ds.SetProjection(image_ds.GetProjection())
        for b in range(1, image_ds.RasterCount + 1):
            if feedback.isCanceled(): break
            src = image_ds.GetRasterBand(b)
            arr = src.ReadAsArray().astype(np.float32)
            nodata = src.GetNoDataValue()
            valid = mask_array.astype(bool)
            if nodata is not None:
                valid &= (arr != nodata)
            cleaned = np.where(valid, arr, -9999.0)
            dst = clean_ds.GetRasterBand(b); dst.WriteArray(cleaned); dst.SetNoDataValue(-9999.0)
            description = src.GetDescription()
            if description: dst.SetDescription(description)
            feedback.setProgress(int(100 * b / image_ds.RasterCount))
        clean_ds.FlushCache(); clean_ds = None; image_ds = None; qa_ds = None
        return {self.MASK_OUT: mask_out, self.CLEAN_OUT: clean_out}


class Sentinel2SCLCloudShadowMaskAlgorithm(_BaseCloudMask):
    """Masks Sentinel-2 SCL classes not selected as clear-surface classes."""
    def name(self): return 'ic_sentinel2_scl_cloud_shadow_mask'
    def displayName(self): return 'Sentinel-2 SCL - Cloud/Shadow Mask'
    def group(self): return 'Clouds and shadows'
    def groupId(self): return 'cloud_shadow_intelligence'
    def shortHelpString(self):
        return ('Uses the Sentinel-2 Scene Classification Layer (SCL). Default clear classes retained: 4 vegetation, 5 bare soil, 6 water; class 7 is masked conservatively. '
                'Other classes are masked. Input image and SCL must be exactly grid-aligned. Clean output is Float32 with NoData=-9999.')
    def createInstance(self): return Sentinel2SCLCloudShadowMaskAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.IMAGE, 'Sentinel-2 image band or multiband raster'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.QA, 'Sentinel-2 SCL classification raster'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.MASK_OUT, 'Clear-pixel mask (1=retained, 0=masked)'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.CLEAN_OUT, 'Cloud/shadow-masked image (Float32, NoData=-9999)'))
    def processAlgorithm(self, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as exc: raise QgsProcessingException('GDAL/NumPy required: ' + str(exc))
        image = self.parameterAsRasterLayer(parameters, self.IMAGE, context)
        scl = self.parameterAsRasterLayer(parameters, self.QA, context)
        if image is None or scl is None: raise QgsProcessingException('Invalid input raster.')
        im_path = image.source().split('|')[0]; scl_path = scl.source().split('|')[0]
        qa_ds = gdal.Open(scl_path)
        if qa_ds is None: raise QgsProcessingException('Cannot read SCL raster.')
        scl_arr = qa_ds.GetRasterBand(1).ReadAsArray()
        # Default retain: classes 4,5,6,7. SCL 2 (dark area), 3 (shadow), 8-10 (cloud/cirrus), 11 (snow) masked.
        mask = np.isin(scl_arr, [4, 5, 6])
        qa_ds = None
        return self._write_outputs(im_path, scl_path, mask, parameters, context, feedback)


class LandsatQAPixelCloudShadowMaskAlgorithm(_BaseCloudMask):
    """Masks Landsat Collection 2 QA_PIXEL fill, cloud, shadow, snow and cirrus bits."""
    def name(self): return 'ic_landsat_qa_pixel_cloud_shadow_mask'
    def displayName(self): return 'Landsat 8/9 QA_PIXEL - Cloud/Shadow Mask'
    def group(self): return 'Clouds and shadows'
    def groupId(self): return 'cloud_shadow_intelligence'
    def shortHelpString(self):
        return ('Masks Landsat Collection 2 QA_PIXEL bits: fill (0), dilated cloud (1), cirrus (2), cloud (3), cloud shadow (4), snow (5). '
                'Retains pixels where all selected bits are clear. Input image and QA_PIXEL must be exactly grid-aligned. Clean output Float32, NoData=-9999.')
    def createInstance(self): return LandsatQAPixelCloudShadowMaskAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.IMAGE, 'Landsat 8/9 image band or multiband raster'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.QA, 'Landsat Collection 2 QA_PIXEL raster'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.MASK_OUT, 'Clear-pixel mask (1=retained, 0=masked)'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.CLEAN_OUT, 'Cloud/shadow-masked image (Float32, NoData=-9999)'))
    def processAlgorithm(self, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as exc: raise QgsProcessingException('GDAL/NumPy required: ' + str(exc))
        image = self.parameterAsRasterLayer(parameters, self.IMAGE, context)
        qa = self.parameterAsRasterLayer(parameters, self.QA, context)
        if image is None or qa is None: raise QgsProcessingException('Invalid input raster.')
        im_path = image.source().split('|')[0]; qa_path = qa.source().split('|')[0]
        qa_ds = gdal.Open(qa_path)
        if qa_ds is None: raise QgsProcessingException('Cannot read QA_PIXEL raster.')
        qa_arr = qa_ds.GetRasterBand(1).ReadAsArray().astype(np.uint32)
        # Collection 2 QA_PIXEL flags: 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 shadow, 5 snow.
        bad_bits = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        mask = (qa_arr & bad_bits) == 0
        qa_ds = None
        return self._write_outputs(im_path, qa_path, mask, parameters, context, feedback)

class CloudMaskSummaryAlgorithm(QgsProcessingAlgorithm):
    """Creates a simple HTML summary from a binary clear-pixel mask."""
    MASK = 'MASK'
    REPORT = 'REPORT'
    def name(self): return 'ic_cloud_mask_summary'
    def displayName(self): return 'Cloud Mask - Coverage Summary Report'
    def group(self): return 'Clouds and shadows'
    def groupId(self): return 'cloud_shadow_intelligence'
    def shortHelpString(self):
        return 'Summarizes a binary clear-pixel mask (1 retained, 0 masked), including clear and masked pixel counts and percentages. It does not identify clouds by itself.'
    def createInstance(self): return CloudMaskSummaryAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.MASK, 'Binary clear-pixel mask (1=clear, 0=masked)'))
        from qgis.core import QgsProcessingParameterFileDestination
        self.addParameter(QgsProcessingParameterFileDestination(self.REPORT, 'HTML coverage report', 'HTML files (*.html)'))
    def processAlgorithm(self, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as exc: raise QgsProcessingException('GDAL/NumPy required: ' + str(exc))
        layer = self.parameterAsRasterLayer(parameters, self.MASK, context)
        if layer is None: raise QgsProcessingException('Invalid mask raster.')
        ds = gdal.Open(layer.source().split('|')[0])
        if ds is None: raise QgsProcessingException('Cannot read mask raster.')
        arr = ds.GetRasterBand(1).ReadAsArray()
        total = int(arr.size); clear = int(np.count_nonzero(arr == 1)); masked = total - clear
        clear_pct = 100.0 * clear / total if total else 0.0
        masked_pct = 100.0 * masked / total if total else 0.0
        report = self.parameterAsFileOutput(parameters, self.REPORT, context)
        import html, os, datetime
        os.makedirs(os.path.dirname(report) or '.', exist_ok=True)
        title = 'Index Calculator Pro - Cloud Mask Coverage Summary'
        body = ('<!DOCTYPE html><html><head><meta charset="utf-8"><title>'+title+'</title>'
               '<style>body{font-family:Arial,sans-serif;margin:2rem;color:#203040}table{border-collapse:collapse}td,th{padding:.7rem;border:1px solid #ccc}th{background:#f0f3f5}</style></head><body>'
               '<h1>'+title+'</h1><p>Generated: '+html.escape(datetime.datetime.now().isoformat(timespec='seconds'))+'</p>'
               '<table><tr><th>Metric</th><th>Value</th></tr>'
               '<tr><td>Total pixels</td><td>'+str(total)+'</td></tr>'
               '<tr><td>Clear/retained pixels</td><td>'+str(clear)+'</td></tr>'
               '<tr><td>Masked pixels</td><td>'+str(masked)+'</td></tr>'
               '<tr><td>Clear coverage</td><td>'+format(clear_pct,'.2f')+'%</td></tr>'
               '<tr><td>Masked coverage</td><td>'+format(masked_pct,'.2f')+'%</td></tr></table>'
               '<p>Interpretation: this report summarizes an existing binary mask. Its reliability depends on the source QA/SCL classification and prior processing.</p></body></html>')
        with open(report, 'w', encoding='utf-8') as f: f.write(body)
        ds = None
        return {self.REPORT: report}
