"""Index Calculator Pro explicit raster harmonization to a reference grid."""
try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                          QgsProcessingParameterRasterDestination, QgsProcessingParameterEnum,
                          QgsProcessingException)
except Exception:
    QgsProcessingAlgorithm = object

RESAMPLING = ['Nearest neighbour', 'Bilinear', 'Cubic', 'Average', 'Mode']
# GDAL Warp enum values: near=0, bilinear=1, cubic=2, average=5, mode=6
GDAL_RESAMPLING = [0, 1, 2, 5, 6]

if QgsProcessingAlgorithm is not object:
    class RasterHarmonizeToReferenceAlgorithm(QgsProcessingAlgorithm):
        INPUT = 'INPUT'; REFERENCE = 'REFERENCE'; RESAMPLING = 'RESAMPLING'; OUTPUT = 'OUTPUT'
        def name(self): return 'raster_harmonize_to_reference'
        def displayName(self): return 'Raster Harmonization - Align to reference grid'
        def group(self): return 'Raster alignment'
        def groupId(self): return 'raster_harmonization'
        def shortHelpString(self):
            return ('Reprojects/resamples the input raster to the reference raster CRS, extent, and pixel size. '
                    'Resampling is explicit. Use Nearest for categorical data; Bilinear/Cubic for continuous imagery. '
                    'This operation creates a new raster and does not modify source data.')
        def createInstance(self): return RasterHarmonizeToReferenceAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, 'Raster to harmonize'))
            self.addParameter(QgsProcessingParameterRasterLayer(self.REFERENCE, 'Reference raster/grid'))
            self.addParameter(QgsProcessingParameterEnum(self.RESAMPLING, 'Resampling method', options=RESAMPLING, defaultValue=1))
            self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, 'Harmonized output raster'))
        def processAlgorithm(self, parameters, context, feedback):
            source = self.parameterAsRasterLayer(parameters, self.INPUT, context)
            ref = self.parameterAsRasterLayer(parameters, self.REFERENCE, context)
            method_index = self.parameterAsEnum(parameters, self.RESAMPLING, context)
            output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
            if not source or not source.isValid(): raise QgsProcessingException('Input raster is invalid.')
            if not ref or not ref.isValid(): raise QgsProcessingException('Reference raster is invalid.')
            if source == ref: raise QgsProcessingException('Input and reference rasters must be different layers.')
            rx, ry = ref.rasterUnitsPerPixelX(), ref.rasterUnitsPerPixelY()
            if abs(abs(rx)-abs(ry)) > max(abs(rx),abs(ry))*1e-9:
                raise QgsProcessingException('Reference raster has non-square pixels. This version requires equal X/Y pixel sizes for target-resolution alignment.')
            method_index = max(0, min(method_index, len(GDAL_RESAMPLING)-1))
            try:
                import processing
                params = {
                    'INPUT': source,
                    'SOURCE_CRS': source.crs(),
                    'TARGET_CRS': ref.crs(),
                    'RESAMPLING': GDAL_RESAMPLING[method_index],
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
            except Exception as e:
                raise QgsProcessingException('GDAL Warp failed. Check GDAL provider availability and parameters. Details: '+str(e))
            return {self.OUTPUT: output}
