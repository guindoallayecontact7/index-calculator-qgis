# -*- coding: utf-8 -*-
"""Index Calculator Pro - exploratory spectral connected-component field delineation.
Segments connected pixels whose index values are within a seed tolerance. This is
NOT a validated parcel boundary model and should be reviewed against reference data.
"""
import math

# Pure helpers for testing without QGIS/GDAL.
def classify_segment(mean_value, low, high):
    if mean_value is None or not math.isfinite(float(mean_value)):
        return 'NO_DATA'
    if mean_value < low:
        return 'LOW'
    if mean_value < high:
        return 'MODERATE'
    return 'HIGH'

def connected_segments(values, valid, tolerance=0.08, min_pixels=3):
    """4-connected components, each grown by seed-value tolerance; labels start at 1."""
    rows, cols = values.shape
    labels = [[0 for _ in range(cols)] for __ in range(rows)]
    label = 0
    sizes = {}
    means = {}
    for r in range(rows):
        for c in range(cols):
            if not valid[r, c] or labels[r][c]:
                continue
            label += 1
            seed = float(values[r, c])
            stack = [(r, c)]
            labels[r][c] = label
            total = 0.0; count = 0
            while stack:
                y, x = stack.pop()
                v = float(values[y, x]); total += v; count += 1
                for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                    if 0 <= ny < rows and 0 <= nx < cols and valid[ny,nx] and labels[ny][nx] == 0:
                        if abs(float(values[ny,nx])-seed) <= tolerance:
                            labels[ny][nx] = label
                            stack.append((ny,nx))
            sizes[label] = count
            means[label] = total/count if count else float('nan')
    # Small components remain present but receive an explicit flag for review.
    return labels, sizes, means, {k: (sizes[k] >= min_pixels) for k in sizes}


class AutomaticFieldDelineationAlgorithm:
    """QGIS Processing algorithm implementation; imports QGIS only at runtime."""
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            RASTER='INDEX_RASTER'; TOL='TOLERANCE'; MINPIX='MIN_PIXELS'; LOW='LOW'; HIGH='HIGH'; OUTPUT='OUTPUT'
            def name(self): return 'ic_automatic_field_delineation'
            def displayName(self): return 'Automatic Field Delineation - Spectral Segments'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Segments 4-connected raster pixels by seed-index similarity and polygonizes the segments. '
                       'Exploratory candidate objects only: boundaries are spectral segments, not confirmed field parcels. '
                       'Input should be a cleaned single-band index raster; cloud masking and grid QA are recommended.')
            def createInstance(self): return AutomaticFieldDelineationAlgorithm()
            def initAlgorithm(self, config=None):
                from qgis.core import (QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
                                   QgsProcessingParameterFeatureSink)
                self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER,'Clean single-band index raster (e.g., NDVI)'))
                self.addParameter(QgsProcessingParameterNumber(self.TOL,'Seed similarity tolerance',QgsProcessingParameterNumber.Type.Double,0.08,minValue=0.0,maxValue=2.0))
                self.addParameter(QgsProcessingParameterNumber(self.MINPIX,'Minimum segment size (pixels)',QgsProcessingParameterNumber.Type.Integer,3,minValue=1))
                self.addParameter(QgsProcessingParameterNumber(self.LOW,'LOW class threshold',QgsProcessingParameterNumber.Type.Double,0.20))
                self.addParameter(QgsProcessingParameterNumber(self.HIGH,'MODERATE/HIGH threshold',QgsProcessingParameterNumber.Type.Double,0.45))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Spectral segment polygons'))
            def processAlgorithm(self, parameters, context, feedback):
                import numpy as np
                from osgeo import gdal, ogr, osr
                from qgis.core import (QgsProcessingException, QgsFeature, QgsFields, QgsField,
                    QgsFeatureSink, QgsGeometry, QgsProcessing, QgsWkbTypes)
                from qgis.PyQt.QtCore import QVariant
                layer=self.parameterAsRasterLayer(parameters,self.RASTER,context)
                if layer is None or not layer.isValid(): raise QgsProcessingException('Raster invalide.')
                tol=float(self.parameterAsDouble(parameters,self.TOL,context)); minpix=int(self.parameterAsInt(parameters,self.MINPIX,context))
                low=float(self.parameterAsDouble(parameters,self.LOW,context)); high=float(self.parameterAsDouble(parameters,self.HIGH,context))
                if low >= high: raise QgsProcessingException('LOW threshold must be lower than HIGH threshold.')
                ds=gdal.Open(layer.source(),gdal.GA_ReadOnly)
                if ds is None: raise QgsProcessingException('GDAL cannot open the raster source. Use a local GeoTIFF.')
                if ds.RasterCount < 1: raise QgsProcessingException('Raster has no bands.')
                if ds.RasterXSize*ds.RasterYSize > 4000000: raise QgsProcessingException('Raster exceeds 4 million pixels. Clip to study area before segmentation.')
                band=ds.GetRasterBand(1); arr=band.ReadAsArray().astype('float32'); nd=band.GetNoDataValue()
                valid=np.isfinite(arr)
                if nd is not None: valid &= (arr != nd)
                valid &= (arr >= -1e6) & (arr <= 1e6)
                if not valid.any(): raise QgsProcessingException('No valid raster pixels found.')
                # Compact component labeling with a Python flood-fill; no ML model required.
                labels, sizes, means, eligible=connected_segments(arr,valid,tol,minpix)
                lab=np.asarray(labels,dtype='int32')
                feedback.pushInfo(f'Spectral segments: {len(sizes)}; eligible by minimum size: {sum(eligible.values())}')
                mem=gdal.GetDriverByName('MEM').Create('',ds.RasterXSize,ds.RasterYSize,1,gdal.GDT_Int32)
                mem.SetGeoTransform(ds.GetGeoTransform()); mem.SetProjection(ds.GetProjection())
                mem.GetRasterBand(1).WriteArray(lab); mem.GetRasterBand(1).SetNoDataValue(0)
                vec=ogr.GetDriverByName('Memory').CreateDataSource('segments')
                srs=osr.SpatialReference(); srs.ImportFromWkt(ds.GetProjection())
                lyr=vec.CreateLayer('segments',srs,ogr.wkbPolygon)
                # Polygonize (GDAL >= 3.11) writes the region number into the
                # first field, so DN must be created first.
                lyr.CreateField(ogr.FieldDefn('DN',ogr.OFTInteger))
                lyr.CreateField(ogr.FieldDefn('seg_id',ogr.OFTInteger)); lyr.CreateField(ogr.FieldDefn('px_count',ogr.OFTInteger))
                lyr.CreateField(ogr.FieldDefn('idx_mean',ogr.OFTReal)); lyr.CreateField(ogr.FieldDefn('size_ok',ogr.OFTInteger))
                lyr.CreateField(ogr.FieldDefn('vigor',ogr.OFTString));
                gdal.Polygonize(mem.GetRasterBand(1),mem.GetRasterBand(1).GetMaskBand(),lyr,0,[],callback=None)
                fields=QgsFields()
                fields.append(QgsField('seg_id',QVariant.Int)); fields.append(QgsField('seg_px',QVariant.Int)); fields.append(QgsField('seg_mean',QVariant.Double)); fields.append(QgsField('size_ok',QVariant.Int)); fields.append(QgsField('seg_vigor',QVariant.String))
                sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,QgsWkbTypes.Type.Polygon,layer.crs())
                if sink is None: raise QgsProcessingException('Output sink creation failed.')
                for of in lyr:
                    if feedback.isCanceled(): break
                    sid=int(of.GetField('DN'))
                    if sid <= 0 or sid not in sizes: continue
                    geom=QgsGeometry.fromWkt(of.GetGeometryRef().ExportToWkt())
                    f=QgsFeature(fields); f.setGeometry(geom)
                    f.setAttributes([sid,int(sizes[sid]),float(means[sid]),int(eligible[sid]),classify_segment(means[sid],low,high)])
                    sink.addFeature(f,QgsFeatureSink.Flag.FastInsert)
                vec=None; mem=None; ds=None
                return {self.OUTPUT:dest}
        return _Alg()
