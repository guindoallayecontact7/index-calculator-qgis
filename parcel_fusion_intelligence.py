# -*- coding: utf-8 -*-
"""Index Calculator Pro - explainable parcel candidate fusion scoring."""
import math


def normalize_unit(value, low=0.0, high=1.0):
    """Clip finite values to a unit interval after linear scaling."""
    try:
        v=float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or high <= low:
        return None
    return max(0.0, min(1.0, (v-low)/(high-low)))


def fusion_score(components, weights):
    """Weighted average over available components; missing values are omitted and weights renormalized."""
    valid=[]
    for key, value in components.items():
        try:
            v=float(value); w=float(weights.get(key,0.0))
        except (TypeError, ValueError):
            continue
        if math.isfinite(v) and math.isfinite(w) and w>0:
            valid.append((max(0.0,min(1.0,v)),w))
    if not valid:
        return None, 0.0, 0
    total=sum(w for _,w in valid)
    return sum(v*w for v,w in valid)/total, total, len(valid)


def confidence_from_components(component_count, coverage=None):
    """Conservative evidence coverage label, not empirical probability."""
    if component_count<=0:
        return 'NO_DATA'
    if coverage is not None:
        try:
            c=float(coverage)
            if not math.isfinite(c): c=None
        except (TypeError, ValueError):
            c=None
    else:
        c=None
    if component_count>=3 and (c is None or c>=70):
        return 'HIGH'
    if component_count>=2 and (c is None or c>=35):
        return 'MEDIUM'
    return 'LOW'


class ParcelFusionIntelligenceAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            INPUT='INPUT'; SPECTRAL_FIELD='SPECTRAL_FIELD'; TEMPORAL_FIELD='TEMPORAL_FIELD'; EDGE_FIELD='EDGE_FIELD'; SHAPE_FIELD='SHAPE_FIELD'; COVERAGE_FIELD='COVERAGE_FIELD'; WS='WS'; WT='WT'; WE='WE'; WG='WG'; OUTPUT='OUTPUT'
            def name(self): return 'ic_parcel_fusion_intelligence'
            def displayName(self): return 'Parcel Fusion - Candidate Quality Score'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Combines available spectral, temporal, boundary and geometry indicators into an explainable 0-1 candidate quality score. '
                       'Field values are expected to be normalized to 0-1 except spectral NDVI-like field, which is mapped from -1..1. '
                       'Weights are renormalized when components are missing. Score is heuristic and is not a probability or parcel truth.')
            def createInstance(self): return ParcelFusionIntelligenceAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterFeatureSource,QgsProcessingParameterFeatureSink,QgsProcessingParameterString,QgsProcessingParameterNumber
                self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,'Candidate polygons'))
                self.addParameter(QgsProcessingParameterString(self.SPECTRAL_FIELD,'Spectral field (NDVI-like; blank to omit)',defaultValue='cp_mean',optional=True))
                self.addParameter(QgsProcessingParameterString(self.TEMPORAL_FIELD,'Temporal score field (0-1; blank to omit)',defaultValue='',optional=True))
                self.addParameter(QgsProcessingParameterString(self.EDGE_FIELD,'Boundary score field (0-1; blank to omit)',defaultValue='',optional=True))
                self.addParameter(QgsProcessingParameterString(self.SHAPE_FIELD,'Geometry score field (0-1; blank to omit)',defaultValue='shape_score',optional=True))
                self.addParameter(QgsProcessingParameterString(self.COVERAGE_FIELD,'Coverage field (optional; percent 0-100)',defaultValue='cp_cover_pct',optional=True))
                for key,label,default in [(self.WS,'Spectral weight',0.35),(self.WT,'Temporal weight',0.25),(self.WE,'Boundary weight',0.20),(self.WG,'Geometry weight',0.20)]:
                    self.addParameter(QgsProcessingParameterNumber(key,label,QgsProcessingParameterNumber.Type.Double,defaultValue=default,minValue=0,maxValue=1))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Candidates with fusion metrics'))
            def processAlgorithm(self,parameters,context,feedback):
                from qgis.core import QgsProcessingException,QgsFields,QgsField,QgsFeature,QgsFeatureSink
                from qgis.PyQt.QtCore import QVariant
                source=self.parameterAsSource(parameters,self.INPUT,context)
                if source is None: raise QgsProcessingException('Invalid polygon source.')
                names={self.SPECTRAL_FIELD:self.parameterAsString(parameters,self.SPECTRAL_FIELD,context).strip(),self.TEMPORAL_FIELD:self.parameterAsString(parameters,self.TEMPORAL_FIELD,context).strip(),self.EDGE_FIELD:self.parameterAsString(parameters,self.EDGE_FIELD,context).strip(),self.SHAPE_FIELD:self.parameterAsString(parameters,self.SHAPE_FIELD,context).strip(),self.COVERAGE_FIELD:self.parameterAsString(parameters,self.COVERAGE_FIELD,context).strip()}
                weights={'spectral':self.parameterAsDouble(parameters,self.WS,context),'temporal':self.parameterAsDouble(parameters,self.WT,context),'boundary':self.parameterAsDouble(parameters,self.WE,context),'geometry':self.parameterAsDouble(parameters,self.WG,context)}
                if sum(weights.values())<=0: raise QgsProcessingException('At least one fusion weight must be greater than zero.')
                field_indices={k:source.fields().indexOf(n) if n else -1 for k,n in names.items()}
                for k in (self.TEMPORAL_FIELD,self.EDGE_FIELD,self.SHAPE_FIELD):
                    n=names[k]
                    if n and field_indices[k]<0: raise QgsProcessingException('Configured field not found: '+n)
                if names[self.SPECTRAL_FIELD] and field_indices[self.SPECTRAL_FIELD]<0: raise QgsProcessingException('Spectral field not found: '+names[self.SPECTRAL_FIELD])
                fields=QgsFields(source.fields())
                additions=[('fusion_score',QVariant.Double),('fusion_n',QVariant.Int),('fusion_conf',QVariant.String),('fusion_spectral',QVariant.Double),('fusion_temporal',QVariant.Double),('fusion_boundary',QVariant.Double),('fusion_geometry',QVariant.Double),('fusion_coverage',QVariant.Double)]
                for n,t in additions:
                    if fields.indexOf(n)<0: fields.append(QgsField(n,t))
                sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,source.wkbType(),source.sourceCrs())
                if sink is None: raise QgsProcessingException('Unable to create output sink.')
                def attr(f,idx):
                    if idx<0: return None
                    v=f.attribute(idx)
                    try: return float(v) if v is not None else None
                    except (TypeError,ValueError): return None
                total=source.featureCount(); done=0
                for f in source.getFeatures():
                    if feedback.isCanceled(): break
                    raw_spec=attr(f,field_indices[self.SPECTRAL_FIELD]); spec=normalize_unit(raw_spec,0,1) if raw_spec is not None else None
                    temporal=normalize_unit(attr(f,field_indices[self.TEMPORAL_FIELD]))
                    boundary=normalize_unit(attr(f,field_indices[self.EDGE_FIELD]))
                    geom=normalize_unit(attr(f,field_indices[self.SHAPE_FIELD]))
                    coverage=attr(f,field_indices[self.COVERAGE_FIELD])
                    comps={'spectral':spec,'temporal':temporal,'boundary':boundary,'geometry':geom}
                    score,total_w,n=fusion_score(comps,weights); conf=confidence_from_components(n,coverage)
                    out=QgsFeature(fields); out.setGeometry(f.geometry()); attrs=list(f.attributes())
                    while len(attrs)<fields.count(): attrs.append(None)
                    vals={'fusion_score':score,'fusion_n':n,'fusion_conf':conf,'fusion_spectral':spec,'fusion_temporal':temporal,'fusion_boundary':boundary,'fusion_geometry':geom,'fusion_coverage':coverage}
                    for name,val in vals.items():
                        idx=fields.indexOf(name)
                        if idx>=0: attrs[idx]=val
                    out.setAttributes(attrs); sink.addFeature(out,QgsFeatureSink.Flag.FastInsert)
                    done+=1
                    if total: feedback.setProgress(int(done*100/total))
                feedback.pushInfo(f'Fusion metrics written for {done} candidate features. Score is heuristic, not a probability.')
                return {self.OUTPUT:dest}
        return _Alg()
