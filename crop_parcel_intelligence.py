# -*- coding: utf-8 -*-
"""Index Calculator V3.8 - parcel-level crop index statistics and transparent classes."""
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber, QgsProcessingParameterString,
    QgsProcessingException, QgsFeature, QgsFields, QgsField,
    QgsFeatureSink, QgsGeometry, QgsPointXY, QgsWkbTypes, QgsUnitTypes
)
from qgis.PyQt.QtCore import QVariant
import math



# Pure helper, deliberately testable without QGIS runtime.
def vigor_class(value, low_threshold, medium_threshold):
    if value is None or not math.isfinite(float(value)):
        return 'NO_DATA'
    if value < low_threshold:
        return 'LOW'
    if value < medium_threshold:
        return 'MODERATE'
    return 'HIGH'



def parcel_confidence(valid_pixels):
    if valid_pixels >= 30:
        return 'HIGH'
    if valid_pixels >= 10:
        return 'MEDIUM'
    if valid_pixels >= 1:
        return 'LOW'
    return 'NO_DATA'


class CropParcelIntelligenceAlgorithm(QgsProcessingAlgorithm):
    PARCELS='PARCELS'; INDEX='INDEX'; LOW='LOW'; MEDIUM='MEDIUM'; INDEX_NAME='INDEX_NAME'; OUTPUT='OUTPUT'

    def name(self): return 'ic_crop_parcel_intelligence'
    def displayName(self): return 'Parcel Statistics and Vigor'
    def group(self): return 'Parcel analysis'
    def groupId(self): return 'crop_parcel_intelligence'
    def shortHelpString(self):
        return ('Calcul des statistiques d’un raster d’indice à l’intérieur de polygones agricoles. '
                'Ajoute superficie, min/max/moyenne/médiane/écart-type, pixels valides, couverture estimée, '
                'classe de vigueur paramétrable et niveau de confiance basé uniquement sur le nombre de pixels. '
                'Les classes LOW/MODERATE/HIGH sont des seuils exploratoires, pas un diagnostic agronomique. '
                'Raster et parcelles doivent être alignés en CRS; raster échantillonné par centres de pixels.')
    def createInstance(self): return CropParcelIntelligenceAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.PARCELS, 'Parcelles agricoles (polygones)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.INDEX, 'Raster d’indice (bande 1)'))
        self.addParameter(QgsProcessingParameterString(self.INDEX_NAME, 'Nom de l’indice', defaultValue='NDVI'))
        self.addParameter(QgsProcessingParameterNumber(self.LOW, 'Seuil inférieur (classe LOW)', QgsProcessingParameterNumber.Double, 0.20))
        self.addParameter(QgsProcessingParameterNumber(self.MEDIUM, 'Seuil supérieur LOW / MODERATE', QgsProcessingParameterNumber.Double, 0.45))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Parcelles analysées'))
    def processAlgorithm(self, parameters, context, feedback):
        source=self.parameterAsSource(parameters,self.PARCELS,context)
        raster=self.parameterAsRasterLayer(parameters,self.INDEX,context)
        index_name=self.parameterAsString(parameters,self.INDEX_NAME,context) or 'INDEX'
        low=float(self.parameterAsDouble(parameters,self.LOW,context)); medium=float(self.parameterAsDouble(parameters,self.MEDIUM,context))
        if source is None or raster is None or not raster.isValid():
            raise QgsProcessingException('Source polygonale ou raster invalide.')
        if low >= medium:
            raise QgsProcessingException('Le seuil LOW doit être inférieur au seuil MODERATE/HIGH.')
        if source.sourceCrs()!=raster.crs():
            raise QgsProcessingException('CRS différents : reprojeter les parcelles ou le raster avant traitement.')
        if source.wkbType() not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            raise QgsProcessingException('La couche de parcelles doit contenir des polygones.')
        if raster.crs().mapUnits()!=QgsUnitTypes.DistanceMeters:
            raise QgsProcessingException('Superficie en hectares fiable uniquement avec un CRS projeté en mètres. Reprojeter la couche.')
        extent=raster.extent(); cols=raster.width(); rows=raster.height(); provider=raster.dataProvider()
        block=provider.block(1,extent,cols,rows)
        if block is None or block.isEmpty(): raise QgsProcessingException('Impossible de lire la bande raster.')
        dx=extent.width()/cols; dy=extent.height()/rows; nodata=block.noDataValue(); pixel_area=dx*dy
        out_fields=QgsFields(source.fields())
        additions=[
            QgsField('cp_area_ha',QVariant.Double), QgsField('cp_min',QVariant.Double),
            QgsField('cp_max',QVariant.Double), QgsField('cp_mean',QVariant.Double),
            QgsField('cp_median',QVariant.Double), QgsField('cp_std',QVariant.Double),
            QgsField('cp_valid_px',QVariant.LongLong), QgsField('cp_cover_pct',QVariant.Double),
            QgsField('cp_index',QVariant.String), QgsField('cp_class',QVariant.String),
            QgsField('cp_conf',QVariant.String)
        ]
        for fld in additions: out_fields.append(fld)
        (sink,dest)=self.parameterAsSink(parameters,self.OUTPUT,context,out_fields,source.wkbType(),source.sourceCrs())
        if sink is None: raise QgsProcessingException('Création de la sortie impossible.')
        total=source.featureCount(); done=0
        for feature in source.getFeatures():
            if feedback.isCanceled(): break
            geom=feature.geometry(); area_ha=geom.area()/10000.0; vals=[]
            box=geom.boundingBox().intersect(extent)
            if not box.isEmpty():
                c0=max(0,int((box.xMinimum()-extent.xMinimum())/dx)); c1=min(cols-1,int((box.xMaximum()-extent.xMinimum())/dx))
                r0=max(0,int((extent.yMaximum()-box.yMaximum())/dy)); r1=min(rows-1,int((extent.yMaximum()-box.yMinimum())/dy))
                for row in range(r0,r1+1):
                    y=extent.yMaximum()-(row+0.5)*dy
                    for col in range(c0,c1+1):
                        x=extent.xMinimum()+(col+0.5)*dx
                        if not geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x,y))): continue
                        v=block.value(row,col)
                        if block.isNoData(row,col): continue
                        if nodata is not None and v==nodata: continue
                        if math.isfinite(v): vals.append(float(v))
            if vals:
                vals.sort(); count=len(vals); mean=sum(vals)/count
                median=vals[count//2] if count%2 else (vals[count//2-1]+vals[count//2])/2
                std=math.sqrt(sum((v-mean)**2 for v in vals)/count)
                coverage=min(100.0,(count*pixel_area/(geom.area() or 1))*100.0)
                stats=[area_ha,vals[0],vals[-1],mean,median,std,count,coverage,index_name,vigor_class(mean,low,medium),parcel_confidence(count)]
            else:
                stats=[area_ha,None,None,None,None,None,0,0.0,index_name,'NO_DATA','NO_DATA']
            out=QgsFeature(out_fields); out.setGeometry(geom); out.setAttributes(feature.attributes()+stats); sink.addFeature(out,QgsFeatureSink.FastInsert)
            done+=1; feedback.setProgress(int(done*100/max(total,1)))
        return {self.OUTPUT:dest}
