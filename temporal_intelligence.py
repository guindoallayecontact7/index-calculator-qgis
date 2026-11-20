# -*- coding: utf-8 -*-
"""Index Calculator temporal monitoring tools (prototype)."""
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
        return ('Calcul pixel à pixel de Date 2 - Date 1. Les deux rasters doivent avoir le même CRS, extent, dimensions et grille. '
                'Utiliser de préférence le même indice, la même échelle de réflectance et une période/correction comparable. '
                'Le résultat est une différence numérique, pas un diagnostic agronomique.')
    def createInstance(self): return RasterChangeAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.BASE,'Raster de référence - Date 1'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CURRENT,'Raster récent - Date 2'))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT,'Raster de changement (Date 2 - Date 1)'))
    def processAlgorithm(self, parameters, context, feedback):
        a=self.parameterAsRasterLayer(parameters,self.BASE,context)
        b=self.parameterAsRasterLayer(parameters,self.CURRENT,context)
        if not a or not b or not a.isValid() or not b.isValid():
            raise QgsProcessingException('Les deux rasters doivent être valides.')
        if a.crs()!=b.crs() or a.width()!=b.width() or a.height()!=b.height() or a.extent()!=b.extent():
            raise QgsProcessingException('Grilles différentes : CRS, dimensions et extent doivent être identiques. Reprojeter/rééchantillonner avant le calcul.')
        entries=[]
        for lyr,role in ((a,'A'),(b,'B')):
            e=QgsRasterCalculatorEntry(); e.raster=lyr; e.bandNumber=1; e.ref=lyr.name()+'@1'; entries.append(e)
        formula='"'+b.name()+'@1" - "'+a.name()+'@1"'
        out=self.parameterAsOutputLayer(parameters,self.OUTPUT,context)
        from .raster_calc import calculate
        erreur=calculate(formula,out,a.extent(),a.crs(),a.width(),a.height(),entries,context.transformContext(),feedback)
        if erreur:
            raise QgsProcessingException('Calcul de différence échoué : '+erreur)
        return {self.OUTPUT:out}


class TemporalFieldComparisonAlgorithm(QgsProcessingAlgorithm):
    POLYGONS='POLYGONS'; BASE='BASE'; CURRENT='CURRENT'; OUTPUT='OUTPUT'
    def name(self): return 'ic_temporal_field_comparison'
    def displayName(self): return 'Crop Monitoring - Temporal Comparison per Parcel'
    def group(self): return 'Crop Monitoring'
    def groupId(self): return 'crop_monitoring'
    def shortHelpString(self):
        return ('Compare la moyenne des pixels de deux rasters dans chaque parcelle, en échantillonnant les centres de pixels. '
                'Ajoute ag_t1, ag_t2, ag_delta et ag_pct. Les rasters doivent partager CRS, dimensions, extent et grille. '
                'Le pourcentage est calculé par rapport à abs(moyenne Date 1); il est NULL si Date 1 est proche de zéro. '
                'Des valeurs de différence ne constituent pas un diagnostic de culture.')
    def createInstance(self): return TemporalFieldComparisonAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.POLYGONS,'Parcelles agricoles (polygones)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.BASE,'Raster Date 1 (indice)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CURRENT,'Raster Date 2 (même indice)'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Parcelles comparées'))
    def processAlgorithm(self, parameters, context, feedback):
        src=self.parameterAsSource(parameters,self.POLYGONS,context)
        a=self.parameterAsRasterLayer(parameters,self.BASE,context); b=self.parameterAsRasterLayer(parameters,self.CURRENT,context)
        if src is None or not a or not b or not a.isValid() or not b.isValid(): raise QgsProcessingException('Entrées invalides.')
        if src.sourceCrs()!=a.crs() or a.crs()!=b.crs(): raise QgsProcessingException('Les trois couches doivent partager le même CRS.')
        if a.width()!=b.width() or a.height()!=b.height() or a.extent()!=b.extent(): raise QgsProcessingException('Les rasters doivent être parfaitement alignés (dimensions et extent).')
        if src.wkbType() not in (QgsWkbTypes.Polygon,QgsWkbTypes.MultiPolygon): raise QgsProcessingException('La couche doit être polygonale.')
        ext=a.extent(); cols=a.width(); rows=a.height(); dx=ext.width()/cols; dy=ext.height()/rows
        blk1=a.dataProvider().block(1,ext,cols,rows); blk2=b.dataProvider().block(1,ext,cols,rows)
        if blk1 is None or blk2 is None or blk1.isEmpty() or blk2.isEmpty(): raise QgsProcessingException('Lecture raster impossible.')
        fields=QgsFields(src.fields())
        for fld in (QgsField('ag_t1',QVariant.Double),QgsField('ag_t2',QVariant.Double),QgsField('ag_delta',QVariant.Double),QgsField('ag_pct',QVariant.Double)):
            fields.append(fld)
        sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,src.wkbType(),src.sourceCrs())
        if sink is None: raise QgsProcessingException('Sink de sortie impossible.')
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
