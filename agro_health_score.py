# -*- coding: utf-8 -*-
"""Index Calculator Field Health Score (transparent, exploratory multicriteria score)."""
import math
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber, QgsProcessingException, QgsFeature,
    QgsFields, QgsField, QgsFeatureSink, QgsGeometry, QgsPointXY,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant



class FieldHealthScoreAlgorithm(QgsProcessingAlgorithm):
    POLYGONS='POLYGONS'; NDVI='NDVI'; NDMI='NDMI'; NDRE='NDRE';
    NDVI_MIN='NDVI_MIN'; NDVI_MAX='NDVI_MAX'; NDMI_MIN='NDMI_MIN'; NDMI_MAX='NDMI_MAX'; NDRE_MIN='NDRE_MIN'; NDRE_MAX='NDRE_MAX'
    W_NDVI='W_NDVI'; W_NDMI='W_NDMI'; W_NDRE='W_NDRE'; OUTPUT='OUTPUT'

    def name(self): return 'ic_field_health_score'
    def displayName(self): return 'Field Health Score - Multi-criteria per Parcel'
    def group(self): return 'Agricultural preprocessing'
    def groupId(self): return 'agricultural_intelligence'
    def shortHelpString(self):
        return ('Calcule un score exploratoire 0-100 par parcelle à partir des moyennes NDVI, NDMI et NDRE. '
                'Chaque indice est normalisé selon ses bornes min/max saisies puis combiné avec les poids NDVI/NDMI/NDRE. '
                'Ce score n’est pas un diagnostic de santé, rendement, maladie ou sécheresse. Les indices, leurs bornes, '
                'les poids, le stade cultural, la date et la qualité des images doivent être vérifiés et adaptés. '
                'Les trois rasters doivent être monobande, co-enregistrés, alignés et dans le même CRS que les parcelles.')
    def createInstance(self): return FieldHealthScoreAlgorithm()
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.POLYGONS, 'Parcelles agricoles (polygones)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.NDVI, 'Raster NDVI (bande 1)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.NDMI, 'Raster NDMI (bande 1)'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.NDRE, 'Raster NDRE (bande 1)'))
        for key, label, default in ((self.NDVI_MIN,'NDVI minimum pour normalisation',-1.0),(self.NDVI_MAX,'NDVI maximum pour normalisation',1.0),
                                    (self.NDMI_MIN,'NDMI minimum pour normalisation',-1.0),(self.NDMI_MAX,'NDMI maximum pour normalisation',1.0),
                                    (self.NDRE_MIN,'NDRE minimum pour normalisation',-1.0),(self.NDRE_MAX,'NDRE maximum pour normalisation',1.0)):
            self.addParameter(QgsProcessingParameterNumber(key,label,QgsProcessingParameterNumber.Double,default))
        self.addParameter(QgsProcessingParameterNumber(self.W_NDVI,'Poids NDVI (%)',QgsProcessingParameterNumber.Double,50,minValue=0,maxValue=100))
        self.addParameter(QgsProcessingParameterNumber(self.W_NDMI,'Poids NDMI (%)',QgsProcessingParameterNumber.Double,30,minValue=0,maxValue=100))
        self.addParameter(QgsProcessingParameterNumber(self.W_NDRE,'Poids NDRE (%)',QgsProcessingParameterNumber.Double,20,minValue=0,maxValue=100))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Parcelles avec Field Health Score'))

    def _mean_in_polygon(self, raster, block, geom, feedback):
        ext=raster.extent(); cols=raster.width(); rows=raster.height(); dx=ext.width()/cols; dy=ext.height()/rows
        box=geom.boundingBox().intersect(ext)
        if box.isEmpty(): return None, 0
        c0=max(0,int((box.xMinimum()-ext.xMinimum())/dx)); c1=min(cols-1,int((box.xMaximum()-ext.xMinimum())/dx))
        r0=max(0,int((ext.yMaximum()-box.yMaximum())/dy)); r1=min(rows-1,int((ext.yMaximum()-box.yMinimum())/dy))
        if block is None or block.isEmpty(): return None, 0
        values=[]
        for r in range(r0,r1+1):
            if feedback.isCanceled(): break
            y=ext.yMaximum()-(r+0.5)*dy
            for c in range(c0,c1+1):
                x=ext.xMinimum()+(c+0.5)*dx
                if geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x,y))) and not block.isNoData(r,c):
                    val=float(block.value(r,c))
                    if math.isfinite(val): values.append(val)
        return (sum(values)/len(values) if values else None), len(values)

    def processAlgorithm(self, parameters, context, feedback):
        source=self.parameterAsSource(parameters,self.POLYGONS,context)
        rasters={k:self.parameterAsRasterLayer(parameters,k,context) for k in (self.NDVI,self.NDMI,self.NDRE)}
        if source is None or any(r is None or not r.isValid() for r in rasters.values()):
            raise QgsProcessingException('Entrées invalides.')
        if source.wkbType() not in (QgsWkbTypes.Polygon,QgsWkbTypes.MultiPolygon):
            raise QgsProcessingException('La couche de parcelles doit être polygonale.')
        crs=source.sourceCrs()
        first=rasters[self.NDVI]
        for key,r in rasters.items():
            if r.crs()!=crs: raise QgsProcessingException('Parcelles et rasters doivent partager le CRS. Reprojeter avant le traitement.')
            if r.crs()!=first.crs() or r.width()!=first.width() or r.height()!=first.height() or r.extent()!=first.extent():
                raise QgsProcessingException('Les trois rasters doivent être alignés (CRS, dimensions, extent et grille).')
        ranges={self.NDVI:(self.parameterAsDouble(parameters,self.NDVI_MIN,context),self.parameterAsDouble(parameters,self.NDVI_MAX,context)),
                self.NDMI:(self.parameterAsDouble(parameters,self.NDMI_MIN,context),self.parameterAsDouble(parameters,self.NDMI_MAX,context)),
                self.NDRE:(self.parameterAsDouble(parameters,self.NDRE_MIN,context),self.parameterAsDouble(parameters,self.NDRE_MAX,context))}
        for k,(lo,hi) in ranges.items():
            if hi<=lo: raise QgsProcessingException(f'Bornes de normalisation invalides pour {k}: maximum doit dépasser minimum.')
        weights={self.NDVI:self.parameterAsDouble(parameters,self.W_NDVI,context),self.NDMI:self.parameterAsDouble(parameters,self.W_NDMI,context),self.NDRE:self.parameterAsDouble(parameters,self.W_NDRE,context)}
        total=sum(weights.values())
        if total<=0: raise QgsProcessingException('La somme des poids doit être positive.')
        fields=QgsFields(source.fields())
        for name,typ in [('ag_ndvi',QVariant.Double),('ag_ndmi',QVariant.Double),('ag_ndre',QVariant.Double),('ag_health',QVariant.Double),('ag_health_class',QVariant.String),('ag_pixels',QVariant.LongLong)]: fields.append(QgsField(name,typ))
        sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,source.wkbType(),crs)
        if sink is None: raise QgsProcessingException('Création de la couche de sortie impossible.')
        feats=list(source.getFeatures()); n=max(len(feats),1)
        raster_blocks={k:r.dataProvider().block(1,r.extent(),r.width(),r.height()) for k,r in rasters.items()}
        if any(b is None or b.isEmpty() for b in raster_blocks.values()): raise QgsProcessingException('Impossible de lire un raster d’entrée.')
        for i,feat in enumerate(feats):
            if feedback.isCanceled(): break
            geom=feat.geometry(); means={}; counts={}
            for k,r in rasters.items(): means[k],counts[k]=self._mean_in_polygon(r,raster_blocks[k],geom,feedback)
            vals=[]
            for k in (self.NDVI,self.NDMI,self.NDRE):
                m=means[k]; lo,hi=ranges[k]
                vals.append(None if m is None else max(0.0,min(1.0,(m-lo)/(hi-lo))))
            score=None
            if all(v is not None for v in vals): score=100*sum(weights[k]*v for k,v in zip((self.NDVI,self.NDMI,self.NDRE),vals))/total
            if score is None: klass='NO_DATA'
            elif score>=70: klass='HIGH'
            elif score>=40: klass='MEDIUM'
            else: klass='LOW'
            out=QgsFeature(fields); out.setGeometry(geom); out.setAttributes(feat.attributes()+[means[self.NDVI],means[self.NDMI],means[self.NDRE],score,klass,min(counts.values())])
            sink.addFeature(out,QgsFeatureSink.FastInsert); feedback.setProgress(int((i+1)*100/n))
        return {self.OUTPUT:dest}
