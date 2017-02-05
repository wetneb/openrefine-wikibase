from config import *
import requests
from fuzzywuzzy import fuzz
from itemstore import ItemStore
from typematcher import TypeMatcher

class ReconcileEngine(object):
    """
    Main class of the reconciliation system
    """
    def __init__(self, redis_client):
        self.item_store = ItemStore(redis_client)
        self.type_matcher = TypeMatcher(redis_client)

    def wikidata_string_search(self, query_string):
        r = requests.get(
            'https://www.wikidata.org/w/api.php',
            {'action':'query',
            'format':'json',
            'list':'search',
            'srnamespace':0,
            'srlimit':wd_api_search_results,
            'srsearch':query_string},
            headers=headers)
        resp = r.json()
        return [item['title'] for item in resp.get('query', {}).get('search')]

    def process_queries(self, queries, default_language='en'):
        # Fetch all candidate qids for each query
        qids = {}
        qids_to_prefetch = set()
        for query_id, query in queries.items():
            if 'query' not in query:
                raise ValueError('No "query" provided')
            qids[query_id] = self.wikidata_string_search(query['query'])
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

    def _rank_items(self, query, ids, default_language):
        """
        Given a query and candidate qids returned from the search API,
        return the list of fleshed-out items from these QIDs, filtered
        and ranked.
        """
        search_string = query['query']
        properties = query.get('properties', [])
        target_types = query.get('type', [])
        type_strict = query.get('type_strict', 'any')
        if type_strict not in ['any','all','should']:
            raise ValueError('Invalid type_strict')
        if type(target_types) != list:
            target_types = [target_types]

        # search using the target label as search string
        ids = self.wikidata_string_search(search_string)

        # retrieve corresponding items
        items = self.item_store.get_items(ids)

        # Add the label as "yet another property"
        properties_with_label = [{'pid':'all_labels','v':query['query']}]+properties

        scored_items = []
        types_to_prefetch = set()
        for qid, item in items.items():

            # Add labels
            labels = set()
            for lang, lang_label in item.get('labels', {}).items():
                labels.add(lang_label)

            # Add aliases
            labels |= set(item['aliases'])
            item['all_labels'] = list(labels)

            # Check the type if we have a type constraint
            if target_types:
                current_types = item.get('P31', [])
                found = any([
                    any([
                        self.type_matcher.is_subclass(typ, target_type)
                        for typ in current_types
                    ])
                    for target_type in target_types])

                if not found:
                    continue

            # Compute per-property score
            scored = {}
            matching_fun = fuzz.ratio
            for prop in properties_with_label:
                prop_id = prop['pid']
                ref_val = prop['v']

                maxscore = 0
                bestval = None
                values = item.get(prop_id, [])
                for val in values:
                    curscore = matching_fun(val, ref_val)
                    if curscore > maxscore or bestval is None:
                        bestval = val
                        maxscore = curscore

                scored[prop_id] = {
                    'values': values,
                    'best_value': bestval,
                    'score': maxscore,
                }

            # Compute overall score
            nonzero_scores = [
                prop['score'] for pid, prop in scored.items()
                if prop['score'] > 0 ]
            if nonzero_scores:
                avg = sum(nonzero_scores) / float(len(nonzero_scores))
            else:
                avg = 0
            scored['score'] = avg

            scored['id'] = qid
            scored['name'] = scored['all_labels'].get('best_value', '')
            scored['type'] = item.get('P31', [])
            types_to_prefetch |= set(scored['type'])
            scored['match'] = avg > validation_threshold

            scored_items.append(scored)

        # Prefetch the labels for the types
        self.item_store.get_items(list(types_to_prefetch))

        # Add the labels to the response
        for i in range(len(scored_items)):
            scored_items[i]['type'] = [
                {'id':id, 'name':self.item_store.get_label(id, default_language)}
                    for id in scored_items[i]['type']]

        return sorted(scored_items, key=lambda i: -i.get('score', 0))

    def process_single_query(self, q):
        results = self.process_queries({'q':q})
        return results['q']


