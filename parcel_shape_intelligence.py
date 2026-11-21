# -*- coding: utf-8 -*-
"""Index Calculator Pro - explainable parcel candidate geometry metrics."""
import math

def shape_metrics(area_m2, perimeter_m, bbox_area_m2):
    """Return geometry metrics; values are shape descriptors, not parcel truth."""
    a=float(area_m2); p=float(perimeter_m); b=float(bbox_area_m2)
    if not all(math.isfinite(v) for v in (a,p,b)) or a<=0 or p<=0 or b<=0:
        return {'compactness':None,'elongation':None,'rectangularity':None,'complexity':None,'shape_score':None}
    compact=max(0.0,min(1.0,4.0*math.pi*a/(p*p)))
    rectangular=max(0.0,min(1.0,a/b))
    complexity=p/math.sqrt(a)
    # Shape score: compactness and rectangularity are weak geometric priors only.
    score=max(0.0,min(1.0,0.6*compact+0.4*rectangular))
    return {'compactness':compact,'elongation':None,'rectangularity':rectangular,'complexity':complexity,'shape_score':score}

def shape_metrics_with_bbox(area_m2, perimeter_m, bbox_width_m, bbox_height_m):
    b=float(bbox_width_m)*float(bbox_height_m)
    m=shape_metrics(area_m2,perimeter_m,b)
    w,h=abs(float(bbox_width_m)),abs(float(bbox_height_m))
    m['elongation']=max(w,h)/min(w,h) if min(w,h)>0 else None
    return m

class ParcelShapeIntelligenceAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            INPUT='INPUT'; OUTPUT='OUTPUT'
            def name(self): return 'ic_parcel_shape_intelligence'
            def displayName(self): return 'Parcel Shape Metrics'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Computes area, perimeter, compactness, bounding-box elongation, rectangularity, shape complexity and an explainable geometry score. '
                       'These metrics describe geometry only; they do not confirm agricultural parcel boundaries.')
            def createInstance(self): return ParcelShapeIntelligenceAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterFeatureSource,QgsProcessingParameterFeatureSink
                self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,'Candidate polygons',types=[]))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Polygons with geometry metrics'))
            def processAlgorithm(self,parameters,context,feedback):
                from qgis.core import (QgsProcessingException,QgsFields,QgsField,QgsFeature,QgsFeatureSink,QgsWkbTypes,QgsUnitTypes)
                from qgis.PyQt.QtCore import QVariant
                source=self.parameterAsSource(parameters,self.INPUT,context)
                if source is None: raise QgsProcessingException('Invalid polygon source.')
                crs=source.sourceCrs()
                if crs.isGeographic(): raise QgsProcessingException('Use a projected CRS with linear units; geographic degrees are not suitable for area/perimeter metrics.')
                factor=QgsUnitTypes.fromUnitToUnitFactor(crs.mapUnits(),QgsUnitTypes.DistanceUnit.DistanceMeters)
                if QgsWkbTypes.geometryType(source.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
                    raise QgsProcessingException('Input must contain polygon geometries.')
                fields=QgsFields(source.fields())
                additions=[('shape_area_ha',QVariant.Double),('shape_perim_m',QVariant.Double),('shape_compact',QVariant.Double),('shape_elong',QVariant.Double),('shape_rect',QVariant.Double),('shape_complex',QVariant.Double),('shape_score',QVariant.Double)]
                metric_index={}
                for n,t in additions:
                    idx=fields.indexOf(n)
                    if idx<0:
                        fields.append(QgsField(n,t)); idx=fields.indexOf(n)
                    metric_index[n]=idx
                sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,source.wkbType(),crs)
                if sink is None: raise QgsProcessingException('Could not create output sink.')
                total=source.featureCount(); done=0
                for f in source.getFeatures():
                    if feedback.isCanceled(): break
                    g=f.geometry()
                    area=g.area()*factor*factor; per=g.length()*factor
                    bb=g.boundingBox(); w=bb.width()*factor; h=bb.height()*factor; box=w*h
                    m=shape_metrics_with_bbox(area,per,w,h)
                    nf=QgsFeature(fields); nf.setGeometry(g)
                    attrs=list(f.attributes())
                    while len(attrs)<fields.count(): attrs.append(None)
                    values={'shape_area_ha':area/10000.0,'shape_perim_m':per,'shape_compact':m['compactness'],'shape_elong':m['elongation'],'shape_rect':m['rectangularity'],'shape_complex':m['complexity'],'shape_score':m['shape_score']}
                    for n,val in values.items(): attrs[metric_index[n]]=val
                    nf.setAttributes(attrs); sink.addFeature(nf,QgsFeatureSink.Flag.FastInsert)
                    done+=1
                    if total: feedback.setProgress(int(done*100/total))
                feedback.pushInfo(f'Geometry metrics added to {done} candidate polygons. Shape score is descriptive, not parcel validation.')
                return {self.OUTPUT:dest}
        return _Alg()
