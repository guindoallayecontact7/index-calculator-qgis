# -*- coding: utf-8 -*-
"""Index Calculator V3.5 preprocessing pipeline foundation.
QGIS Processing algorithm: validate input and explicitly harmonize to a reference grid.
This is not radiometric harmonization or cloud/shadow masking.
"""
try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                          QgsProcessingParameterRasterDestination, QgsProcessingParameterEnum,
                          QgsProcessingException)
except Exception:
    QgsProcessingAlgorithm = object

METHODS = ['Nearest neighbour', 'Bilinear', 'Cubic', 'Average', 'Mode']
GDAL_METHODS = [0, 1, 2, 5, 6] # GDAL Warp enum: near, bilinear, cubic, average, mode

if QgsProcessingAlgorithm is not object:
    class AgriculturalPreprocessingPipelineAlgorithm(QgsProcessingAlgorithm):
        INPUT = 'INPUT'; REFERENCE = 'REFERENCE'; METHOD = 'METHOD'; OUTPUT = 'OUTPUT'
        def name(self): return 'agro_preprocessing_pipeline'
        def displayName(self): return 'Agricultural Preprocessing Pipeline - Align and prepare raster'
        def group(self): return 'Preprocessing'
        def groupId(self): return 'preprocessing_pipeline'
        def shortHelpString(self):
            return ('Performs input checks and explicitly reprojects/resamples one raster to a reference raster grid. '
                   'The output uses the reference CRS, extent and target pixel size. Select nearest neighbour for categorical rasters; '
                   'Bilinear/cubic for continuous data. No atmospheric correction, radiometric harmonization, cloud/shadow masking, '
                   'or vegetation-index calculation is performed.')
        def createInstance(self): return AgriculturalPreprocessingPipelineAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, 'Input raster'))
            self.addParameter(QgsProcessingParameterRasterLayer(self.REFERENCE, 'Reference raster / target grid'))
            self.addParameter(QgsProcessingParameterEnum(self.METHOD, 'Resampling method', options=METHODS, defaultValue=1))
            self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, 'Prepared raster'))
        def processAlgorithm(self, parameters, context, feedback):
            source = self.parameterAsRasterLayer(parameters, self.INPUT, context)
            ref = self.parameterAsRasterLayer(parameters, self.REFERENCE, context)
            method = self.parameterAsEnum(parameters, self.METHOD, context)
            output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
            if not source or not source.isValid():
                raise QgsProcessingException('Input raster is invalid or unreadable.')
            if not ref or not ref.isValid():
                raise QgsProcessingException('Reference raster is invalid or unreadable.')
            if source.bandCount() < 1 or ref.bandCount() < 1:
                raise QgsProcessingException('Both rasters must contain at least one band.')
            if source == ref:
                raise QgsProcessingException('Input and reference must be different rasters.')
            if source.crs().isValid() is False or ref.crs().isValid() is False:
                raise QgsProcessingException('Input and reference must have valid CRS definitions.')
            feedback.pushInfo('Index Calculator preprocessing: validating raster inputs...')
            feedback.pushInfo('Input: %s | %s | %s x %s' % (source.name(), source.crs().authid(), source.width(), source.height()))
            feedback.pushInfo('Reference: %s | %s | %s x %s' % (ref.name(), ref.crs().authid(), ref.width(), ref.height()))
            feedback.pushInfo('Resampling: %s' % METHODS[max(0, min(method, len(METHODS)-1))])
            try:
                import processing
                params = {
                    'INPUT': source,
                    'SOURCE_CRS': source.crs(),
                    'TARGET_CRS': ref.crs(),
                    'RESAMPLING': GDAL_METHODS[max(0, min(method, len(GDAL_METHODS)-1))],
                    'NODATA': None,
                    'TARGET_RESOLUTION': abs(ref.rasterUnitsPerPixelX()),
                    'CREATION_OPTIONS': '',
                    'DATA_TYPE': 0,
                    'TARGET_EXTENT': ref.extent(),
                    'TARGET_EXTENT_CRS': ref.crs(),
                    'MULTITHREADING': True,
                    'OUTPUT': output
                }
                processing.run('gdal:warpreproject', params, context=context, feedback=feedback)
            except Exception as exc:
                raise QgsProcessingException('Preprocessing pipeline failed during GDAL Warp. Verify GDAL provider and output path. Details: %s' % exc)
            feedback.pushInfo('Prepared raster created. Source data was not modified.')
            feedback.pushWarning('This pipeline does not perform cloud/shadow masking, atmospheric correction, reflectance scaling, or radiometric cross-sensor harmonization.')
            return {self.OUTPUT: output}
