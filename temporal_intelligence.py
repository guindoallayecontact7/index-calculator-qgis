# -*- coding: utf-8 -*-
"""Index Calculator Pro temporal monitoring tools (prototype)."""
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                      QgsProcessingParameterRasterDestination, QgsProcessingException,
                      QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
                      QgsFeature, QgsFields, QgsField, QgsFeatureSink, QgsGeometry,
                      QgsPointXY, QgsWkbTypes)
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.PyQt.QtCore import QVariant
import math



class RasterChangeAlgorithm(QgsProcessingAlgorithm):
    BASE='BASE'; CURRENT='CURRENT'; OUTPUT='OUTPUT'
    def name(self): return 'ic_raster_change'
    def displayName(self): return 'Change Detection - Raster Difference (Date 2 - Date 1)'
    def group(self): return 'Crop Monitoring'
    def groupId(self): return 'crop_monitoring'
    def shortHelpString(self):
        return ('Pixel-by-pixel calculation of Date 2 - Date 1. Both rasters must share the CRS, extent, dimensions and grid. '
                'Preferably use the same index, the same reflectance scale and a comparable period and correction. '
                'The result is a numerical difference, not an agronomic diagnosis.')
    def createInstance(self): return RasterChangeAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.BASE,'Reference raster - Date 1'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CURRENT,'Recent raster - Date 2'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT,'Change raster (Date 2 - Date 1)'))
    def processAlgorithm(self, parameters, context, feedback):
        a=self.parameterAsRasterLayer(parameters,self.BASE,context)
        b=self.parameterAsRasterLayer(parameters,self.CURRENT,context)
        if not a or not b or not a.isValid() or not b.isValid():
            raise QgsProcessingException('Both rasters must be valid.')
        if a.crs()!=b.crs() or a.width()!=b.width() or a.height()!=b.height() or a.extent()!=b.extent():
            raise QgsProcessingException('Different grids: CRS, dimensions and extent must be identical. Reproject or resample before the calculation.')
        entries=[]
        for lyr,role in ((a,'A'),(b,'B')):
            e=QgsRasterCalculatorEntry(); e.raster=lyr; e.bandNumber=1; e.ref=role+'@1'; entries.append(e)
        formula='"B@1" - "A@1"'
        out=self.parameterAsOutputLayer(parameters,self.OUTPUT,context)
        from .raster_calc import calculate
        erreur=calculate(formula,out,a.extent(),a.crs(),a.width(),a.height(),entries,context.transformContext(),feedback)
        if erreur:
            raise QgsProcessingException('Difference calculation failed: '+erreur)
        return {self.OUTPUT:out}


class TemporalFieldComparisonAlgorithm(QgsProcessingAlgorithm):
    POLYGONS='POLYGONS'; BASE='BASE'; CURRENT='CURRENT'; OUTPUT='OUTPUT'
    def name(self): return 'ic_temporal_field_comparison'
    def displayName(self): return 'Crop Monitoring - Temporal Comparison per Parcel'
    def group(self): return 'Crop Monitoring'
    def groupId(self): return 'crop_monitoring'
    def shortHelpString(self):
        return ('Compares the mean pixel value of two rasters in each parcel, sampling pixel centres. '
                'Adds ag_t1, ag_t2, ag_delta and ag_pct. The rasters must share the CRS, dimensions, extent and grid. '
                'The percentage is relative to abs(Date 1 mean); it is NULL when Date 1 is close to zero. '
                'Difference values are not a crop diagnosis.')
    def createInstance(self): return TemporalFieldComparisonAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.POLYGONS,'Agricultural parcels (polygons)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.BASE,'Date 1 raster (index)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CURRENT,'Date 2 raster (same index)'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Compared parcels'))
    def processAlgorithm(self, parameters, context, feedback):
        src=self.parameterAsSource(parameters,self.POLYGONS,context)
        a=self.parameterAsRasterLayer(parameters,self.BASE,context); b=self.parameterAsRasterLayer(parameters,self.CURRENT,context)
        if src is None or not a or not b or not a.isValid() or not b.isValid(): raise QgsProcessingException('Invalid inputs.')
        if src.sourceCrs()!=a.crs() or a.crs()!=b.crs(): raise QgsProcessingException('The three layers must share the same CRS.')
        if a.width()!=b.width() or a.height()!=b.height() or a.extent()!=b.extent(): raise QgsProcessingException('The rasters must be perfectly aligned (dimensions and extent).')
        if src.wkbType() not in (QgsWkbTypes.Polygon,QgsWkbTypes.MultiPolygon): raise QgsProcessingException('The layer must be a polygon layer.')
        ext=a.extent(); cols=a.width(); rows=a.height(); dx=ext.width()/cols; dy=ext.height()/rows
        blk1=a.dataProvider().block(1,ext,cols,rows); blk2=b.dataProvider().block(1,ext,cols,rows)
        if blk1 is None or blk2 is None or blk1.isEmpty() or blk2.isEmpty(): raise QgsProcessingException('The raster could not be read.')
        fields=QgsFields(src.fields())
        for fld in (QgsField('ag_t1',QVariant.Double),QgsField('ag_t2',QVariant.Double),QgsField('ag_delta',QVariant.Double),QgsField('ag_pct',QVariant.Double)):
            fields.append(fld)
        sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,src.wkbType(),src.sourceCrs())
        if sink is None: raise QgsProcessingException('The output sink could not be created.')
        total=max(src.featureCount(),1); done=0
        for f in src.getFeatures():
            if feedback.isCanceled(): break
            geom=f.geometry(); box=geom.boundingBox().intersect(ext); v1=[]; v2=[]
            if not box.isEmpty():
                c0=max(0,int((box.xMinimum()-ext.xMinimum())/dx)); c1=min(cols-1,int((box.xMaximum()-ext.xMinimum())/dx))
                r0=max(0,int((ext.yMaximum()-box.yMaximum())/dy)); r1=min(rows-1,int((ext.yMaximum()-box.yMinimum())/dy))
                for r in range(r0,r1+1):
                    y=ext.yMaximum()-(r+0.5)*dy
                    for c in range(c0,c1+1):
                        x=ext.xMinimum()+(c+0.5)*dx
                        if not geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x,y))): continue
                        if not blk1.isNoData(r,c) and not blk2.isNoData(r,c):
                            x1=float(blk1.value(r,c)); x2=float(blk2.value(r,c))
                            if math.isfinite(x1) and math.isfinite(x2): v1.append(x1); v2.append(x2)
            if v1:
                m1=sum(v1)/len(v1); m2=sum(v2)/len(v2); delta=m2-m1; pct=(delta/abs(m1)*100.0) if abs(m1)>1e-12 else None
            else: m1=m2=delta=pct=None
            out=QgsFeature(fields); out.setGeometry(geom); out.setAttributes(f.attributes()+[m1,m2,delta,pct]); sink.addFeature(out,QgsFeatureSink.FastInsert)
            done+=1; feedback.setProgress(int(done*100/total))
        return {self.OUTPUT:dest}
