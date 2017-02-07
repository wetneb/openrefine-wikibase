from config import *
import requests
import itertools
from fuzzywuzzy import fuzz
from itemstore import ItemStore
from typematcher import TypeMatcher
from utils import to_q

class ReconcileEngine(object):
    """
    Main class of the reconciliation system
    """
    def __init__(self, redis_client):
        self.item_store = ItemStore(redis_client)
        self.type_matcher = TypeMatcher(redis_client)
        self.property_weight = 0.4
        self.validation_threshold_discount_per_property = 5
        self.match_score_gap = 10
        self.avoid_type = 'Q17442446' # Wikimedia internal stuff


    def wikidata_string_search(self, query_string, num_results):
        r = requests.get(
            'https://www.wikidata.org/w/api.php',
            {'action':'query',
            'format':'json',
            'list':'search',
            'srnamespace':0,
            'srlimit':num_results,
            'srsearch':query_string},
            headers=headers)
        resp = r.json()
        return [item['title'] for item in resp.get('query', {}).get('search', [])]

    def process_queries(self, queries, default_language='en'):
        # Fetch all candidate qids for each query
        qids = {}
        qids_to_prefetch = set()
        for query_id, query in queries.items():
            if 'query' not in query:
                raise ValueError('No "query" provided')
            num_results = int(query.get('limit') or default_num_results)
            num_results_before_filter = min([2*num_results, wd_api_max_search_results])
            qids[query_id] = self.wikidata_string_search(query['query'],
                                    num_results_before_filter)
            qids_to_prefetch |= set(qids[query_id])

        # Prefetch all items
        self.item_store.get_items(qids_to_prefetch)

        # Perform each query
        result = {}
        for query_id, query in queries.items():
            result[query_id] = {
                'result':self._rank_items(query,qids[query_id], default_language)
            }

        return result

    def prepare_property(self, prop):
        """
        Converts a property to RDF paths
        """
        pid = prop['pid']
        path = [pid]
        if '/' in pid:
            path = pid.split('/')
        prop['path'] = path
        return prop


    def resolve_property_path(self, path, item):
        """
        Returns the values matching the given path,
        starting on the item
        """
        return list(set(self._resolve_property_path(path, item)))

    def _resolve_property_path(self, path, item):
        # Check if it as item
        if type(item) != dict:
            item = str(item)
            qid = to_q(item)
            if qid:
                item = self.item_store.get_item(qid)

        if not path:
            if type(item) == dict: # this is an item
                # return all labels and aliases
                return itertools.chain(
                    item.get('labels', {}).values(),
                    item.get('aliases', []))
            else: # this is a value
                return [item]

        # otherwise we want to step into the item

        if type(item) != dict:
            return [] # we can't step into a value

        pid = path[0]
        remaining = path[1:]
        return itertools.chain(*[
            self.resolve_property_path(remaining, child)
            for child in item.get(pid, [])
        ])

    def _rank_items(self, query, ids, default_language):
        """
        Given a query and candidate qids returned from the search API,
        return the list of fleshed-out items from these QIDs, filtered
        and ranked.
        """
        search_string = query['query']
        properties = query.get('properties', [])
        target_types = query.get('type') or []
        type_strict = query.get('type_strict', 'any')
        if type_strict not in ['any','all','should']:
            raise ValueError('Invalid type_strict')
        if type(target_types) != list:
            target_types = [target_types]

        discounted_validation_threshold = (validation_threshold -
            self.validation_threshold_discount_per_property * len(properties))

        # retrieve corresponding items
        items = self.item_store.get_items(ids)

        # Add the label as "yet another property"
        properties_with_label = list(map(self.prepare_property, properties))
        properties_with_label.append({'pid':'all_labels','v':query['query'],
                                      'path':[]})

        scored_items = []
        types_to_prefetch = set()
        for qid, item in items.items():
            # Check the type if we have a type constraint
            current_types = item.get('P31', [])
            if target_types:
                good_type = any([
                    any([
                        self.type_matcher.is_subclass(typ, target_type)
                        for typ in current_types
                    ])
                    for target_type in target_types])
            else: # Check if we should ignore this item
                good_type = not any([
                   self.type_matcher.is_subclass(typ, self.avoid_type)
                   for typ in current_types
                ])

            # If the type is invalid, skip the item
            if not good_type:
                continue

            # Compute per-property score
            scored = {}
            matching_fun = fuzz.ratio
            for prop in properties_with_label:
                prop_id = prop['pid']
                ref_val = prop['v']

                maxscore = 0
                bestval = None
                values = list(self.resolve_property_path(prop['path'], item))
                for val in values:
                    curscore = matching_fun(val, ref_val)
                    if curscore > maxscore or bestval is None:
                        bestval = val
                        maxscore = curscore

                weight = (1.0 if prop_id == 'all_labels'
                          else self.property_weight)
                scored[prop_id] = {
                    'values': values,
                    'best_value': bestval,
                    'score': maxscore,
                    'weighted': weight*maxscore,
                }

            # Compute overall score
            sum_scores = sum([
                prop['weighted'] for pid, prop in scored.items()
                ])
            total_weight = self.property_weight*len(properties) + 1.0
            if sum_scores:
                avg = sum_scores / total_weight
            else:
                avg = 0
            scored['score'] = avg

            scored['id'] = qid
            scored['name'] = scored['all_labels'].get('best_value', '')
            scored['type'] = item.get('P31', [])
            types_to_prefetch |= set(scored['type'])
            scored['match'] = False # will be changed later

            scored_items.append(scored)

        # Prefetch the labels for the types
        self.item_store.get_items(list(types_to_prefetch))

        # Add the labels to the response
        for i in range(len(scored_items)):
            scored_items[i]['type'] = [
                {'id':id, 'name':self.item_store.get_label(id, default_language)}
                    for id in scored_items[i]['type']]

        ranked_items = sorted(scored_items, key=lambda i: -i.get('score', 0))

        if ranked_items:
            # Decide if we trust the first match
            next_score = ranked_items[1]['score'] if len(scored_items) > 1 else 0
            current_score = ranked_items[0]['score']
            ranked_items[0]['match'] = (
                current_score > discounted_validation_threshold and
                current_score > next_score + self.match_score_gap)

        max_results = int(query.get('limit') or default_num_results)
        return ranked_items[:max_results]

    def process_single_query(self, q, default_language='en'):
        results = self.process_queries({'q':q}, default_language)
        return results['q']


