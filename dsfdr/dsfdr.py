import numpy as np
import scipy as sp
import types
from statsmodels.sandbox.stats.multicomp import multipletests
from scipy.special import comb

from . import transform
from . import statistics


# new fdr method
def dsfdr(data, labels, transform_type='rankdata', method='meandiff',
          alpha=0.1, numperm=1000, fdr_method='dsfdr'):
    '''
    calculate the Discrete FDR for the data

    input:
    data : N x S numpy array
        each column is a sample (S total), each row an OTU (N total)
    labels : a 1d numpy array (length S)
        the labels of each sample (same order as data) with the group
        (0/1 if binary, 0-G-1 if G groups, or numeric values for correlation)


    transform_type : str or None
        transformation to apply to the data before caluculating
        the test statistic
        'rankdata' : rank transfrom each OTU reads
        'log2data' : calculate log2 for each OTU using minimal cutoff of 2
        'normdata' : normalize the data to constant sum per samples
        'binarydata' : convert to binary absence/presence
        'clrdata' : clr transformation of data (after replacing 0 with 1)
         None : no transformation to perform

    method : str or function
        the method to use for calculating test statistics:
        'meandiff' : mean(A)-mean(B) (binary)
        'mannwhitney' : mann-whitney u-test (binary)
        'kruwallis' : kruskal-wallis test (multiple groups)
        'stdmeandiff' : (mean(A)-mean(B))/(std(A)+std(B)) (binary)
        'spearman' : spearman correlation (numeric)
        'pearson' : pearson correlation (numeric)
        'nonzerospearman' : spearman correlation only non-zero entries
                            (numeric)
        'nonzeropearson' : pearson correlation only non-zero entries (numeric)
        function : use this function to calculate the test statistic
        (input is data,labels, output is array of float)

    alpha : float
        the desired FDR control level
    numperm : int
        number of permutations to perform

    fdr_method : str
        the FDR procedure to determine significant bacteria
        'dsfdr' : discrete FDR method
        'bhfdr' : Benjamini-Hochberg FDR method
        'byfdr' : Benjamini-Yekutielli FDR method
        'filterBH' : Benjamini-Hochberg FDR method with filtering

    output:
    reject : np array of bool (length N)
        True for OTUs where the null hypothesis is rejected
    tstat : np array of float (length N)
        the test statistic value for each OTU (for effect size)
    pvals : np array of float (length N)
        the p-value for each OTU
    '''

    data = data.copy()

    if fdr_method == 'filterBH':
        index = []
        n0 = np.sum(labels == 0)
        n1 = np.sum(labels == 1)

        for i in range(np.shape(data)[0]):
            nonzeros = np.count_nonzero(data[i, :])
            if nonzeros < min(n0, n1):
                pval_min = (comb(n0, nonzeros, exact=True) +
                            comb(n1, nonzeros,
                                 exact=True)) / comb(n0 + n1, nonzeros)
                if pval_min <= alpha:
                    index.append(i)
            else:
                index.append(i)
        data = data[index, :]

    # transform the data
    if transform_type == 'rankdata':
        data = transform.rankdata(data)
    elif transform_type == 'log2data':
        data = transform.log2data(data)
    elif transform_type == 'binarydata':
        data = transform.binarydata(data)
    elif transform_type == 'normdata':
        data = transform.normdata(data)
    elif transform_type == 'clrdata':
        data = transform.clrdata(data)
    elif transform_type is None:
            pass
    else:
        raise ValueError('transform type %s not supported' % transform_type)

    numbact = np.shape(data)[0]

    labels = labels.copy()

    numbact = np.shape(data)[0]
    labels = labels.copy()

    if method == 'meandiff':
        # fast matrix multiplication based calculation
        method = statistics.meandiff
        tstat = method(data, labels)
        t = np.abs(tstat)
        numsamples = np.shape(data)[1]
        p = np.zeros([numsamples, numperm])
        k1 = 1 / np.sum(labels == 0)
        k2 = 1 / np.sum(labels == 1)
        for cperm in range(numperm):
            np.random.shuffle(labels)
            p[labels == 0, cperm] = k1
        p2 = np.ones(p.shape) * k2
        p2[p > 0] = 0
        mean1 = np.dot(data, p)
        mean2 = np.dot(data, p2)
        u = np.abs(mean1 - mean2)

    elif method == 'mannwhitney' or method == \
                   'kruwallis' or method == 'stdmeandiff':
        if method == 'mannwhitney':
            method = statistics.mannwhitney
        if method == 'kruwallis':
            method = statistics.kruwallis
        if method == 'stdmeandiff':
            method = statistics.stdmeandiff

        tstat = method(data, labels)
        t = np.abs(tstat)
        u = np.zeros([numbact, numperm])
        for cperm in range(numperm):
            rlabels = np.random.permutation(labels)
            rt = method(data, rlabels)
            u[:, cperm] = rt

    elif method == 'spearman' or method == 'pearson':
        # fast matrix multiplication based correlation
        if method == 'spearman':
            data = transform.rankdata(data)
            labels = sp.stats.rankdata(labels)
        meanval = np.mean(data, axis=1).reshape([data.shape[0], 1])
        data = data - np.repeat(meanval, data.shape[1], axis=1)
        labels = labels - np.mean(labels)
        tstat = np.dot(data, labels)
        t = np.abs(tstat)
        permlabels = np.zeros([len(labels), numperm])
        for cperm in range(numperm):
            rlabels = np.random.permutation(labels)
            permlabels[:, cperm] = rlabels
        u = np.abs(np.dot(data, permlabels))

    elif method == 'nonzerospearman' or method == 'nonzeropearson':
        t = np.zeros([numbact])
        tstat = np.zeros([numbact])
        u = np.zeros([numbact, numperm])
        for i in range(numbact):
            index = np.nonzero(data[i, :])
            label_nonzero = labels[index]
            sample_nonzero = data[i, :][index]
            if method == 'nonzerospearman':
                sample_nonzero = sp.stats.rankdata(sample_nonzero)
                label_nonzero = sp.stats.rankdata(label_nonzero)
            sample_nonzero = sample_nonzero - np.mean(sample_nonzero)
            label_nonzero = label_nonzero - np.mean(label_nonzero)
            tstat[i] = np.dot(sample_nonzero, label_nonzero)
            t[i] = np.abs(tstat[i])

            permlabels = np.zeros([len(label_nonzero), numperm])
            for cperm in range(numperm):
                rlabels = np.random.permutation(label_nonzero)
                permlabels[:, cperm] = rlabels
            u[i, :] = np.abs(np.dot(sample_nonzero, permlabels))

    elif isinstance(method, types.FunctionType):
        # call the user-defined function of statistical test
        t = method(data, labels)
        tstat = t.copy()
        u = np.zeros([numbact, numperm])
        for cperm in range(numperm):
            rlabels = np.random.permutation(labels)
            rt = method(data, rlabels)
            u[:, cperm] = rt
    else:
        print('unsupported method %s' % method)
        return None, None

    # fix floating point errors (important for permutation values!)
    # https://github.com/numpy/numpy/issues/8116
    for crow in range(numbact):
        closepos = np.isclose(t[crow], u[crow, :])
        u[crow, closepos] = t[crow]

    # calculate permutation p-vals
    pvals = np.zeros([numbact])  # p-value for original test statistic t
    pvals_u = np.zeros([numbact, numperm])
    # pseudo p-values for permutated test statistic u
    for crow in range(numbact):
        allstat = np.hstack([t[crow], u[crow, :]])
        stat_rank = sp.stats.rankdata(allstat, method='min')
        allstat = 1 - ((stat_rank - 1) / len(allstat))
        # assign ranks to t from biggest as 1
        pvals[crow] = allstat[0]
        pvals_u[crow, :] = allstat[1:]

    # calculate FDR
    if fdr_method == 'dsfdr':
        # sort unique p-values for original test statistics biggest to smallest
        pvals_unique = np.unique(pvals)
        sortp = pvals_unique[np.argsort(-pvals_unique)]

        # find a data-dependent threshold for the p-value
        foundit = False
        allfdr = []
        allt = []
        for cp in sortp:
            realnum = np.sum(pvals <= cp)
            fdr = (realnum + np.count_nonzero(
                pvals_u <= cp)) / (realnum * (numperm + 1))
            allfdr.append(fdr)
            allt.append(cp)
            if fdr <= alpha:
                realcp = cp
                foundit = True
                break

        if not foundit:
            # no good threshold was found
            reject = np.repeat([False], numbact)
            return reject, tstat, pvals

        # fill the reject null hypothesis
        reject = np.zeros(numbact, dtype=int)
        reject = (pvals <= realcp)

    elif fdr_method == 'bhfdr' or fdr_method == 'filterBH':
        t_star = np.array([t, ] * numperm).transpose()
        pvals = (np.sum(u >= t_star, axis=1) + 1) / (numperm + 1)
        reject = multipletests(pvals, alpha=alpha, method='fdr_bh')[0]

    elif fdr_method == 'byfdr':
        t_star = np.array([t, ] * numperm).transpose()
        pvals = (np.sum(u >= t_star, axis=1) + 1) / (numperm + 1)
        reject = multipletests(pvals, alpha=alpha, method='fdr_by')[0]

    else:
        raise ValueError('fdr method %s not supported' % fdr_method)

    return reject, tstat, pvals
