# -*- coding: utf-8 -*-
"""Index Calculator Stress Detection and Field Ranking processing algorithms."""
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterRasterDestination, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterNumber,
    QgsProcessingException, QgsProcessingParameterEnum, QgsFeature, QgsFields,
    QgsField, QgsFeatureSink, QgsGeometry, QgsPointXY, QgsWkbTypes)
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.PyQt.QtCore import QVariant
import math



class StressDetectionAlgorithm(QgsProcessingAlgorithm):
    BEFORE='BEFORE'; AFTER='AFTER'; THRESHOLD='THRESHOLD'; OUTPUT='OUTPUT'
    def name(self): return 'ic_stress_anomaly'
    def displayName(self): return 'Stress Detection - Index Drop Between Dates'
    def group(self): return 'Agricultural preprocessing'
    def groupId(self): return 'agricultural_intelligence'
    def shortHelpString(self):
        return ('Produit un masque binaire des pixels où l’indice baisse d’au moins le seuil choisi : Date 1 - Date 2 >= seuil. '
                'Rasters identiques en CRS, dimensions, extent et grille. Utiliser le même indice et des dates comparables. '
                'Une anomalie n’est pas un diagnostic : récolte, stade, pâturage, défrichement, nuages et artefacts peuvent aussi expliquer une baisse.')
    def createInstance(self): return StressDetectionAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.BEFORE, 'Raster indice - Date 1 (avant)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.AFTER, 'Raster indice - Date 2 (après)'))
        self.addParameter(QgsProcessingParameterNumber(self.THRESHOLD, 'Seuil minimum de baisse (Date 1 - Date 2)', QgsProcessingParameterNumber.Double, 0.15, False, 0.0))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, 'Masque d’anomalie (1 = baisse dépassant le seuil)'))
    def processAlgorithm(self, parameters, context, feedback):
        before=self.parameterAsRasterLayer(parameters,self.BEFORE,context)
        after=self.parameterAsRasterLayer(parameters,self.AFTER,context)
        threshold=self.parameterAsDouble(parameters,self.THRESHOLD,context)
        if not before or not after or not before.isValid() or not after.isValid():
            raise QgsProcessingException('Rasters d’entrée invalides.')
        if before.crs()!=after.crs() or before.width()!=after.width() or before.height()!=after.height() or before.extent()!=after.extent():
            raise QgsProcessingException('Les rasters doivent être parfaitement alignés (CRS, dimensions, extent et grille).')
        entries=[]
        for lyr in (before,after):
            e=QgsRasterCalculatorEntry(); e.raster=lyr; e.bandNumber=1; e.ref=lyr.name()+'@1'; entries.append(e)
        formula='("'+before.name()+'@1" - "'+after.name()+'@1") >= '+str(threshold)
        out=self.parameterAsOutputLayer(parameters,self.OUTPUT,context)
        from .raster_calc import calculate
        erreur=calculate(formula,out,before.extent(),before.crs(),before.width(),before.height(),entries,context.transformContext(),feedback)
        if erreur: raise QgsProcessingException('Détection échouée : '+erreur)
        return {self.OUTPUT:out}


class FieldRankingAlgorithm(QgsProcessingAlgorithm):
    POLYGONS='POLYGONS'; RASTER='RASTER'; OUTPUT='OUTPUT'
    def name(self): return 'ic_field_ranking'
    def displayName(self): return 'Field Ranking by Index Level'
    def group(self): return 'Agricultural preprocessing'
    def groupId(self): return 'agricultural_intelligence'
    def shortHelpString(self):
        return ('Calcule la moyenne du raster dans chaque parcelle puis classe les parcelles de la valeur la plus faible à la plus élevée. '
                'Le rang 1 correspond donc à la moyenne la plus faible et peut servir à prioriser une inspection, selon l’indice utilisé. '
                'Cette priorisation est descriptive et ne constitue pas une interprétation agronomique universelle.')
    def createInstance(self): return FieldRankingAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.POLYGONS,'Parcelles agricoles (polygones)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER,'Raster d’indice à classer (bande 1)'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Parcelles classées'))
    def processAlgorithm(self, parameters, context, feedback):
        source=self.parameterAsSource(parameters,self.POLYGONS,context)
        raster=self.parameterAsRasterLayer(parameters,self.RASTER,context)
        if source is None or raster is None or not raster.isValid(): raise QgsProcessingException('Entrées invalides.')
        if source.sourceCrs()!=raster.crs(): raise QgsProcessingException('Parcelles et raster doivent partager le CRS. Reprojeter avant traitement.')
        if source.wkbType() not in (QgsWkbTypes.Polygon,QgsWkbTypes.MultiPolygon): raise QgsProcessingException('La couche doit être polygonale.')
        ext=raster.extent(); cols=raster.width(); rows=raster.height(); dx=ext.width()/cols; dy=ext.height()/rows
        block=raster.dataProvider().block(1,ext,cols,rows)
        if block is None or block.isEmpty(): raise QgsProcessingException('Lecture raster impossible.')
        records=[]; total=max(source.featureCount(),1); done=0
        for feat in source.getFeatures():
            if feedback.isCanceled(): break
            geom=feat.geometry(); box=geom.boundingBox().intersect(ext); vals=[]
            if not box.isEmpty():
                c0=max(0,int((box.xMinimum()-ext.xMinimum())/dx)); c1=min(cols-1,int((box.xMaximum()-ext.xMinimum())/dx))
                r0=max(0,int((ext.yMaximum()-box.yMaximum())/dy)); r1=min(rows-1,int((ext.yMaximum()-box.yMinimum())/dy))
                for r in range(r0,r1+1):
                    y=ext.yMaximum()-(r+0.5)*dy
                    for c in range(c0,c1+1):
                        x=ext.xMinimum()+(c+0.5)*dx
                        if geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x,y))) and not block.isNoData(r,c):
                            v=float(block.value(r,c))
                            if math.isfinite(v): vals.append(v)
            mean=sum(vals)/len(vals) if vals else None
            records.append((feat,mean,len(vals)))
            done+=1; feedback.setProgress(int(done*100/total))
        ranked=sorted([r for r in records if r[1] is not None],key=lambda r:r[1])
        rank_by_id={r[0].id():i+1 for i,r in enumerate(ranked)}
        fields=QgsFields(source.fields())
        fields.append(QgsField('ag_mean',QVariant.Double)); fields.append(QgsField('ag_rank',QVariant.Int)); fields.append(QgsField('ag_pixels',QVariant.LongLong)); fields.append(QgsField('ag_priority',QVariant.String,len=16))
        sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,source.wkbType(),source.sourceCrs())
        if sink is None: raise QgsProcessingException('Création de sortie impossible.')
        n=len(ranked)
        for feat,mean,count in records:
            rank=rank_by_id.get(feat.id())
            if rank is None: priority='NO_DATA'
            elif n and rank<=max(1,math.ceil(n*0.2)): priority='HIGH'
            elif n and rank<=max(1,math.ceil(n*0.5)): priority='MEDIUM'
            else: priority='LOW'
            out=QgsFeature(fields); out.setGeometry(feat.geometry()); out.setAttributes(feat.attributes()+[mean,rank,count,priority]); sink.addFeature(out,QgsFeatureSink.FastInsert)
        return {self.OUTPUT:dest}
