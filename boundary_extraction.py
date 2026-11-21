# -*- coding: utf-8 -*-
"""Index Calculator Pro - Boundary candidate extraction.
Thresholds a boundary-candidate score raster and polygonizes non-boundary regions.
These are candidate regions, not validated agricultural parcels.
"""

def label_regions(mask, scores, connectivity=4, min_pixels=1):
    """Pure NumPy/Python connected components with per-region size and score mean."""
    rows, cols = mask.shape
    labels = [[0 for _ in range(cols)] for __ in range(rows)]
    sizes, means = {}, {}
    neighbors = ((-1,0),(1,0),(0,-1),(0,1))
    if connectivity == 8:
        neighbors += ((-1,-1),(-1,1),(1,-1),(1,1))
    lab=0
    for r in range(rows):
        for c in range(cols):
            if not mask[r,c] or labels[r][c]: continue
            lab+=1; labels[r][c]=lab; stack=[(r,c)]; total=0.0; n=0
            while stack:
                y,x=stack.pop(); total+=float(scores[y,x]); n+=1
                for dy,dx in neighbors:
                    yy,xx=y+dy,x+dx
                    if 0<=yy<rows and 0<=xx<cols and mask[yy,xx] and not labels[yy][xx]:
                        labels[yy][xx]=lab; stack.append((yy,xx))
            sizes[lab]=n; means[lab]=total/n if n else float('nan')
    keep={k:(sizes[k]>=int(min_pixels)) for k in sizes}
    return labels,sizes,means,keep


class BoundaryExtractionAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            R='SCORE'; T='THRESHOLD'; MIN='MIN_PIXELS'; CON='CONNECTIVITY'; OUT='OUTPUT'
            def name(self): return 'ic_boundary_candidate_extraction'
            def displayName(self): return 'Boundary Extraction - Candidate Region Polygonizer'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Thresholds the boundary-candidate score and polygonizes connected regions below the threshold. '
                        'Outputs candidate regions only, not validated parcels. Use aligned rasters and inspect results.')
            def createInstance(self): return BoundaryExtractionAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import (QgsProcessingParameterRasterLayer,QgsProcessingParameterNumber,
                                    QgsProcessingParameterEnum,QgsProcessingParameterFeatureSink)
                self.addParameter(QgsProcessingParameterRasterLayer(self.R,'Boundary candidate score raster'))
                self.addParameter(QgsProcessingParameterNumber(self.T,'Boundary threshold',QgsProcessingParameterNumber.Type.Double,0.35,minValue=0,maxValue=1))
                self.addParameter(QgsProcessingParameterNumber(self.MIN,'Minimum region size (pixels)',QgsProcessingParameterNumber.Type.Integer,4,minValue=1))
                self.addParameter(QgsProcessingParameterEnum(self.CON,'Connectivity',options=['4-connected','8-connected'],defaultValue=0))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUT,'Candidate region polygons'))
            def processAlgorithm(self,parameters,context,feedback):
                import numpy as np
                from osgeo import gdal, ogr, osr
                from qgis.core import (QgsProcessingException,QgsFields,QgsField,QgsFeature,
                    QgsGeometry,QgsFeatureSink,QgsWkbTypes)
                from qgis.PyQt.QtCore import QVariant
                layer=self.parameterAsRasterLayer(parameters,self.R,context)
                if not layer or not layer.isValid(): raise QgsProcessingException('Invalid score raster.')
                ds=gdal.Open(layer.source(),gdal.GA_ReadOnly)
                if ds is None: raise QgsProcessingException('GDAL cannot open raster. Use a local GeoTIFF.')
                if ds.RasterCount!=1: raise QgsProcessingException('Input must be single-band score raster.')
                if ds.RasterXSize*ds.RasterYSize>4000000: raise QgsProcessingException('Raster exceeds 4 million pixels. Clip first.')
                score=ds.GetRasterBand(1).ReadAsArray().astype('float32'); nd=ds.GetRasterBand(1).GetNoDataValue()
                valid=np.isfinite(score)& (score>=0)& (score<=1)
                if nd is not None: valid &= score!=nd
                if not valid.any(): raise QgsProcessingException('No valid score values in range 0-1.')
                threshold=self.parameterAsDouble(parameters,self.T,context); minimum=self.parameterAsInt(parameters,self.MIN,context)
                conn=4 if self.parameterAsEnum(parameters,self.CON,context)==0 else 8
                # Low score cells represent candidate interiors; high scores are treated as edge barriers.
                region=valid & (score<=threshold)
                labels,sizes,means,keep=label_regions(region,score,conn,minimum)
                lab=np.asarray(labels,dtype='int32')
                feedback.pushInfo(f'Regions found: {len(sizes)}; retained: {sum(keep.values())}')
                mem=gdal.GetDriverByName('MEM').Create('',ds.RasterXSize,ds.RasterYSize,1,gdal.GDT_Int32)
                mem.SetGeoTransform(ds.GetGeoTransform()); mem.SetProjection(ds.GetProjection())
                # Exclude small regions from polygonization.
                for k,ok in keep.items():
                    if not ok: lab[lab==k]=0
                mem.GetRasterBand(1).WriteArray(lab); mem.GetRasterBand(1).SetNoDataValue(0)
                vds=ogr.GetDriverByName('Memory').CreateDataSource('candidate_regions')
                srs=osr.SpatialReference(); srs.ImportFromWkt(ds.GetProjection())
                if srs.IsGeographic(): raise QgsProcessingException('Area calculation requires a projected CRS with linear units. Reproject the score raster first.')
                linear_factor=float(srs.GetLinearUnits())
                vl=vds.CreateLayer('regions',srs,ogr.wkbPolygon)
                # Polygonize (GDAL >= 3.11) writes the region number into the
                # first field, so DN must be created first.
                vl.CreateField(ogr.FieldDefn('DN',ogr.OFTInteger))
                vl.CreateField(ogr.FieldDefn('cand_id',ogr.OFTInteger)); vl.CreateField(ogr.FieldDefn('pixel_n',ogr.OFTInteger))
                vl.CreateField(ogr.FieldDefn('edge_mean',ogr.OFTReal)); vl.CreateField(ogr.FieldDefn('area_ha',ogr.OFTReal))
                gdal.Polygonize(mem.GetRasterBand(1),mem.GetRasterBand(1).GetMaskBand(),vl,0,[],callback=None)
                fields=QgsFields(); fields.append(QgsField('cand_id',QVariant.Int)); fields.append(QgsField('pixel_n',QVariant.Int)); fields.append(QgsField('edge_mean',QVariant.Double)); fields.append(QgsField('area_ha',QVariant.Double))
                sink,dest=self.parameterAsSink(parameters,self.OUT,context,fields,QgsWkbTypes.Type.Polygon,layer.crs())
                if sink is None: raise QgsProcessingException('Could not create output vector sink.')
                gt=ds.GetGeoTransform(); pixel_area=abs(gt[1]*gt[5]-gt[2]*gt[4])*linear_factor*linear_factor; area_ha=pixel_area*sizes.get(1,0)/10000.0
                # polygonized DN maps to candidate labels
                for feat in vl:
                    if feedback.isCanceled(): break
                    cid=int(feat.GetField('DN'))
                    if cid<=0 or cid not in sizes or not keep.get(cid,False): continue
                    geom=QgsGeometry.fromWkt(feat.GetGeometryRef().ExportToWkt())
                    f=QgsFeature(fields); f.setGeometry(geom)
                    f.setAttributes([cid,int(sizes[cid]),float(means[cid]),float(pixel_area*sizes[cid]/10000.0)])
                    sink.addFeature(f,QgsFeatureSink.Flag.FastInsert)
                vds=None; mem=None; ds=None
                feedback.pushInfo('Candidate polygons extracted. These are low-score regions and require visual/field validation.')
                return {self.OUT:dest}
        return _Alg()
