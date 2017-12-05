"""
@author: Jonathan Navarrete
"""


import pandas as pd
import itertools as it
import numpy as np
from Probs2 import Probs ## code for calculating joint/marginal probabilities
#from Plot import PlotDiGraph, PlotNetwork ## plotting
from tqdm import tqdm
import networkx as nx


class KDEBayes():

    def __init__(self, dataframe, class_col_name, maximum=True, progress_bar=False):
        """
        Tree Augmented Naive Bayes Algorithm for building a Tree Augmented Naive Bayes Classifier
        """
        self.class_col_name = class_col_name
        self.priors = self.Priors(dataframe, class_col_name)
        colnames = dataframe.columns.tolist()
        colnames.remove(class_col_name)
        self.colnames = colnames
        self.MIresults = self.MutualInfo(dataframe, progress_bar = progress_bar) ## a dictionary {class: dataframe}
        self.Roots = self.SetRoots(dataframe) ## returns name of root
        self.MST = self.BuildMST()
        self.DAG = self.BuildDAG()

    def Priors(self, dataframe, class_col_name):
        n = dataframe.shape[0]
        array = dataframe[class_col_name].values
        vals, counts = np.unique(array, return_counts=True)
        prop = counts/n
        priors = dict(zip(vals, prop))
        return priors

    
    def MutualInfo(self, df, progress_bar):
        class_col_name = self.class_col_name
        g = df.groupby(by = class_col_name) ## group df by class
        if progress_bar:
            g = tqdm(g)
        colnames = self.colnames
        ## process the following steps for each class
        ClassMats = {} ## dictionary to store MutualInfMatrix for each class
        for i, frame in g:
            colcombos = it.combinations(colnames, 2) ## will return tuples
            MutualInfo = []
            for u, v in colcombos:
                ulist = frame[u] #.tolist() ## Probs2 takes a series
                vlist = frame[v] #.tolist()
                probs = Probs(ulist, vlist) ## calculates all probs
                MI = probs.CalcMutualInfo() 
                MutualInfo.append((u, v, MI)) ## no longer storing probs to save memory
            MutualInfMatrix = pd.DataFrame(MutualInfo, columns = ['U', 'V', "MI"])
            MutualInfMatrix.sort_values(by = "MI", ascending=False, inplace=True)
            MutualInfMatrix.reset_index(inplace=True, drop=True)
            ClassMats[i] = MutualInfMatrix ## store results for current class
        return ClassMats

      
    def SetRoots(self, dataframe):
        """
        FAN algorithm: 
        
        1. for each attribute:
            calculate the Mutual Information with the Class variable;
                    this is not the conditional-Mutual Info.
        2. Root = attribute with max(MI)
        
        Root is the same for all trees in this version of TAN
        """
        class_col_name = self.class_col_name
        colnames = self.colnames
        colcombos = it.product([class_col_name], colnames)
        MutualInfo = []
        ulist = dataframe[class_col_name]
        for u, v in colcombos:
            vlist = dataframe[v]
            probs = Probs(ulist, vlist)
            MI = probs.CalcMutualInfo()
            MutualInfo.append((u, v, MI))
        MutualInfo.sort(key = lambda x: x[2], reverse=False) ## descending
        [print(line) for line in MutualInfo] ## test
        ## top branch
        xclass, root, weight = MutualInfo[0]
        return root
        
            
            
    
    def BuildMST(self):
        """
        Uses Networkx to build Maximum Spanning Tree
        """
        ClassFrames = self.MIresults        
        MST = {}
        
        for i, frame in ClassFrames.items():
            print(f"\nClass: {i} || Unidirected Graph: ")
            print("--------------------------------")
            print(frame.head())
            print("...")

            G = nx.Graph()  ## number of unique attributes
            for ind, u, v, mi in frame.itertuples():
                mi = -1*mi ## -1*mi to build minimum spanning tree
                G.add_edge(u, v, weight = mi) 
            ## return Maximum Spanning Tree and switched flag (list)
            maxst = nx.minimum_spanning_tree(G)
            MST[i] = maxst
            ## return dictionary of maximum spanning trees
        return MST



    def BuildDAG(self):
        """
        From MST build a dag by choosing a column to be a root
        """
        MST = self.MST ## dictionary(class: list of tuples)
        #modelprobs = self.MIresults ## dictionary {class: dataframe}
        DAG = {}
        for key, mst in MST.items():
            root = self.Root            
            pred = nx.predecessor(mst, root)
            #print(pred)
            edges = []
            weights = []
            for u, v in pred.items():
                if len(v) > 0:
                    v = v[0]
                    edge_data = mst.get_edge_data(u,v)
                    w = edge_data['weight']
                    weights.append(w)
                else:
                    v = None
                ## U: Child
                ## V: Parent, thus Parent can be None for Roots
                edges.append((u,v,w))
            
            avgweight = sum(weights)/len(weights)
            
            ## new rule:
            ## If weight is less than avg, break conditional probs
            final_edges = []
            for u, v, w in edges:
                if w <= avgweight:
                    v = None
            final_edges.append((u,v))
            DAG[key] = final_edges
        return DAG


    def BuildModel(self, dataframe):
        class_col_name = self.class_col_name
        g = dataframe.groupby(by = class_col_name) ## group df by class
        DAG = self.DAG
        ClassMats = {} ## dictionary to store MutualInfMatrix for each class
        for klass, frame in g:
            edges = DAG[klass]
            MutualInfo = []
            for u, v in edges:
                ulist = frame[u] #.tolist()
                if v is not None:
                    vlist = frame[v] #.tolist()
                else:
                    ## head node will have None
                    vlist = None
                probs = Probs(ulist, vlist) ## calculates all probs
                MutualInfo.append((u, v, probs)) 
            MutualInfMatrix = pd.DataFrame(MutualInfo, columns = ['U', 'V', "Probs"])
            ClassMats[klass] = MutualInfMatrix
        return TreeBayes(self.priors, ClassMats, self.class_col_name)
            


class TreeBayes():
    def __init__(self, priors, TreeModels, class_col_name):
        self.class_col_name = class_col_name
        self.priors = priors
        self.TreeModels = TreeModels
        
    def __repr__(self):
        treemodels = self.TreeModels
        out = str(treemodels)        
        return out

    def Predict(self, newdf, log=False, progress_bar=False):
        TreeProbs = self.TreeModels
        newcols = newdf.columns.tolist()
        if self.class_col_name in newcols:
            newdf = newdf.drop(self.class_col_name, axis = 1)
        results = []
        rows = newdf.iterrows()
        if progress_bar:
            rows = tqdm(rows)
        for i, row in newdf.iterrows():
            sample = row.to_dict()
            class_probs = {}
            for class_name, treeframe in TreeProbs.items():
                prior = self.priors[class_name]
                LogPosterior = np.log(prior)
                for ind, u, v, probs in treeframe.itertuples():
                    if v is not None:
                        pval = probs.ConditionalProb(sample[u], sample[v])
                    else:
                        pval = probs.PredMarginalProb(sample[u])
                    logpval = np.log(pval)
                    LogPosterior += logpval
                if log:
                    class_probs[class_name] = LogPosterior
                else:
                    class_probs[class_name] = np.exp(LogPosterior)
            results.append(class_probs)
        dfresult = pd.DataFrame(results)
        dfresult[self.class_col_name] = dfresult.idxmax(axis=1)
        return dfresult
