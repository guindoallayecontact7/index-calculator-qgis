# -*- coding: utf-8 -*-
"""Index Calculator Field Intelligence: grid-center zonal statistics (prototype)."""
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsFeature, QgsFields, QgsField, QgsFeatureSink,
    QgsGeometry, QgsPointXY, QgsWkbTypes)
from qgis.PyQt.QtCore import QVariant
import math


class FieldZonalStatsAlgorithm(QgsProcessingAlgorithm):
    POLYGONS='POLYGONS'; RASTER='RASTER'; OUTPUT='OUTPUT'
    def name(self): return 'ic_field_zonal_stats'
    def displayName(self): return 'Field Statistics per Parcel'
    def group(self): return 'Field statistics'
    def groupId(self): return 'field_intelligence'
    def shortHelpString(self):
        return ('Calcule min, max, moyenne, mediane, ecart-type et nombre de pixels valides pour chaque entite polygonale. '
                'Echantillonnage aux centres des pixels. Raster et vecteur doivent partager le meme CRS. '
                'Statistiques descriptives, non diagnostiques agronomiques.')
    def createInstance(self): return FieldZonalStatsAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.POLYGONS,'Parcelles (polygones)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER,'Raster indice (bande 1)'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Parcelles avec statistiques'))
    def processAlgorithm(self, parameters, context, feedback):
        source=self.parameterAsSource(parameters,self.POLYGONS,context)
        raster=self.parameterAsRasterLayer(parameters,self.RASTER,context)
        if source is None or raster is None or not raster.isValid():
            raise QgsProcessingException('Source polygonale ou raster invalide.')
        if source.sourceCrs()!=raster.crs():
            raise QgsProcessingException('CRS differents. Reprojeter les parcelles ou le raster avant traitement.')
        if source.wkbType() not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            raise QgsProcessingException('La couche de parcelles doit contenir des polygones.')
        extent=raster.extent(); cols=raster.width(); rows=raster.height(); provider=raster.dataProvider()
        block=provider.block(1,extent,cols,rows)
        if block is None or block.isEmpty(): raise QgsProcessingException('Impossible de lire la bande raster.')
        dx=extent.width()/cols; dy=extent.height()/rows; nodata=block.noDataValue()
        out_fields=QgsFields(source.fields())
        for fld in [QgsField('ag_min',QVariant.Double),QgsField('ag_max',QVariant.Double),QgsField('ag_mean',QVariant.Double),QgsField('ag_median',QVariant.Double),QgsField('ag_std',QVariant.Double),QgsField('ag_count',QVariant.LongLong)]: out_fields.append(fld)
        (sink,dest)=self.parameterAsSink(parameters,self.OUTPUT,context,out_fields,source.wkbType(),source.sourceCrs())
        if sink is None: raise QgsProcessingException('Creation du fichier de sortie impossible.')
        total=source.featureCount(); done=0
        for feature in source.getFeatures():
            if feedback.isCanceled(): break
            geom=feature.geometry(); vals=[]
            box=geom.boundingBox().intersect(extent)
            if not box.isEmpty():
                c0=max(0,int((box.xMinimum()-extent.xMinimum())/dx)); c1=min(cols-1,int((box.xMaximum()-extent.xMinimum())/dx))
                r0=max(0,int((extent.yMaximum()-box.yMaximum())/dy)); r1=min(rows-1,int((extent.yMaximum()-box.yMinimum())/dy))
                for row in range(r0,r1+1):
                    y=extent.yMaximum()-(row+0.5)*dy
                    for col in range(c0,c1+1):
                        x=extent.xMinimum()+(col+0.5)*dx
                        if not geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x,y))): continue
                        value=block.value(row,col)
                        if block.isNoData(row,col): continue
                        if nodata is not None and value==nodata: continue
                        if math.isfinite(value): vals.append(float(value))
            if vals:
                vals.sort(); n=len(vals); mean=sum(vals)/n; med=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
                std=math.sqrt(sum((v-mean)**2 for v in vals)/n)
                stats=[vals[0],vals[-1],mean,med,std,n]
            else: stats=[None,None,None,None,None,0]
            out=QgsFeature(out_fields); out.setGeometry(geom); out.setAttributes(feature.attributes()+stats); sink.addFeature(out,QgsFeatureSink.FastInsert)
            done+=1; feedback.setProgress(int(done*100/max(total,1)))
        return {self.OUTPUT:dest}
