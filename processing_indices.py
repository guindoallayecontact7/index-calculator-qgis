# -*- coding: utf-8 -*-
"""Index Calculator Pro spectral indices exposed through the QGIS Processing Toolbox.
Prototype algorithms: input rasters must be single-band, reflectance-scaled,
co-registered, and have matching grid/extent/CRS. No silent resampling occurs.
"""
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
                      QgsProcessingParameterRasterDestination, QgsProcessingException,
                      QgsProcessingProvider)
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry


# code, display title, group, roles, formula, scientific note
INDEX_SPECS = [
 ('DVI','Difference Vegetation Index','Vegetation',['NIR','RED'],'NIR - RED','Difference-based vegetation response; scale-sensitive.'),
 ('RVI','Ratio Vegetation Index','Vegetation',['NIR','RED'],'NIR / (RED + 1e-6)','Ratio index; values may exceed 1.'),
 ('BNDVI','Blue Normalized Difference Vegetation Index','Vegetation',['NIR','BLUE'],'(NIR - BLUE) / (NIR + BLUE + 1e-6)','Blue/NIR normalized contrast.'),
 ('NGRDI','Normalized Green-Red Difference Index','Vegetation',['GREEN','RED'],'( GREEN - RED ) / ( GREEN + RED + 1e-6)','Visible-band green/red contrast.'),
 ('GRVI','Green-Red Vegetation Index','Vegetation',['GREEN','RED'],'GREEN / (RED + 1e-6)','Green-to-red ratio variant; distinct from NGRDI.'),
 ('IPVI','Infrared Percentage Vegetation Index','Vegetation',['NIR','RED'],'NIR / (NIR + RED + 1e-6)','Percentage-like infrared ratio.'),
 ('ATSAVI','Adjusted Transformed SAVI','Vegetation',['NIR','RED'],'1.22 * (NIR - 1.22 * RED - 0.03) / (NIR + RED + 0.22)','ATSAVI formula variant; constants assume reflectance inputs.'),
 ('TNDVI','Transformed NDVI','Vegetation',['NIR','RED'],'sqrt((NIR - RED) / (NIR + RED + 1e-6) + 0.5)','Use only when the expression is non-negative; invalid pixels may occur.'),
 ('GEMI','Global Environment Monitoring Index','Vegetation',['NIR','RED'],'((2 * NIR * NIR - RED * RED + 1.5 * NIR + 0.5 * RED) / (NIR + RED + 0.5)) * (1 - 0.25 * ((2 * NIR * NIR - RED * RED + 1.5 * NIR + 0.5 * RED) / (NIR + RED + 0.5))) - (RED - 0.125) / (1 - RED)','GEMI; reflectance-domain and denominator checks recommended.'),
 ('MSAVI2','Modified Soil Adjusted Vegetation Index 2','Vegetation',['NIR','RED'],'(2 * NIR + 1 - sqrt((2 * NIR + 1) * (2 * NIR + 1) - 8 * (NIR - RED))) / 2','MSAVI2; requires non-negative square-root argument.'),
 ('TSAVI','Transformed Soil Adjusted Vegetation Index','Vegetation',['NIR','RED'],'(0.5 * (NIR - 0.08 - RED)) / (NIR + RED - 0.08 + 1e-6)','Fixed soil-line parameters are a generalized variant; local soil line is preferred.'),
 ('MTCI','MERIS Terrestrial Chlorophyll Index','Chlorophyll',['RE2','RE1','RED'],'(RE2 - RE1) / (RE1 - RED + 1e-6)','Requires red-edge bands; Sentinel-2 mapping: B6/B5/B4.'),
 ('RECI','Red Edge Chlorophyll Index','Chlorophyll',['NIR','RE1'],'NIR / (RE1 + 1e-6) - 1','Red-edge proxy; sensor/band mapping matters.'),
 ('RENDVI','Red Edge NDVI','Chlorophyll',['NIR','RE1'],'(NIR - RE1) / (NIR + RE1 + 1e-6)','Normalized red-edge vegetation contrast.'),
 ('NPCI','Normalized Pigment Chlorophyll Index','Chlorophyll',['RED','BLUE'],'(RED - BLUE) / (RED + BLUE + 1e-6)','Pigment proxy; not a direct chlorophyll measurement.'),
 ('CVI','Chlorophyll Vegetation Index','Chlorophyll',['GREEN','RED','NIR'],'( NIR * RED ) / ( GREEN * GREEN + 1e-6)','Chlorophyll-related proxy; reflectance scaling required.'),
 ('NMDI','Normalized Multi-band Drought Index','Water / Dryness',['NIR','SWIR1','SWIR2'],'(NIR - (SWIR1 - SWIR2)) / (NIR + SWIR1 - SWIR2 + 1e-6)','NMDI; SWIR band definitions and reflectance scaling required.'),
 ('NDWI2','NDWI (McFeeters)','Water',['GREEN','NIR'],'( GREEN - NIR ) / ( GREEN + NIR + 1e-6)','Open-water contrast; not Gao vegetation-water NDWI.'),
 ('MNDWI','Modified NDWI','Water',['GREEN','SWIR1'],'( GREEN - SWIR1 ) / ( GREEN + SWIR1 + 1e-6)','Water detection; sensor mapping and scene context matter.'),
 ('NDTI','Normalized Difference Tillage Index','Soil',['SWIR1','SWIR2'],'( SWIR1 - SWIR2 ) / ( SWIR1 + SWIR2 + 1e-6)','Surface/tillage proxy; soil and moisture influence.'),
 ('RI','Redness Index','Soil',['RED','GREEN'],'RED / (GREEN + 1e-6)','Redness ratio.'),
 ('CI','Color Index','Soil',['RED','GREEN'],'(RED - GREEN) / (RED + GREEN + 1e-6)','Visible color contrast.'),
 ('BI','Brightness Index','Soil',['RED','GREEN'],'sqrt((RED * RED + GREEN * GREEN) / 2)','Brightness variant using red and green.'),
 ('SBI','Soil Brightness Index','Soil',['RED','GREEN','NIR'],'sqrt((RED * RED + GREEN * GREEN + NIR * NIR) / 3)','Brightness variant; not a calibrated soil property.'),
 ('SSI','Soil Salinity Index (visible variant)','Soil',['RED','GREEN','BLUE'],'(RED + GREEN) / (BLUE + 1e-6)','Exploratory visible-band ratio; not direct salinity measurement.'),
 ('ISU','Built Surface Index','Built-up',['RED','NIR'],'(RED - NIR) / (RED + NIR + 1e-6)','Simple built-surface contrast; not a unique built-up index.'),
]
ROLE_LABELS={'RED':'Red','GREEN':'Green','BLUE':'Blue','NIR':'Near Infrared','RE1':'Red Edge 1','RE2':'Red Edge 2','SWIR1':'Shortwave Infrared 1','SWIR2':'Shortwave Infrared 2'}
class SpectralIndexAlgorithm(QgsProcessingAlgorithm):
 def __init__(self,spec): super().__init__(); self.spec=spec
 def name(self): return 'ic_'+self.spec[0].lower()
 def displayName(self): return self.spec[0]+' - '+self.spec[1]
 def group(self): return self.spec[2]
 def groupId(self): return self.spec[2].lower().replace(' ','_').replace('/','_')
 def shortHelpString(self):
  return ('Formula: '+self.spec[4]+'. '+self.spec[5]+' Inputs must be single-band reflectance rasters, aligned in CRS, extent and pixel dimensions. '
          'This prototype does not perform automatic resampling, band scaling, atmospheric correction or cloud masking.')
 def createInstance(self): return SpectralIndexAlgorithm(self.spec)
 def initAlgorithm(self,config=None):
  for role in self.spec[3]: self.addParameter(QgsProcessingParameterRasterLayer(role,ROLE_LABELS.get(role,role)+' raster (single-band)'))
  self.addParameter(QgsProcessingParameterRasterDestination('OUTPUT','Output index raster'))
 def processAlgorithm(self,parameters,context,feedback):
  layers={role:self.parameterAsRasterLayer(parameters,role,context) for role in self.spec[3]}
  if any(l is None or not l.isValid() for l in layers.values()): raise QgsProcessingException('One or more input rasters are invalid.')
  first=next(iter(layers.values()))
  for role,layer in layers.items():
   if layer.crs()!=first.crs() or layer.width()!=first.width() or layer.height()!=first.height() or layer.extent()!=first.extent():
    raise QgsProcessingException('Input rasters are not aligned (CRS, dimensions and extent must match). Align/resample first.')
  entries=[]; formula=self.spec[4]
  for role,layer in layers.items():
   entry=QgsRasterCalculatorEntry(); entry.raster=layer; entry.bandNumber=1; entry.ref=role+'@1'; entries.append(entry)
   formula=formula.replace(role, '"'+role+'@1"')
  output=self.parameterAsOutputLayer(parameters,'OUTPUT',context)
  from .raster_calc import calculate
  erreur=calculate(formula,output,first.extent(),first.crs(),first.width(),first.height(),entries,context.transformContext(),feedback)
  if erreur: raise QgsProcessingException('Calculation failed: '+erreur)
  return {'OUTPUT':output}
class IndexCalculatorProvider(QgsProcessingProvider):
 def loadAlgorithms(self):
  for spec in INDEX_SPECS: self.addAlgorithm(SpectralIndexAlgorithm(spec))
  from .field_intelligence import FieldZonalStatsAlgorithm
  from .temporal_intelligence import RasterChangeAlgorithm, TemporalFieldComparisonAlgorithm
  from .stress_ranking import StressDetectionAlgorithm, FieldRankingAlgorithm
  from .agro_health_score import FieldHealthScoreAlgorithm
  self.addAlgorithm(FieldZonalStatsAlgorithm())
  self.addAlgorithm(RasterChangeAlgorithm())
  self.addAlgorithm(TemporalFieldComparisonAlgorithm())
  self.addAlgorithm(StressDetectionAlgorithm())
  self.addAlgorithm(FieldRankingAlgorithm())
  self.addAlgorithm(FieldHealthScoreAlgorithm())
  from .time_series import CropTimeSeriesAlgorithm
  self.addAlgorithm(CropTimeSeriesAlgorithm())
  from .scientific_registry import ScientificRegistryReportAlgorithm
  if ScientificRegistryReportAlgorithm is not None: self.addAlgorithm(ScientificRegistryReportAlgorithm())
  from .scientific_testbench import NumericalTestBenchAlgorithm
  if NumericalTestBenchAlgorithm is not None: self.addAlgorithm(NumericalTestBenchAlgorithm())
  from .quality_engine import RasterQualityAuditAlgorithm, RasterAlignmentCheckAlgorithm
  if RasterQualityAuditAlgorithm is not None: self.addAlgorithm(RasterQualityAuditAlgorithm())
  if RasterAlignmentCheckAlgorithm is not None: self.addAlgorithm(RasterAlignmentCheckAlgorithm())
  from .sensor_registry import SensorCompatibilityReportAlgorithm
  if SensorCompatibilityReportAlgorithm is not None: self.addAlgorithm(SensorCompatibilityReportAlgorithm())
  from .band_mapping import AutomaticBandMappingAlgorithm, RasterHarmonizationReadinessAlgorithm
  self.addAlgorithm(AutomaticBandMappingAlgorithm())
  self.addAlgorithm(RasterHarmonizationReadinessAlgorithm())
  from .raster_harmonizer import RasterHarmonizeToReferenceAlgorithm
  self.addAlgorithm(RasterHarmonizeToReferenceAlgorithm())
  from .preprocessing_pipeline import AgriculturalPreprocessingPipelineAlgorithm
  self.addAlgorithm(AgriculturalPreprocessingPipelineAlgorithm())
  from .cloud_shadow_intelligence import Sentinel2SCLCloudShadowMaskAlgorithm, LandsatQAPixelCloudShadowMaskAlgorithm, CloudMaskSummaryAlgorithm
  self.addAlgorithm(Sentinel2SCLCloudShadowMaskAlgorithm())
  self.addAlgorithm(LandsatQAPixelCloudShadowMaskAlgorithm())
  self.addAlgorithm(CloudMaskSummaryAlgorithm())
  from .agricultural_intelligence import AgriculturalIntelligencePipelineAlgorithm
  self.addAlgorithm(AgriculturalIntelligencePipelineAlgorithm())
  from .security_audit import PluginSecurityAuditAlgorithm
  if PluginSecurityAuditAlgorithm is not None: self.addAlgorithm(PluginSecurityAuditAlgorithm())
  from .crop_parcel_intelligence import CropParcelIntelligenceAlgorithm
  self.addAlgorithm(CropParcelIntelligenceAlgorithm())
  from .automatic_field_delineation import AutomaticFieldDelineationAlgorithm
  self.addAlgorithm(AutomaticFieldDelineationAlgorithm())
  from .edge_temporal_intelligence import EdgeTemporalIntelligenceAlgorithm
  self.addAlgorithm(EdgeTemporalIntelligenceAlgorithm())
  from .boundary_extraction import BoundaryExtractionAlgorithm
  self.addAlgorithm(BoundaryExtractionAlgorithm())
  from .parcel_shape_intelligence import ParcelShapeIntelligenceAlgorithm
  self.addAlgorithm(ParcelShapeIntelligenceAlgorithm())
  from .parcel_fusion_intelligence import ParcelFusionIntelligenceAlgorithm
  self.addAlgorithm(ParcelFusionIntelligenceAlgorithm())
  from .parcel_topology_intelligence import ParcelTopologyAuditAlgorithm
  self.addAlgorithm(ParcelTopologyAuditAlgorithm())
  from .parcel_candidate_refinement import ParcelCandidateRefinementAlgorithm
  self.addAlgorithm(ParcelCandidateRefinementAlgorithm())
  from .crop_pattern_intelligence import CropPatternClusteringAlgorithm
  self.addAlgorithm(CropPatternClusteringAlgorithm())
 def id(self): return 'index_calculator'
 def name(self): return 'Index Calculator Pro'
 def shortName(self): return 'Index Calculator Pro'
 def icon(self):
  from qgis.PyQt.QtGui import QIcon
  import os
  return QIcon(os.path.join(os.path.dirname(__file__),'icon.png'))
 def createInstance(self): return IndexCalculatorProvider()
