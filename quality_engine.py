# -*- coding: utf-8 -*-
"""Index Calculator Pro Quality & Uncertainty Engine.
Raster QA is chunked to limit memory usage. Requires QGIS/GDAL Python runtime.
"""
from html import escape

try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                          QgsProcessingParameterFileDestination, QgsProcessingException)
    from qgis.PyQt.QtCore import QCoreApplication

    def _html_report(title, rows, note=''):
        body = ''.join(f'<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>' for k, v in rows)
        return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:950px;margin:28px auto;padding:0 18px;color:#26332b}}h1{{color:#236b42}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #d8ded9;text-align:left}}th{{background:#eef5ef;width:35%}}.note{{padding:12px;background:#fff4d6;border-radius:8px}}</style></head><body><h1>{escape(title)}</h1><p class='note'>{escape(note)}</p><table>{body}</table></body></html>"""

    class RasterQualityAuditAlgorithm(QgsProcessingAlgorithm):
        INPUT='INPUT'; OUTPUT='OUTPUT'
        def name(self): return 'raster_quality_audit'
        def displayName(self): return 'Raster Quality Audit'
        def group(self): return 'Quality control'
        def groupId(self): return 'quality_uncertainty'
        def shortHelpString(self):
            return ('Audits a raster: CRS, size, resolution, NoData, non-finite values, range and valid coverage. '
                   'Reads by blocks to limit memory use. The check is technical, not an agronomic validation.')
        def createInstance(self): return RasterQualityAuditAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, 'Raster to audit'))
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT, 'HTML quality report', 'HTML'))
        def processAlgorithm(self, parameters, context, feedback):
            layer=self.parameterAsRasterLayer(parameters,self.INPUT,context)
            if layer is None or not layer.isValid(): raise QgsProcessingException('Raster invalide ou illisible.')
            try:
                from osgeo import gdal
                import numpy as np
            except Exception as e:
                raise QgsProcessingException('GDAL and NumPy are required in the QGIS environment: '+str(e))
            ds=gdal.Open(layer.source())
            if ds is None: raise QgsProcessingException('GDAL cannot open the raster source.')
            rows=[('Nom',layer.name()),('Source',layer.source()),('CRS',layer.crs().authid() or layer.crs().description()),
                  ('Dimensions',f'{ds.RasterXSize} × {ds.RasterYSize} pixels'),('Band count',ds.RasterCount),
                  ('Resolution',str(layer.rasterUnitsPerPixelX())+' × '+str(layer.rasterUnitsPerPixelY())),
                  ('Extent',str(layer.extent().toString())),('Data type',str(ds.GetRasterBand(1).DataType))]
            for b in range(1,ds.RasterCount+1):
                band=ds.GetRasterBand(b); nodata=band.GetNoDataValue(); valid=invalid=0; mn=None; mx=None
                block_rows=max(1,min(512,band.GetBlockSize()[1] or 256))
                for y in range(0,ds.RasterYSize,block_rows):
                    if feedback.isCanceled(): return {}
                    h=min(block_rows,ds.RasterYSize-y)
                    arr=band.ReadAsArray(0,y,ds.RasterXSize,h)
                    if arr is None: continue
                    finite=np.isfinite(arr)
                    mask=finite if nodata is None else (finite & (arr!=nodata))
                    valid_count=int(mask.sum()); total=arr.size
                    valid+=valid_count; invalid+=(total-valid_count)
                    if valid_count:
                        vals=arr[mask]
                        local_min=float(vals.min()); local_max=float(vals.max())
                        mn=local_min if mn is None else min(mn,local_min); mx=local_max if mx is None else max(mx,local_max)
                total=ds.RasterXSize*ds.RasterYSize; coverage=100*valid/total if total else 0
                rows.extend([(f'Band {b} - declared NoData',nodata if nodata is not None else 'Not defined'),
                    (f'Band {b} - valid pixels',valid),(f'Band {b} - invalid/NoData pixels',invalid),
                    (f'Band {b} - valid coverage',f'{coverage:.2f}%'),
                    (f'Band {b} - valid minimum',mn if mn is not None else 'No valid value'),
                    (f'Band {b} - valid maximum',mx if mx is not None else 'No valid value')])
                feedback.pushInfo(f'Band {b}: valid coverage {coverage:.2f}%')
            path=self.parameterAsFileOutput(parameters,self.OUTPUT,context)
            with open(path,'w',encoding='utf-8') as f:
                f.write(_html_report('Index Calculator Pro - Raster Quality Audit',rows,
                    'Technical raster audit. NoData values and statistics do not guarantee radiometric, atmospheric or geometric quality, nor agronomic relevance.'))
            ds=None
            return {self.OUTPUT:path}

    class RasterAlignmentCheckAlgorithm(QgsProcessingAlgorithm):
        A='A'; B='B'; OUTPUT='OUTPUT'
        def name(self): return 'raster_alignment_check'
        def displayName(self): return 'Raster Alignment Check'
        def group(self): return 'Quality control'
        def groupId(self): return 'quality_uncertainty'
        def shortHelpString(self): return 'Compares the CRS, dimensions, extent and resolution of two rasters. Does not reproject or resample.'
        def createInstance(self): return RasterAlignmentCheckAlgorithm()
        def initAlgorithm(self,config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.A,'Raster A'))
            self.addParameter(QgsProcessingParameterRasterLayer(self.B,'Raster B'))
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT,'HTML comparison report','HTML'))
        def processAlgorithm(self,parameters,context,feedback):
            a=self.parameterAsRasterLayer(parameters,self.A,context); b=self.parameterAsRasterLayer(parameters,self.B,context)
            if a is None or b is None or not a.isValid() or not b.isValid(): raise QgsProcessingException('Raster A ou B invalide.')
            checks=[('CRS identique',a.crs()==b.crs()),('Dimensions identiques',a.width()==b.width() and a.height()==b.height()),
                   ('Same extent',a.extent()==b.extent()),('Same resolution',abs(a.rasterUnitsPerPixelX()-b.rasterUnitsPerPixelX())<1e-12 and abs(a.rasterUnitsPerPixelY()-b.rasterUnitsPerPixelY())<1e-12)]
            rows=[('Raster A',a.name()),('Raster B',b.name())]+[(name,'OK' if ok else 'DIFFERENT') for name,ok in checks]
            rows.append(('Alignement complet','COMPATIBLE' if all(ok for _,ok in checks) else 'NON COMPATIBLE'))
            path=self.parameterAsFileOutput(parameters,self.OUTPUT,context)
            with open(path,'w',encoding='utf-8') as f: f.write(_html_report('Index Calculator Pro - Raster Alignment Check',rows,'This check compares the grids. It does not verify that pixels actually coincide, nor the registration quality.'))
            feedback.pushInfo('Alignement complet: '+('compatible' if all(ok for _,ok in checks) else 'non compatible'))
            return {self.OUTPUT:path}
except ImportError:
    RasterQualityAuditAlgorithm = None
    RasterAlignmentCheckAlgorithm = None
