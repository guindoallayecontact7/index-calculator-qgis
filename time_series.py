# -*- coding: utf-8 -*-
"""Index Calculator crop time-series zonal analysis."""
import math
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessing, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMultipleLayers, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsFeature, QgsFields, QgsField, QgsFeatureSink,
    QgsGeometry, QgsPointXY, QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant



class CropTimeSeriesAlgorithm(QgsProcessingAlgorithm):
    PARCELS = 'PARCELS'
    RASTERS = 'RASTERS'
    OUTPUT = 'OUTPUT'



    def name(self):
        return 'ic_crop_time_series'


    def displayName(self):
        return 'Crop Time Series - Tendances par parcelle'

    def group(self):
        return 'Crop Monitoring'

    def groupId(self):
        return 'crop_monitoring'

    def shortHelpString(self):
        return ('Analyse une liste ordonnée de rasters mono-bande (un raster par date) dans chaque parcelle. '
                'Produit les moyennes par date, moyenne générale, écart-type, minimum, maximum, amplitude et pente linéaire '
                'en unités d indice par pas temporel. Les dates doivent être fournies dans l ordre chronologique. '
                'Les rasters et parcelles doivent partager un CRS. Les valeurs NoData et non finies sont ignorées. '
                'La pente utilise les positions 1..N et non des intervalles calendaires exacts; pour des dates irrégulières, '
                'interpréter avec prudence. Ce traitement ne diagnostique pas directement un stress ou un rendement.')

    def createInstance(self):
        return CropTimeSeriesAlgorithm()



    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.PARCELS, 'Parcelles agricoles (polygones)'))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.RASTERS, 'Rasters d indices ordonnés chronologiquement', layerType=QgsProcessing.TypeRaster))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Parcelles - résultats de série temporelle'))

    def processAlgorithm(self, parameters, context, feedback):
        src = self.parameterAsSource(parameters, self.PARCELS, context)
        rasters = self.parameterAsLayerList(parameters, self.RASTERS, context)
        if src is None or not rasters or len(rasters) < 2:
            raise QgsProcessingException('Sélectionner les parcelles et au moins deux rasters datés, dans l ordre chronologique.')
        if src.wkbType() not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            raise QgsProcessingException('La couche de parcelles doit être polygonale.')
        for r in rasters:
            if r is None or not r.isValid():
                raise QgsProcessingException('Un raster de la série est invalide.')
            if r.crs() != src.sourceCrs():
                raise QgsProcessingException('Tous les rasters doivent être dans le même CRS que les parcelles. Reprojeter avant analyse.')

        fields = QgsFields(src.fields())
        date_fields = []
        for i in range(len(rasters)):
            fn = 'ag_t%02d' % (i + 1)
            date_fields.append(fn)
            fields.append(QgsField(fn, QVariant.Double))
        for name in ('ag_mean', 'ag_std', 'ag_min', 'ag_max', 'ag_range', 'ag_trend'):
            fields.append(QgsField(name, QVariant.Double))
        fields.append(QgsField('ag_n_dates', QVariant.Int))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, fields, src.wkbType(), src.sourceCrs())
        if sink is None:
            raise QgsProcessingException('Impossible de créer la couche de sortie.')

        # Cache raster blocks once; each block is read at native resolution.
        raster_data = []
        for raster in rasters:
            ext = raster.extent(); cols = raster.width(); rows = raster.height()
            block = raster.dataProvider().block(1, ext, cols, rows)
            if block is None or block.isEmpty():
                raise QgsProcessingException('Impossible de lire raster : ' + raster.name())
            raster_data.append((raster, ext, cols, rows, ext.width()/cols, ext.height()/rows, block))

        total = max(src.featureCount(), 1); done = 0
        for feat in src.getFeatures():
            if feedback.isCanceled():
                break
            geom = feat.geometry()
            means = []
            for raster, ext, cols, rows, dx, dy, block in raster_data:
                box = geom.boundingBox().intersect(ext)
                vals = []
                if not box.isEmpty() and dx > 0 and dy > 0:
                    c0 = max(0, int((box.xMinimum()-ext.xMinimum())/dx)); c1 = min(cols-1, int((box.xMaximum()-ext.xMinimum())/dx))
                    r0 = max(0, int((ext.yMaximum()-box.yMaximum())/dy)); r1 = min(rows-1, int((ext.yMaximum()-box.yMinimum())/dy))
                    for rr in range(r0, r1+1):
                        if feedback.isCanceled(): break
                        y = ext.yMaximum()-(rr+0.5)*dy
                        for cc in range(c0, c1+1):
                            x = ext.xMinimum()+(cc+0.5)*dx
                            if not geom.contains(QgsGeometry.fromPointXY(QgsPointXY(x, y))):
                                continue
                            if block.isNoData(rr, cc):
                                continue
                            v = float(block.value(rr, cc))
                            if math.isfinite(v): vals.append(v)
                means.append(sum(vals)/len(vals) if vals else None)

            valid = [(idx+1, v) for idx, v in enumerate(means) if v is not None]
            if valid:
                values = [v for _, v in valid]
                mean = sum(values)/len(values)
                std = math.sqrt(sum((v-mean)**2 for v in values)/len(values))
                minimum = min(values); maximum = max(values); amplitude = maximum-minimum
                if len(valid) >= 2:
                    xs = [x for x, _ in valid]; ys = [y for _, y in valid]
                    xmean = sum(xs)/len(xs); ymean = sum(ys)/len(ys)
                    denom = sum((x-xmean)**2 for x in xs)
                    trend = sum((x-xmean)*(y-ymean) for x,y in zip(xs,ys))/denom if denom else None
                else:
                    trend = None
            else:
                mean = std = minimum = maximum = amplitude = trend = None
            out = QgsFeature(fields); out.setGeometry(geom)
            out.setAttributes(feat.attributes()+means+[mean,std,minimum,maximum,amplitude,trend,len(valid)])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            done += 1; feedback.setProgress(int(done*100/total))
        return {self.OUTPUT: dest}
