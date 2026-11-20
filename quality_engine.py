# -*- coding: utf-8 -*-
"""Index Calculator V3.1 Quality & Uncertainty Engine.
Raster QA is chunked to limit memory usage. Requires QGIS/GDAL Python runtime.
"""
from html import escape

try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                          QgsProcessingParameterFileDestination, QgsProcessingException)
    from qgis.PyQt.QtCore import QCoreApplication

    def _html_report(title, rows, note=''):
        body = ''.join(f'<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>' for k, v in rows)
        return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:950px;margin:28px auto;padding:0 18px;color:#26332b}}h1{{color:#236b42}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #d8ded9;text-align:left}}th{{background:#eef5ef;width:35%}}.note{{padding:12px;background:#fff4d6;border-radius:8px}}</style></head><body><h1>{escape(title)}</h1><p class='note'>{escape(note)}</p><table>{body}</table></body></html>"""

    class RasterQualityAuditAlgorithm(QgsProcessingAlgorithm):
        INPUT='INPUT'; OUTPUT='OUTPUT'
        def name(self): return 'raster_quality_audit'
        def displayName(self): return 'Raster Quality Audit'
        def group(self): return 'Quality control'
        def groupId(self): return 'quality_uncertainty'
        def shortHelpString(self):
            return ('Audite un raster : CRS, taille, résolution, NoData, valeurs non finies, plage et couverture valide. '
                   'Lecture par blocs pour limiter la mémoire. Le contrôle est technique, pas une validation agronomique.')
        def createInstance(self): return RasterQualityAuditAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, 'Raster à auditer'))
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT, 'Rapport qualité HTML', 'HTML'))
        def processAlgorithm(self, parameters, context, feedback):
            layer=self.parameterAsRasterLayer(parameters,self.INPUT,context)
            if layer is None or not layer.isValid(): raise QgsProcessingException('Raster invalide ou illisible.')
            try:
                from osgeo import gdal
                import numpy as np
            except Exception as e:
                raise QgsProcessingException('GDAL et NumPy sont requis dans l’environnement QGIS: '+str(e))
            ds=gdal.Open(layer.source())
            if ds is None: raise QgsProcessingException('GDAL ne peut pas ouvrir la source raster.')
            rows=[('Nom',layer.name()),('Source',layer.source()),('CRS',layer.crs().authid() or layer.crs().description()),
                  ('Dimensions',f'{ds.RasterXSize} × {ds.RasterYSize} pixels'),('Nombre de bandes',ds.RasterCount),
                  ('Résolution',str(layer.rasterUnitsPerPixelX())+' × '+str(layer.rasterUnitsPerPixelY())),
                  ('Emprise',str(layer.extent().toString())),('Type de données',str(ds.GetRasterBand(1).DataType))]
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
                rows.extend([(f'Bande {b} - NoData déclaré',nodata if nodata is not None else 'Non défini'),
                    (f'Bande {b} - Pixels valides',valid),(f'Bande {b} - Pixels invalides/NoData',invalid),
                    (f'Bande {b} - Couverture valide',f'{coverage:.2f}%'),
                    (f'Bande {b} - Minimum valide',mn if mn is not None else 'Aucune valeur valide'),
                    (f'Bande {b} - Maximum valide',mx if mx is not None else 'Aucune valeur valide')])
                feedback.pushInfo(f'Bande {b}: couverture valide {coverage:.2f}%')
            path=self.parameterAsFileOutput(parameters,self.OUTPUT,context)
            with open(path,'w',encoding='utf-8') as f:
                f.write(_html_report('Index Calculator - Raster Quality Audit',rows,
                    'Audit technique du raster. Les valeurs NoData et les statistiques ne garantissent pas la qualité radiométrique, atmosphérique, géométrique ni la pertinence agronomique.'))
            ds=None
            return {self.OUTPUT:path}

    class RasterAlignmentCheckAlgorithm(QgsProcessingAlgorithm):
        A='A'; B='B'; OUTPUT='OUTPUT'
        def name(self): return 'raster_alignment_check'
        def displayName(self): return 'Raster Alignment Check'
        def group(self): return 'Quality control'
        def groupId(self): return 'quality_uncertainty'
        def shortHelpString(self): return 'Compare CRS, dimensions, emprise et résolution de deux rasters. Ne reprojette ni rééchantillonne.'
        def createInstance(self): return RasterAlignmentCheckAlgorithm()
        def initAlgorithm(self,config=None):
            self.addParameter(QgsProcessingParameterRasterLayer(self.A,'Raster A'))
            self.addParameter(QgsProcessingParameterRasterLayer(self.B,'Raster B'))
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT,'Rapport comparaison HTML','HTML'))
        def processAlgorithm(self,parameters,context,feedback):
            a=self.parameterAsRasterLayer(parameters,self.A,context); b=self.parameterAsRasterLayer(parameters,self.B,context)
            if a is None or b is None or not a.isValid() or not b.isValid(): raise QgsProcessingException('Raster A ou B invalide.')
            checks=[('CRS identique',a.crs()==b.crs()),('Dimensions identiques',a.width()==b.width() and a.height()==b.height()),
                   ('Emprise identique',a.extent()==b.extent()),('Résolution identique',abs(a.rasterUnitsPerPixelX()-b.rasterUnitsPerPixelX())<1e-12 and abs(a.rasterUnitsPerPixelY()-b.rasterUnitsPerPixelY())<1e-12)]
            rows=[('Raster A',a.name()),('Raster B',b.name())]+[(name,'OK' if ok else 'DIFFÉRENT') for name,ok in checks]
            rows.append(('Alignement complet','COMPATIBLE' if all(ok for _,ok in checks) else 'NON COMPATIBLE'))
            path=self.parameterAsFileOutput(parameters,self.OUTPUT,context)
            with open(path,'w',encoding='utf-8') as f: f.write(_html_report('Index Calculator - Raster Alignment Check',rows,'Ce contrôle compare la grille. Il ne vérifie pas la coïncidence réelle des pixels ni la qualité de registration.'))
            feedback.pushInfo('Alignement complet: '+('compatible' if all(ok for _,ok in checks) else 'non compatible'))
            return {self.OUTPUT:path}
except ImportError:
    RasterQualityAuditAlgorithm = None
    RasterAlignmentCheckAlgorithm = None
