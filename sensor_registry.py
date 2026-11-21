# -*- coding: utf-8 -*-
"""Index Calculator Pro Sensor Intelligence Registry."""
from html import escape

SENSORS = {
    'SENTINEL2': {
        'label': 'Sentinel-2 MSI (Level-2A reflectance)',
        'bands': {'BLUE':'B2','GREEN':'B3','RED':'B4','RE1':'B5','RE2':'B6','NIR':'B8','SWIR1':'B11','SWIR2':'B12'},
        'resolutions': {'B2':'10 m','B3':'10 m','B4':'10 m','B5':'20 m','B6':'20 m','B8':'10 m','B11':'20 m','B12':'20 m'},
        'notes': 'Red-edge and SWIR bands are native 20 m. Many workflows resample them, which changes pixel support and must be documented.'
    },
    'LANDSAT89': {
        'label': 'Landsat 8/9 OLI (surface reflectance)',
        'bands': {'BLUE':'B2','GREEN':'B3','RED':'B4','NIR':'B5','SWIR1':'B6','SWIR2':'B7'},
        'resolutions': {'B2':'30 m','B3':'30 m','B4':'30 m','B5':'30 m','B6':'30 m','B7':'30 m'},
        'notes': 'Landsat OLI has no Sentinel-style red-edge bands. Red-edge indices are not directly compatible.'
    }
}

def compatibility(sensor_key, required_roles):
    sensor = SENSORS[sensor_key]
    bands = sensor['bands']
    missing = [r for r in required_roles if r not in bands]
    return {'sensor': sensor['label'], 'required': list(required_roles), 'mapping': {r:bands[r] for r in required_roles if r in bands}, 'missing': missing, 'compatible': not missing, 'notes': sensor['notes']}

def html_report(results):
    rows=[]
    for method, roles, sensor_key, result in results:
        state='Compatible' if result['compatible'] else 'Incompatible / missing bands'
        mapping=', '.join(f'{escape(k)} -> {escape(v)}' for k,v in result['mapping'].items()) or 'None'
        missing=', '.join(result['missing']) or 'None'
        rows.append(f'<tr><td>{escape(method)}</td><td>{escape(SENSORS[sensor_key]["label"])}</td><td>{escape(state)}</td><td>{mapping}</td><td>{escape(missing)}</td></tr>')
    return '''<!doctype html><html><head><meta charset="utf-8"><title>Index Calculator Pro Sensor Compatibility</title><style>body{font-family:Arial,sans-serif;margin:28px;color:#203040}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:8px;text-align:left}th{background:#e8f0f4}h1{color:#176b45}</style></head><body><h1>Index Calculator Pro - Sensor Compatibility Report</h1><p>Compatibility is based on spectral band roles only. It does not validate reflectance scaling, atmospheric correction, spatial resolution harmonization, cloud masking, or scientific suitability.</p><table><thead><tr><th>Method</th><th>Sensor</th><th>Status</th><th>Band mapping</th><th>Missing roles</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></body></html>'''

try:
    from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterEnum,
                          QgsProcessingParameterFileDestination, QgsProcessingException)
    class SensorCompatibilityReportAlgorithm(QgsProcessingAlgorithm):
        def name(self): return 'ic_sensor_compatibility'
        def displayName(self): return 'Sensor Compatibility Report'
        def group(self): return 'Scientific Core'
        def groupId(self): return 'scientific_core'
        def shortHelpString(self):
            return 'Creates an HTML compatibility report for selected methods and Sentinel-2 MSI or Landsat 8/9 OLI. Band-role compatibility only; no scaling or resampling is performed.'
        def createInstance(self): return SensorCompatibilityReportAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterEnum('SENSOR','Sensor', options=['Sentinel-2 MSI','Landsat 8/9 OLI'], defaultValue=0))
            self.addParameter(QgsProcessingParameterEnum('METHODS','Methods to check', options=['NDVI','NDMI','NDRE','MTCI','RECI','RENDVI','NMDI','MNDWI','NDTI','MSAVI2','ATSAVI','TSAVI','GEMI','TNDVI','CVI','NPCI','NGRDI','BNDVI','DVI','RVI','IPVI','GRVI','RI','CI','BI','SBI','SSI','ISU'], allowMultiple=True, defaultValue=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26]))
            self.addParameter(QgsProcessingParameterFileDestination('OUTPUT','Compatibility report (HTML)','HTML files (*.html)'))
        def processAlgorithm(self, parameters, context, feedback):
            sensor_key='SENTINEL2' if self.parameterAsEnum(parameters,'SENSOR',context)==0 else 'LANDSAT89'
            method_options=['NDVI','NDMI','NDRE','MTCI','RECI','RENDVI','NMDI','MNDWI','NDTI','MSAVI2','ATSAVI','TSAVI','GEMI','TNDVI','CVI','NPCI','NGRDI','BNDVI','DVI','RVI','IPVI','GRVI','RI','CI','BI','SBI','SSI','ISU']
            required={
                'NDVI':['NIR','RED'],'NDMI':['NIR','SWIR1'],'NDRE':['NIR','RE1'],'MTCI':['RE2','RE1','RED'],'RECI':['NIR','RE1'],'RENDVI':['NIR','RE1'],'NMDI':['NIR','SWIR1','SWIR2'],'MNDWI':['GREEN','SWIR1'],'NDTI':['SWIR1','SWIR2'],'MSAVI2':['NIR','RED'],'ATSAVI':['NIR','RED'],'TSAVI':['NIR','RED'],'GEMI':['NIR','RED'],'TNDVI':['NIR','RED'],'CVI':['GREEN','RED','NIR'],'NPCI':['RED','BLUE'],'NGRDI':['GREEN','RED'],'BNDVI':['NIR','BLUE'],'DVI':['NIR','RED'],'RVI':['NIR','RED'],'IPVI':['NIR','RED'],'GRVI':['GREEN','RED'],'RI':['RED','GREEN'],'CI':['RED','GREEN'],'BI':['RED','GREEN'],'SBI':['RED','GREEN','NIR'],'SSI':['RED','GREEN','BLUE'],'ISU':['RED','NIR']}
            selected=self.parameterAsEnums(parameters,'METHODS',context)
            results=[]
            for i in selected:
                method=method_options[i]
                r=compatibility(sensor_key,required[method])
                results.append((method,required[method],sensor_key,r))
            output=self.parameterAsFileOutput(parameters,'OUTPUT',context)
            try:
                with open(output,'w',encoding='utf-8') as f: f.write(html_report(results))
            except OSError as e: raise QgsProcessingException('Unable to write report: '+str(e))
            return {'OUTPUT':output}
except ImportError:
    SensorCompatibilityReportAlgorithm = None
