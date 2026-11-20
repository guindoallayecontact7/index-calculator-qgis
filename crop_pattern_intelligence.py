# -*- coding: utf-8 -*-
"""Index Calculator V4.6 - transparent exploratory crop-pattern clustering."""
import math


def normalize_vectors(rows):
    """Z-score normalize complete numeric vectors; return normalized rows, means, stds."""
    if not rows or not rows[0]:
        raise ValueError('At least one feature and one metric are required.')
    dims=len(rows[0])
    if any(len(r)!=dims for r in rows): raise ValueError('Feature vectors must have equal dimensions.')
    means=[]; stds=[]
    for j in range(dims):
        vals=[float(r[j]) for r in rows]
        if any(not math.isfinite(v) for v in vals): raise ValueError('Non-finite metric values are not supported.')
        m=sum(vals)/len(vals); var=sum((v-m)**2 for v in vals)/len(vals); sd=math.sqrt(var)
        means.append(m); stds.append(sd if sd>1e-12 else 1.0)
    return [[(float(v)-means[j])/stds[j] for j,v in enumerate(r)] for r in rows],means,stds


def kmeans(vectors,k=4,max_iterations=100):
    """Deterministic farthest-first initialized k-means. Returns labels, centroids, distances."""
    if not vectors: return [],[],[]
    n=len(vectors); dims=len(vectors[0])
    if k<1: raise ValueError('k must be >= 1')
    if any(len(v)!=dims for v in vectors): raise ValueError('Vector dimensions mismatch.')
    # Farthest-first initialization, deterministic and data-driven.
    centroids=[list(vectors[0])]
    while len(centroids)<min(k,n):
        distances=[min(sum((v[d]-c[d])**2 for d in range(dims)) for c in centroids) for v in vectors]
        idx=max(range(n),key=lambda i:(distances[i],-i))
        if vectors[idx] in centroids: break
        centroids.append(list(vectors[idx]))
    labels=[0]*n
    for _ in range(max_iterations):
        newlabels=[]
        for v in vectors:
            ds=[sum((v[d]-c[d])**2 for d in range(dims)) for c in centroids]
            newlabels.append(min(range(len(ds)),key=lambda j:(ds[j],j)))
        newcent=[]
        for j in range(len(centroids)):
            members=[vectors[i] for i,l in enumerate(newlabels) if l==j]
            newcent.append([sum(v[d] for v in members)/len(members) for d in range(dims)] if members else centroids[j])
        if newlabels==labels and all(sum((a-b)**2 for a,b in zip(c,nc))<1e-12 for c,nc in zip(centroids,newcent)):
            labels=newlabels; centroids=newcent; break
        labels,centroids=newlabels,newcent
    distances=[math.sqrt(sum((v[d]-centroids[l][d])**2 for d in range(dims))) for v,l in zip(vectors,labels)]
    return labels,centroids,distances


class CropPatternClusteringAlgorithm:
    def __new__(cls):
        from qgis.core import QgsProcessingAlgorithm
        class _Alg(QgsProcessingAlgorithm):
            INPUT='INPUT'; FIELD1='FIELD1'; FIELD2='FIELD2'; FIELD3='FIELD3'; FIELD4='FIELD4'; K='K'; OUTPUT='OUTPUT'
            def name(self): return 'ic_crop_pattern_clustering'
            def displayName(self): return 'Crop Pattern Clustering'
            def group(self): return 'Parcel analysis'
            def groupId(self): return 'crop_parcel_intelligence'
            def shortHelpString(self):
                return ('Exploratory unsupervised grouping of polygons using selected numeric spectral or temporal metrics. '
                       'Metrics are standardized (z-score) and clustered with deterministic k-means. Cluster IDs do not identify crop species; '
                       'distance/similarity are relative to the computed centroid and are not probabilities.')
            def createInstance(self): return CropPatternClusteringAlgorithm()
            def initAlgorithm(self,config=None):
                from qgis.core import QgsProcessingParameterFeatureSource,QgsProcessingParameterString,QgsProcessingParameterNumber,QgsProcessingParameterFeatureSink
                self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,'Parcel / field polygons'))
                for key,label,default in [(self.FIELD1,'Metric field 1 (required)','NDVI_mean'),(self.FIELD2,'Metric field 2 (required)','NDVI_std'),(self.FIELD3,'Metric field 3 (optional)','NDMI_mean'),(self.FIELD4,'Metric field 4 (optional)','')]:
                    self.addParameter(QgsProcessingParameterString(key,label,defaultValue=default))
                self.addParameter(QgsProcessingParameterNumber(self.K,'Number of clusters (K)',QgsProcessingParameterNumber.Integer,defaultValue=4,minValue=2,maxValue=10))
                self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,'Clustered polygons'))
            def processAlgorithm(self,parameters,context,feedback):
                from qgis.core import QgsProcessingException,QgsFields,QgsField,QgsFeature,QgsFeatureSink
                from qgis.PyQt.QtCore import QVariant
                source=self.parameterAsSource(parameters,self.INPUT,context)
                if source is None: raise QgsProcessingException('Invalid polygon source.')
                selected=[self.parameterAsString(parameters,key,context).strip() for key in (self.FIELD1,self.FIELD2,self.FIELD3,self.FIELD4)]
                fields_selected=[f for f in selected if f]
                if len(fields_selected)<2: raise QgsProcessingException('Select at least two numeric metrics.')
                if len(set(fields_selected))!=len(fields_selected): raise QgsProcessingException('Metric fields must be unique.')
                idxs=[source.fields().indexOf(f) for f in fields_selected]
                if any(i<0 for i in idxs): raise QgsProcessingException('One or more selected metric fields are missing.')
                records=[]; featurelist=[]; skipped=0
                for f in source.getFeatures():
                    vals=[]
                    for fld in fields_selected:
                        try: v=float(f[fld])
                        except (TypeError,ValueError): v=float('nan')
                        vals.append(v)
                    if not all(math.isfinite(v) for v in vals): skipped+=1; continue
                    records.append(vals); featurelist.append(f)
                if len(records)<2: raise QgsProcessingException('At least two polygons with complete numeric metrics are required.')
                k=self.parameterAsInt(parameters,self.K,context)
                if k>len(records): raise QgsProcessingException('K cannot exceed the number of valid polygons.')
                try:
                    norm,means,stds=normalize_vectors(records); labels,centroids,distances=kmeans(norm,k)
                except ValueError as e: raise QgsProcessingException(str(e))
                outfields=QgsFields(source.fields())
                additions=[('pattern_cluster',QVariant.Int),('pattern_distance',QVariant.Double),('pattern_similarity',QVariant.Double),('pattern_metrics',QVariant.String)]
                outidx={}
                for name,typ in additions:
                    i=outfields.indexOf(name)
                    if i<0: outfields.append(QgsField(name,typ)); i=outfields.indexOf(name)
                    outidx[name]=i
                sink,dest=self.parameterAsSink(parameters,self.OUTPUT,context,outfields,source.wkbType(),source.sourceCrs())
                if sink is None: raise QgsProcessingException('Could not create output sink.')
                for n,(f,l,d,vals) in enumerate(zip(featurelist,labels,distances,records)):
                    if feedback.isCanceled(): break
                    nf=QgsFeature(outfields); nf.setGeometry(f.geometry()); attrs=list(f.attributes())
                    while len(attrs)<outfields.count(): attrs.append(None)
                    # Similarity is an exponential distance transform for ranking/visualization, not a probability.
                    similarity=math.exp(-d)
                    attrs[outidx['pattern_cluster']]=int(l+1)
                    attrs[outidx['pattern_distance']]=float(d)
                    attrs[outidx['pattern_similarity']]=float(similarity)
                    attrs[outidx['pattern_metrics']]=';'.join(f'{name}={val:g}' for name,val in zip(fields_selected,vals))
                    nf.setAttributes(attrs); sink.addFeature(nf,QgsFeatureSink.FastInsert)
                    if len(featurelist): feedback.setProgress(int((n+1)*100/len(featurelist)))
                feedback.pushInfo(f'Clustering complete: {len(featurelist)} polygons; {skipped} skipped for missing/non-numeric metrics; {len(centroids)} clusters.')
                feedback.pushInfo('Metrics: '+', '.join(f'{name} mean={m:.6g}, sd={s:.6g}' for name,m,s in zip(fields_selected,means,stds)))
                return {self.OUTPUT:dest}
        return _Alg()
