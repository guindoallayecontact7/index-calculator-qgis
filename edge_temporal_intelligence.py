# -*- coding: utf-8 -*-
"""Index Calculator Pro - Edge & Multi-date Boundary Intelligence.
Creates an exploratory boundary-candidate score from local spatial gradients and
multi-date index change. It is NOT a parcel boundary probability model.
"""
import math

def _normalize01(a, valid):
    import numpy as np
    out=np.zeros_like(a,dtype='float32')
    vals=a[valid]
    if vals.size == 0: return out
    lo=float(np.nanpercentile(vals,2)); hi=float(np.nanpercentile(vals,98))
    if not math.isfinite(lo) or not math.isfinite(hi) or hi<=lo:
        return out
    out[valid]=np.clip((a[valid]-lo)/(hi-lo),0,1)
    return out

def boundary_candidate_score(date1, date2, valid, temporal_weight=0.35):
    """0..1 exploratory score from max local gradient + temporal change."""
    import numpy as np
    def gradient(a):
        gx=np.zeros_like(a,dtype='float32'); gy=np.zeros_like(a,dtype='float32')
        gx[:,1:-1]=(a[:,2:]-a[:,:-2])*0.5
        gy[1:-1,:]=(a[2:,:]-a[:-2,:])*0.5
        return np.sqrt(gx*gx+gy*gy)
    g=np.maximum(gradient(date1),gradient(date2))
    change=np.abs(date2-date1)
    ng=_normalize01(g,valid); nc=_normalize01(change,valid)
    w=float(np.clip(temporal_weight,0,1))
    score=((1-w)*ng+w*nc).astype('float32')
    score[~valid]=np.nan
    return score

class EdgeTemporalIntelligenceAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            D1='INDEX_DATE1'; D2='INDEX_DATE2'; W='TEMPORAL_WEIGHT'; OUT='OUTPUT'
            def name(self): return 'ic_edge_temporal_boundary_score'
            def displayName(self): return 'Edge and Multi-date Boundary Candidates'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Produces an exploratory 0-1 boundary-candidate score combining spatial gradients from two dates and temporal change. '
                       'Higher scores indicate stronger edge/change signals, not confirmed parcel boundaries. Inputs must be single-band, grid-aligned local rasters.')
            def createInstance(self): return EdgeTemporalIntelligenceAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterRasterLayer,QgsProcessingParameterNumber,QgsProcessingParameterRasterDestination
                self.addParameter(QgsProcessingParameterRasterLayer(self.D1,'Index raster - date 1'))
                self.addParameter(QgsProcessingParameterRasterLayer(self.D2,'Index raster - date 2'))
                self.addParameter(QgsProcessingParameterNumber(self.W,'Temporal change weight',QgsProcessingParameterNumber.Type.Double,0.35,minValue=0,maxValue=1))
                self.addParameter(QgsProcessingParameterRasterDestination(self.OUT,'Boundary candidate score raster'))
            def processAlgorithm(self,parameters,context,feedback):
                import numpy as np
                from osgeo import gdal
                from qgis.core import QgsProcessingException
                l1=self.parameterAsRasterLayer(parameters,self.D1,context); l2=self.parameterAsRasterLayer(parameters,self.D2,context)
                if not l1 or not l2 or not l1.isValid() or not l2.isValid(): raise QgsProcessingException('Invalid raster input.')
                d1=gdal.Open(l1.source(),gdal.GA_ReadOnly); d2=gdal.Open(l2.source(),gdal.GA_ReadOnly)
                if d1 is None or d2 is None: raise QgsProcessingException('GDAL cannot open inputs; use local GeoTIFFs.')
                if d1.RasterCount!=1 or d2.RasterCount!=1: raise QgsProcessingException('Both inputs must be single-band index rasters.')
                if (d1.RasterXSize,d1.RasterYSize,d1.GetGeoTransform(),d1.GetProjection()) != (d2.RasterXSize,d2.RasterYSize,d2.GetGeoTransform(),d2.GetProjection()):
                    raise QgsProcessingException('Inputs must be exactly aligned (dimensions, geotransform, CRS). Harmonize grids first.')
                a=d1.GetRasterBand(1).ReadAsArray().astype('float32'); b=d2.GetRasterBand(1).ReadAsArray().astype('float32')
                nd1=d1.GetRasterBand(1).GetNoDataValue(); nd2=d2.GetRasterBand(1).GetNoDataValue()
                valid=np.isfinite(a)&np.isfinite(b)
                if nd1 is not None: valid &= a!=nd1
                if nd2 is not None: valid &= b!=nd2
                if not valid.any(): raise QgsProcessingException('No valid common pixels.')
                weight=self.parameterAsDouble(parameters,self.W,context)
                score=boundary_candidate_score(a,b,valid,weight)
                path=self.parameterAsOutputLayer(parameters,self.OUT,context)
                drv=gdal.GetDriverByName('GTiff'); out=drv.Create(path,d1.RasterXSize,d1.RasterYSize,1,gdal.GDT_Float32,['COMPRESS=LZW'])
                if out is None: raise QgsProcessingException('Unable to create output raster.')
                out.SetGeoTransform(d1.GetGeoTransform()); out.SetProjection(d1.GetProjection())
                band=out.GetRasterBand(1); band.WriteArray(np.where(valid,score,-9999).astype('float32')); band.SetNoDataValue(-9999); band.FlushCache()
                out.FlushCache(); out=None; d1=None; d2=None
                feedback.pushInfo('Boundary candidate score created. Interpret as exploratory edge/change signal, not parcel probability.')
                return {self.OUT:path}
        return _Alg()
