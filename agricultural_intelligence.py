# -*- coding: utf-8 -*-
"""Index Calculator V3.7 Agricultural Intelligence preprocessing algorithm.
Provides a reproducible combined QA-mask + raster-cleaning workflow.
No atmospheric correction, radiometric harmonization, index calculation, or crop diagnosis.
"""
try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
        QgsProcessingParameterEnum, QgsProcessingParameterRasterDestination,
        QgsProcessingParameterFileDestination, QgsProcessingException)
except Exception:
    QgsProcessingAlgorithm = object

METHODS = ['Sentinel-2 SCL', 'Landsat Collection 2 QA_PIXEL']


def build_clear_mask(qa_array, method):
    """Pure NumPy mask helper: 1=clear/retained, 0=masked."""
    import numpy as np
    if method == 0:
        # Conservative SCL classes: vegetation (4), bare soil (5), water (6).
        return np.isin(qa_array, [4, 5, 6]).astype(np.uint8)
    qa = qa_array.astype(np.uint32, copy=False)
    bad_bits = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5))
    return ((qa & bad_bits) == 0).astype(np.uint8)



if QgsProcessingAlgorithm is not object:
    class AgriculturalIntelligencePipelineAlgorithm(QgsProcessingAlgorithm):
        IMAGE = 'IMAGE'; QA = 'QA'; METHOD = 'METHOD'; MASK = 'MASK'; CLEAN = 'CLEAN'; REPORT = 'REPORT'
        def name(self): return 'ic_agricultural_intelligence_pipeline'
        def displayName(self): return 'QA Mask and Clean Raster'
        def group(self): return 'Agricultural preprocessing'
        def groupId(self): return 'agricultural_intelligence'
        def shortHelpString(self):
            return ('Combined, explicit QA masking and raster cleaning pipeline. Sentinel-2 SCL retains classes 4, 5 and 6; '
                    'Landsat QA_PIXEL masks bits 0-5. Image and QA rasters must have identical grids. '
                    'Outputs a mask (1 clear, 0 masked, 255 NoData), cleaned Float32 raster (-9999 NoData), and HTML report. '
                    'This is not atmospheric correction, radiometric harmonization, index calculation or crop diagnosis.')
        def createInstance(self): return AgriculturalIntelligencePipelineAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.IMAGE, 'Input image (single- or multiband raster)'))
            self.addParameter(QgsProcessingParameterRasterLayer(self.QA, 'QA/SCL raster'))
            self.addParameter(QgsProcessingParameterEnum(self.METHOD, 'QA mask interpretation', options=METHODS, defaultValue=0))
            self.addParameter(QgsProcessingParameterRasterDestination(self.MASK, 'Clear-pixel mask (1 clear, 0 masked, 255 NoData)'))
            self.addParameter(QgsProcessingParameterRasterDestination(self.CLEAN, 'Cleaned raster (Float32, NoData=-9999)'))
            self.addParameter(QgsProcessingParameterFileDestination(self.REPORT, 'HTML QA summary', 'HTML files (*.html)'))
        def processAlgorithm(self, parameters, context, feedback):
            try:
                from osgeo import gdal
                import numpy as np
                import html, os, datetime
            except Exception as exc:
                raise QgsProcessingException('GDAL/NumPy required in QGIS environment: %s' % exc)
            image_layer = self.parameterAsRasterLayer(parameters, self.IMAGE, context)
            qa_layer = self.parameterAsRasterLayer(parameters, self.QA, context)
            method = self.parameterAsEnum(parameters, self.METHOD, context)
            mask_path = self.parameterAsOutputLayer(parameters, self.MASK, context)
            clean_path = self.parameterAsOutputLayer(parameters, self.CLEAN, context)
            report_path = self.parameterAsFileOutput(parameters, self.REPORT, context)
            if not image_layer or not image_layer.isValid() or not qa_layer or not qa_layer.isValid():
                raise QgsProcessingException('Both image and QA/SCL rasters must be valid.')
            image_path = image_layer.source().split('|')[0]
            qa_path = qa_layer.source().split('|')[0]
            img = gdal.Open(image_path, gdal.GA_ReadOnly); qa = gdal.Open(qa_path, gdal.GA_ReadOnly)
            if img is None or qa is None: raise QgsProcessingException('GDAL cannot open the image or QA input.')
            if (img.RasterXSize != qa.RasterXSize or img.RasterYSize != qa.RasterYSize or
                img.GetGeoTransform() != qa.GetGeoTransform() or img.GetProjection() != qa.GetProjection()):
                raise QgsProcessingException('Image and QA rasters must be exactly aligned. Run raster harmonization first.')
            qa_band = qa.GetRasterBand(1)
            qa_array = qa_band.ReadAsArray()
            mask = build_clear_mask(qa_array, method)
            qa_nodata = qa_band.GetNoDataValue()
            qa_valid = np.ones(qa_array.shape, dtype=bool)
            if qa_nodata is not None:
                qa_valid &= (qa_array != qa_nodata)
                mask[~qa_valid] = 0
            driver = gdal.GetDriverByName('GTiff')
            mask_ds = driver.Create(mask_path, img.RasterXSize, img.RasterYSize, 1, gdal.GDT_Byte, options=['COMPRESS=LZW'])
            mask_ds.SetGeoTransform(img.GetGeoTransform()); mask_ds.SetProjection(img.GetProjection())
            mask_write = mask.copy(); mask_write[~qa_valid] = 255
            mb = mask_ds.GetRasterBand(1); mb.WriteArray(mask_write); mb.SetNoDataValue(255)
            mask_ds.SetMetadata({'AGROGEO_AI_MASK_CONVENTION':'1=clear/retained; 0=masked; 255=NoData'})
            mask_ds.FlushCache(); mask_ds = None
            clean_ds = driver.Create(clean_path, img.RasterXSize, img.RasterYSize, img.RasterCount, gdal.GDT_Float32, options=['COMPRESS=LZW'])
            clean_ds.SetGeoTransform(img.GetGeoTransform()); clean_ds.SetProjection(img.GetProjection())
            valid_count = clear_count = masked_count = 0
            for band_no in range(1, img.RasterCount + 1):
                if feedback.isCanceled():
                    clean_ds = None; img = None; qa = None
                    raise QgsProcessingException('Processing cancelled by user.')
                src_band = img.GetRasterBand(band_no)
                arr = src_band.ReadAsArray().astype(np.float32)
                valid = np.isfinite(arr)
                nd = src_band.GetNoDataValue()
                if nd is not None: valid &= (arr != nd)
                if band_no == 1:
                    valid_count = int(np.count_nonzero(valid & qa_valid))
                    clear_count = int(np.count_nonzero(valid & qa_valid & (mask == 1)))
                    masked_count = int(np.count_nonzero(valid & qa_valid & (mask == 0)))
                cleaned = np.where(valid & (mask == 1), arr, -9999.0)
                dst = clean_ds.GetRasterBand(band_no); dst.WriteArray(cleaned); dst.SetNoDataValue(-9999.0)
                if src_band.GetDescription(): dst.SetDescription(src_band.GetDescription())
                feedback.setProgress(int(100 * band_no / img.RasterCount))
            clean_ds.FlushCache(); clean_ds = None; img = None; qa = None
            clear_pct = 100.0 * clear_count / valid_count if valid_count else 0.0
            masked_pct = 100.0 * masked_count / valid_count if valid_count else 0.0
            method_name = METHODS[max(0, min(method, len(METHODS)-1))]
            os.makedirs(os.path.dirname(report_path) or '.', exist_ok=True)
            report = ('<!doctype html><html><head><meta charset="utf-8"><title>Index Calculator QA report</title>'
                '<style>body{font-family:Arial,sans-serif;margin:2em;color:#243447}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ddd}th{background:#f3f5f7}</style></head><body>'
                '<h1>Index Calculator - QA Mask and Clean Raster</h1><p>Generated: '+html.escape(datetime.datetime.now().isoformat(timespec='seconds'))+'</p>'
                '<table><tr><th>Metric</th><th>Value</th></tr><tr><td>Mask method</td><td>'+html.escape(method_name)+'</td></tr>'
                '<tr><td>Valid image pixels (band 1)</td><td>'+str(valid_count)+'</td></tr><tr><td>Clear/retained pixels</td><td>'+str(clear_count)+'</td></tr>'
                '<tr><td>Masked pixels</td><td>'+str(masked_count)+'</td></tr><tr><td>Clear coverage</td><td>'+format(clear_pct,'.2f')+'%</td></tr>'
                '<tr><td>Masked coverage</td><td>'+format(masked_pct,'.2f')+'%</td></tr></table>'
                '<h2>Mask definitions</h2><p>Sentinel-2 SCL retains classes 4 (vegetation), 5 (bare soil), 6 (water). Other classes are masked. Landsat QA_PIXEL masks bits 0-5 (fill, dilated cloud, cirrus, cloud, cloud shadow, snow).</p>'
                '<p>QA mask reliability depends on the source classification. This workflow does not perform atmospheric correction, reflectance scaling, radiometric cross-sensor harmonization, index calculation or crop diagnosis.</p></body></html>')
            with open(report_path, 'w', encoding='utf-8') as f: f.write(report)
            feedback.pushInfo('Pipeline complete: QA mask, cleaned raster and HTML report created.')
            return {self.MASK: mask_path, self.CLEAN: clean_path, self.REPORT: report_path}
