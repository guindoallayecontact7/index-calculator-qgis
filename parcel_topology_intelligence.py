# -*- coding: utf-8 -*-
"""Index Calculator Pro - non-destructive polygon topology audit.
The algorithm preserves input geometries and reports validity, overlaps and
basic geometry characteristics. It does not repair or infer missing boundaries.
"""
import math


def classify_overlap(overlap_area_m2, tolerance_m2=0.01):
    try:
        value=float(overlap_area_m2)
        tolerance=float(tolerance_m2)
    except (TypeError, ValueError):
        return 'UNKNOWN'
    if not math.isfinite(value) or not math.isfinite(tolerance) or tolerance < 0:
        return 'UNKNOWN'
    return 'OVERLAP' if value > tolerance else 'OK'



class ParcelTopologyAuditAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            INPUT='INPUT'; OVERLAP_TOL='OVERLAP_TOL'; OUTPUT='OUTPUT'
            def name(self): return 'ic_parcel_topology_audit'
            def displayName(self): return 'Parcel Topology Audit'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Non-destructively audits polygon geometry validity, part count, area, perimeter, '
                        'neighbor count and pairwise overlap area. It preserves source geometry and attributes. '
                        'Gap detection requires a reference coverage and is not performed here.')
            def createInstance(self): return ParcelTopologyAuditAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterFeatureSource,QgsProcessingParameterFeatureSink,QgsProcessingParameterNumber
                self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,'Candidate polygons'))
                self.addParameter(QgsProcessingParameterNumber(self.OVERLAP_TOL,'Overlap reporting tolerance (m²)',QgsProcessingParameterNumber.Double,defaultValue=0.01,minValue=0))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Polygons with topology audit fields'))
            def processAlgorithm(self,parameters,context,feedback):
                from qgis.core import (QgsProcessingException,QgsFields,QgsField,QgsFeature,QgsFeatureSink,
                                    QgsSpatialIndex,QgsWkbTypes,QgsUnitTypes)
                from qgis.PyQt.QtCore import QVariant
                source=self.parameterAsSource(parameters,self.INPUT,context)
                if source is None: raise QgsProcessingException('Invalid polygon source.')
                if QgsWkbTypes.geometryType(source.wkbType()) != QgsWkbTypes.PolygonGeometry:
                    raise QgsProcessingException('Input must be polygon geometry.')
                crs=source.sourceCrs()
                if crs.isGeographic(): raise QgsProcessingException('Use a projected CRS with linear units for topology area metrics.')
                factor=QgsUnitTypes.fromUnitToUnitFactor(crs.mapUnits(),QgsUnitTypes.DistanceMeters)
                tolerance=self.parameterAsDouble(parameters,self.OVERLAP_TOL,context)
                feats=list(source.getFeatures())
                index=QgsSpatialIndex(); geoms={}; valid={}; part_count={}
                for f in feats:
                    if f.hasGeometry() and not f.geometry().isNull():
                        g=f.geometry(); geoms[f.id()]=g; valid[f.id()]=bool(g.isGeosValid())
                        part_count[f.id()]=int(g.constGet().partCount()) if g.constGet() else 0
                        index.addFeature(f)
                overlaps={fid:0.0 for fid in geoms}; neighbors={fid:0 for fid in geoms}; overlap_pairs={fid:0 for fid in geoms}
                # Pairwise exact intersection only for bbox-neighbors; process each pair once.
                for fid,g in geoms.items():
                    if feedback.isCanceled(): break
                    for other in index.intersects(g.boundingBox()):
                        if other<=fid or other not in geoms: continue
                        if not g.boundingBox().intersects(geoms[other].boundingBox()): continue
                        try:
                            inter=g.intersection(geoms[other])
                            area=inter.area()*factor*factor if not inter.isNull() else 0.0
                        except Exception:
                            area=0.0
                        if area>0:
                            overlaps[fid]+=area; overlaps[other]+=area
                            neighbors[fid]+=1; neighbors[other]+=1
                            if area>tolerance:
                                overlap_pairs[fid]+=1; overlap_pairs[other]+=1
                fields=QgsFields(source.fields())
                additions=[('topo_valid',QVariant.Bool),('topo_area_ha',QVariant.Double),('topo_perim_m',QVariant.Double),('topo_parts',QVariant.Int),('topo_neighbors',QVariant.Int),('topo_overlap_m2',QVariant.Double),('topo_overlap_n',QVariant.Int),('topo_status',QVariant.String)]
                indices={}
                for name,typ in additions:
                    idx=fields.indexOf(name)
                    if idx<0: fields.append(QgsField(name,typ)); idx=fields.indexOf(name)
                    indices[name]=idx
                sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,fields,source.wkbType(),crs)
                if sink is None: raise QgsProcessingException('Could not create output sink.')
                total=len(feats); done=0
                for f in feats:
                    if feedback.isCanceled(): break
                    fid=f.id(); g=geoms.get(fid)
                    if g is None:
                        area_ha=perim=None; is_valid=False; parts=0; overlap=0.0; n=0; pairs=0; status='NO_GEOMETRY'
                    else:
                        area_ha=g.area()*factor*factor/10000.0; perim=g.length()*factor
                        is_valid=valid.get(fid,False); parts=part_count.get(fid,1)
                        overlap=overlaps.get(fid,0.0); n=neighbors.get(fid,0); pairs=overlap_pairs.get(fid,0)
                        status='INVALID' if not is_valid else ('OVERLAP' if pairs else 'OK')
                    nf=QgsFeature(fields); nf.setGeometry(g if g is not None else f.geometry())
                    attrs=list(f.attributes())
                    while len(attrs)<fields.count(): attrs.append(None)
                    vals={'topo_valid':is_valid,'topo_area_ha':area_ha,'topo_perim_m':perim,'topo_parts':parts,'topo_neighbors':n,'topo_overlap_m2':overlap,'topo_overlap_n':pairs,'topo_status':status}
                    for name,value in vals.items(): attrs[indices[name]]=value
                    nf.setAttributes(attrs); sink.addFeature(nf,QgsFeatureSink.FastInsert)
                    done+=1
                    if total: feedback.setProgress(int(done*100/total))
                feedback.pushInfo(f'Topology audit completed for {done} polygons. Input geometry preserved; gaps are not assessed.')
                return {self.OUTPUT:dest}
        return _Alg()
