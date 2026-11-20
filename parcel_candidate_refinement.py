# -*- coding: utf-8 -*-
"""Index Calculator V4.5 - configurable, non-destructive candidate refinement.
Candidate features are routed to accepted/rejected outputs with reason fields.
No input geometry is altered or repaired.
"""
import math


def refinement_decision(area_ha, shape_score=None, topo_status=None,
                      min_area_ha=0.0, max_area_ha=0.0, min_shape_score=0.0,
                      reject_invalid=True, reject_overlap=False):
    reasons=[]
    try: area=float(area_ha)
    except (TypeError,ValueError): area=float('nan')
    if not math.isfinite(area): reasons.append('AREA_UNAVAILABLE')
    else:
        if min_area_ha>0 and area<min_area_ha: reasons.append('BELOW_MIN_AREA')
        if max_area_ha>0 and area>max_area_ha: reasons.append('ABOVE_MAX_AREA')
    if min_shape_score>0:
        try: score=float(shape_score)
        except (TypeError,ValueError): score=float('nan')
        if not math.isfinite(score): reasons.append('SHAPE_SCORE_MISSING')
        elif score<min_shape_score: reasons.append('LOW_SHAPE_SCORE')
    status=str(topo_status or '').strip().upper()
    if reject_invalid and status=='INVALID': reasons.append('INVALID_GEOMETRY')
    if reject_overlap and status=='OVERLAP': reasons.append('OVERLAP')
    return (not reasons, '|'.join(reasons) if reasons else 'PASS')


class ParcelCandidateRefinementAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            INPUT='INPUT'; MIN_AREA='MIN_AREA'; MAX_AREA='MAX_AREA'; SHAPE_FIELD='SHAPE_FIELD'; MIN_SHAPE='MIN_SHAPE'; REJECT_INVALID='REJECT_INVALID'; REJECT_OVERLAP='REJECT_OVERLAP'; ACCEPTED='ACCEPTED'; REJECTED='REJECTED'
            def name(self): return 'ic_parcel_candidate_refinement'
            def displayName(self): return 'Parcel Candidate Refinement - Rule-based Filtering'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Routes candidate polygons to accepted or rejected outputs using configurable area, optional shape score, '
                        'and optional topology-status rules. Adds a transparent reason field. Original geometries are preserved. '
                        'This is rule-based filtering, not proof of agricultural parcels.')
            def createInstance(self): return ParcelCandidateRefinementAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterFeatureSource,QgsProcessingParameterFeatureSink,QgsProcessingParameterNumber,QgsProcessingParameterString,QgsProcessingParameterBoolean
                self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,'Candidate polygons'))
                self.addParameter(QgsProcessingParameterNumber(self.MIN_AREA,'Minimum area (ha; 0 disables)',QgsProcessingParameterNumber.Double,defaultValue=0,minValue=0))
                self.addParameter(QgsProcessingParameterNumber(self.MAX_AREA,'Maximum area (ha; 0 disables)',QgsProcessingParameterNumber.Double,defaultValue=0,minValue=0))
                self.addParameter(QgsProcessingParameterString(self.SHAPE_FIELD,'Optional shape score field (blank disables)',defaultValue='shape_score'))
                self.addParameter(QgsProcessingParameterNumber(self.MIN_SHAPE,'Minimum shape score (0 disables)',QgsProcessingParameterNumber.Double,defaultValue=0,minValue=0,maxValue=1))
                self.addParameter(QgsProcessingParameterBoolean(self.REJECT_INVALID,'Reject invalid geometries',defaultValue=True))
                self.addParameter(QgsProcessingParameterBoolean(self.REJECT_OVERLAP,'Reject topo_status=OVERLAP (if field exists)',defaultValue=False))
                self.addParameter(QgsProcessingParameterFeatureSink(self.ACCEPTED,'Accepted candidates'))
                self.addParameter(QgsProcessingParameterFeatureSink(self.REJECTED,'Rejected candidates'))
            def processAlgorithm(self,parameters,context,feedback):
                from qgis.core import QgsProcessingException,QgsFields,QgsField,QgsFeature,QgsFeatureSink,QgsWkbTypes,QgsUnitTypes
                from qgis.PyQt.QtCore import QVariant
                source=self.parameterAsSource(parameters,self.INPUT,context)
                if source is None: raise QgsProcessingException('Invalid polygon source.')
                if QgsWkbTypes.geometryType(source.wkbType()) != QgsWkbTypes.PolygonGeometry: raise QgsProcessingException('Input must contain polygon geometries.')
                crs=source.sourceCrs()
                if crs.isGeographic(): raise QgsProcessingException('Use a projected CRS for area thresholds.')
                factor=QgsUnitTypes.fromUnitToUnitFactor(crs.mapUnits(),QgsUnitTypes.DistanceMeters)
                minarea=self.parameterAsDouble(parameters,self.MIN_AREA,context); maxarea=self.parameterAsDouble(parameters,self.MAX_AREA,context)
                if maxarea>0 and minarea>maxarea: raise QgsProcessingException('Maximum area must be greater than or equal to minimum area.')
                shape_field=self.parameterAsString(parameters,self.SHAPE_FIELD,context).strip(); shape_idx=source.fields().indexOf(shape_field) if shape_field else -1
                minshape=self.parameterAsDouble(parameters,self.MIN_SHAPE,context)
                if minshape>0 and shape_idx<0: raise QgsProcessingException('Minimum shape score is enabled but the configured field is missing.')
                topo_idx=source.fields().indexOf('topo_status')
                reject_invalid=self.parameterAsBool(parameters,self.REJECT_INVALID,context); reject_overlap=self.parameterAsBool(parameters,self.REJECT_OVERLAP,context)
                fields=QgsFields(source.fields())
                extra=[('refine_status',QVariant.String),('refine_reason',QVariant.String),('refine_area_ha',QVariant.Double),('refine_shape',QVariant.Double)]
                idxs={}
                for name,typ in extra:
                    idx=fields.indexOf(name)
                    if idx<0: fields.append(QgsField(name,typ)); idx=fields.indexOf(name)
                    idxs[name]=idx
                accepted,adest=self.parameterAsSink(parameters,self.ACCEPTED,context,fields,source.wkbType(),crs)
                rejected,rdest=self.parameterAsSink(parameters,self.REJECTED,context,fields,source.wkbType(),crs)
                if accepted is None or rejected is None: raise QgsProcessingException('Could not create output sinks.')
                total=source.featureCount(); done=0; nacc=0; nrej=0
                for f in source.getFeatures():
                    if feedback.isCanceled(): break
                    g=f.geometry(); area_ha=g.area()*factor*factor/10000.0 if f.hasGeometry() and not g.isNull() else float('nan')
                    shape=None
                    if shape_idx>=0:
                        try: shape=float(f[shape_field])
                        except (TypeError,ValueError): shape=None
                    topo=f['topo_status'] if topo_idx>=0 else None
                    keep,reason=refinement_decision(area_ha,shape,topo,minarea,maxarea,minshape,reject_invalid,reject_overlap)
                    if reject_invalid and (not f.hasGeometry() or g.isNull() or not g.isGeosValid()):
                        keep=False; reason=('INVALID_GEOMETRY|' + reason) if reason!='PASS' else 'INVALID_GEOMETRY'
                    nf=QgsFeature(fields); nf.setGeometry(g)
                    attrs=list(f.attributes())
                    while len(attrs)<fields.count(): attrs.append(None)
                    vals={'refine_status':'ACCEPTED' if keep else 'REJECTED','refine_reason':reason,'refine_area_ha':area_ha if math.isfinite(area_ha) else None,'refine_shape':shape}
                    for name,value in vals.items(): attrs[idxs[name]]=value
                    nf.setAttributes(attrs)
                    if keep: accepted.addFeature(nf,QgsFeatureSink.FastInsert); nacc+=1
                    else: rejected.addFeature(nf,QgsFeatureSink.FastInsert); nrej+=1
                    done+=1
                    if total: feedback.setProgress(int(done*100/total))
                feedback.pushInfo(f'Refinement complete: {nacc} accepted; {nrej} rejected. Input geometries were not modified.')
                return {self.ACCEPTED:adest,self.REJECTED:rdest}
        return _Alg()
