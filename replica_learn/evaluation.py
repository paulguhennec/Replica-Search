from typing import List, Tuple
from tqdm import tqdm
import numpy as np
import numba
import matplotlib.pyplot as plt


class TestQuery:
    def __init__(self, query_id: str, targets: List[str], query_box=None, to_ignore=None, weight=1.):
        self.query_id = query_id
        self.targets = frozenset(targets)
        if to_ignore is None:
            to_ignore = []
        if self.query_id not in self.targets:
            to_ignore.append(query_id)
        self.to_ignore = frozenset(to_ignore)
        self.query_box = query_box
        self.weight = weight

        assert len(self.targets) > 0, "No targets in query"
        assert self.targets.isdisjoint(self.to_ignore),\
            "Common elements in targets and to_ignore : {}".format(self.targets.intersection(self.to_ignore))

    def __repr__(self):
        return "{} -> {}, (Ignore {})".format(self.query_id, self.targets, self.to_ignore)

    @numba.jit()
    def compute_ap(self, list_result):
        pos_set = self.targets
        amb_set = self.to_ignore

        old_recall, old_precision = 0., 1.
        intersect_size = 0
        j = 0
        ap = 0.
        for r in list_result:
            if r in amb_set:
                continue
            if r in pos_set:
                intersect_size += 1
            j += 1
            recall = intersect_size / len(pos_set)
            precision = intersect_size / j

            ap += (recall - old_recall) * ((old_precision + precision) / 2.0)

            old_recall, old_precision = recall, precision
        return ap

    @numba.jit()
    def compute_precision_recall(self, list_result):
        pos_set = self.targets
        amb_set = self.to_ignore

        old_recall, old_precision = 0., 1.
        intersect_size = 0
        j = 0
        ap = 0.
        for r in list_result:
            if r in amb_set:
                continue
            if r in pos_set:
                intersect_size += 1
            j += 1
            recall = intersect_size / len(pos_set)
            precision = intersect_size / j

            ap += (recall - old_recall) * ((old_precision + precision) / 2.0)

            old_recall, old_precision = recall, precision
        return old_precision, old_recall


class Benchmark:
    """
    List of queries (defined by the id of the search) and targets (defined by their ids as well) to be found
    """
    def __init__(self):
        self.queries = []  # type: List[TestQuery]

    def __repr__(self):
        return "Benchmark ({} queries) \n{}".format(len(self.queries), self.queries)

    def add_query(self, test_query: TestQuery):
        self.queries.append(test_query)

    def generate_evaluation_results(self, search_function, max_n=400, verbose=True) -> 'BenchmarkResults':
        results_ids, results_scores = [], []
        for test_query in tqdm(self.queries, disable=(not verbose)):
            # tmp_results = search_function(test_query.query_id, max_n)
            # results.append([])
            # for target_id in test_query.targets:
            #     position = None
            #     for i, r in enumerate(tmp_results):
            #         if r['id'] == target_id:
            #             position = i
            #             break
            #     results[-1].append(position)
            result_ids, result_scores = zip(*search_function(test_query.query_id, max_n))
            results_ids.append(result_ids)
            results_scores.append(result_scores)
        return BenchmarkResults(self.queries, results_ids, results_scores)


class BenchmarkResults:
    def __init__(self, queries: List[TestQuery], results_ids: List[List[str]], results_scores: List[List[float]]):
        self.queries = queries
        self.results_ids = results_ids
        self.results_scores = results_scores
        self.max_n = len(results_ids[0])
        assert len(self.queries) == len(self.results_ids) == len(self.results_scores)

    def mean_ap(self):
        return np.mean([q.compute_ap(rr) for q, rr in zip(self.queries, self.results_ids)])

    def mean_precision_recall(self, thresholds: List[float], return_individual_scores=False):
        # Compute quantities
        average_precision_recall_list = []
        individual_scores = [[] for q in self.queries]
        for t in thresholds:
            precision_list, recall_list = [], []
            for i, (q, results_id, results_score) in enumerate(zip(self.queries, self.results_ids, self.results_scores)):
                precision, recall = q.compute_precision_recall(results_id[results_score > t])
                precision_list.append(precision)
                recall_list.append(recall)
                individual_scores[i].append((precision, recall))
            average_precision_recall_list.append((np.mean(precision_list), np.mean(recall_list)))
        if return_individual_scores:
            return individual_scores
        else:
            return average_precision_recall_list

    def recall_at_n(self, max_n=100) -> np.ndarray:
        """
        Compute the average recall for the benchmark
        :param max_n:
        :return:
        """
        assert max_n <= self.max_n
        recalls = np.array([q.compute_precision_recall(r[:max_n])[1] for q, r in zip(self.queries, self.results_ids)])
        weights = np.array([q.weight for q in self.queries])
        #weights = (nb_links+1)/nb_links
        return np.sum(recalls*weights, axis=0)/np.sum(weights)

    def plot_query(self, dataset, query_number: int, ncols=5):
        test_query = self.queries[query_number]
        result = self.results_ids[query_number]
        plt.figure(figsize=(20, 20))
        plt.subplot(1, ncols, 1)
        dataset.plot_img(test_query.query_id)
        plt.axis('off')
        for i, uid in enumerate(result):
            if i == ncols:
                break
            #plt.figure(figsize=(5, 5))
            plt.subplot(1, ncols, i+1)
            dataset.plot_img(uid)
            plt.axis('off')
            if uid in test_query.targets:
                title = 'OK'
            elif uid in test_query.to_ignore:
                title = 'IGNORE'
            else:
                title = 'WRONG'
            title += " {:.3f}".format(self.results_scores[query_number][i])
            plt.title(title)