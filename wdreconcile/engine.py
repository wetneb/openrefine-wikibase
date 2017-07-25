from config import *
import requests
import itertools
import re
import json
from collections import defaultdict

from .itemstore import ItemStore
from .typematcher import TypeMatcher
from .utils import to_q
from .language import language_fallback
from .propertypath import PropertyFactory
from .wikidatavalue import ItemValue

class ReconcileEngine(object):
    """
    Main class of the reconciliation system
    """
    def __init__(self, redis_client):
        self.item_store = ItemStore(redis_client)
        self.type_matcher = TypeMatcher(redis_client)
        self.pf = PropertyFactory(self.item_store)
        self.property_weight = 0.4
        self.validation_threshold_discount_per_property = 5
        self.match_score_gap = 10
        self.avoid_type = 'Q17442446' # Wikimedia internal stuff
        self.p31_property_path = self.pf.parse('P31')

    def wikidata_string_search(self, query_string, num_results, default_language):
        """
        Use the Wikidata API to search for matching items
        """
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
        search_results = [item['title'] for item in resp.get('query', {}).get('search', [])]
        r = requests.get(
            'https://www.wikidata.org/w/api.php',
            {'action':'wbsearchentities',
            'format':'json',
            'language': default_language,
            'limit':num_results,
            'search':query_string},
            headers=headers)
        resp = r.json()
        autocomplete_results = [item['id'] for item in resp.get('search', [])]

        return search_results + autocomplete_results

    def prepare_property(self, prop):
        """
        Converts a property to a SPARQL path
        """
        pid = prop['pid']
        path = self.pf.parse(pid)
        prop['path'] = path
        prop['v'] = str(prop.get('v')).strip()

        # This indicates whether the property is a unique
        # identifier for the resolved items. If so, we can use it
        # to fetch matches, without relying on string search.
        prop['unique_id'] = path.is_unique_identifier()
        return prop

    def process_queries(self, queries, default_language='en'):
        """
        This contains the backbone of the reconciliation algorithm.

        - If unique identifiers are supplied for the queries,
          try to use these to find matches by SPARQL
        - Otherwise, do a string search for candidates,
          filter them and rank them.
        """
        # Prepare all properties
        for query_id in queries:
            queries[query_id]['properties'] = list(map(self.prepare_property,
                queries[query_id].get('properties', [])))

        # Find primary ids in the queries
        unique_id_values = defaultdict(set)
        for query in queries.values():
            for prop in query['properties']:
                v = prop['v']
                if prop['unique_id'] and v:
                    unique_id_values[prop['path']].add(v)

        # Find Qids and labels by primary id
        unique_id_to_qid = {
            path : path.fetch_qids_by_values(values, default_language)
            for path, values in unique_id_values.items()
        }

        # Fetch all candidate qids for each query
        qids = {}
        qids_to_prefetch = set()
        for query_id, query in queries.items():
            # First, see if any qids can be fetched by primary id
            primary_qids_and_labels = []
            for prop in query['properties']:
                if prop['unique_id']:
                    primary_qids_and_labels += unique_id_to_qid.get(
                        prop['path'], {}).get(
                        prop['v'], [])

            if primary_qids_and_labels:
                # for now we're throwing away the labels
                # returned by the SPARQL query. Ideally we
                # could keep them to avoid fetching these items.
                qids[query_id] = [qid for qid, _ in primary_qids_and_labels]
                qids_to_prefetch |= set(qids[query_id])
                continue

            # Otherwise, use the text query
            if 'query' not in query:
                raise ValueError('No "query" provided')
            num_results = int(query.get('limit') or default_num_results)
            num_results_before_filter = min([2*num_results, wd_api_max_search_results])

            # If the text query is actually a QID, just return the QID itself
            query_as_qid = to_q(query['query'])
            if query_as_qid:
                qids[query_id] = [query_as_qid]
            else: # otherwise just search for the string with the WD API
                qids[query_id] = self.wikidata_string_search(query['query'],
                                    num_results_before_filter, default_language)

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
        properties_with_label = properties + [{
            'pid':'all_labels',
            'v':query['query'],
            'path':self.pf.make_empty(),
            'unique_id':False
        }]

        scored_items = []
        no_type_items = []

        types_to_prefetch = set()
        for qid, item in items.items():
            itemvalue = ItemValue(id=qid)

            # Check the type if we have a type constraint
            current_types = [val.id for val in self.p31_property_path.step(itemvalue)]
            type_found = len(current_types) > 0

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

            # If the type is invalid, skip the item.
            # If there is no type, we keep the item and will
            # reduce the score later on.
            if type_found and not good_type:
                continue

            # Compute per-property score
            scored = {}
            unique_id_found = False
            for prop in properties_with_label:
                prop_id = prop['pid']
                ref_val = str(prop['v'])
                path = prop['path']

                maxscore = 0
                bestval = None
                values = path.step(
                            ItemValue(id=qid))

                for val in values:
                    curscore = val.match_with_str(ref_val, self.item_store)
                    if curscore > maxscore or bestval is None:
                        bestval = val
                        maxscore = curscore

                if prop['unique_id'] and maxscore == 100:
                    # We found a match for a unique identifier!
                    unique_id_found = True

                weight = (1.0 if prop_id == 'all_labels'
                          else self.property_weight)
                scored[prop_id] = {
                    'score': maxscore,
                    'weighted': weight*maxscore,
                }

            # Compute overall score
            sum_scores = sum([
                prop['weighted'] for pid, prop in scored.items()
                ])
            properties_non_unique_ids = len([p for p in properties if not p['unique_id']])
            total_weight = self.property_weight*properties_non_unique_ids + 1.0

            if unique_id_found:
                avg = 100 # maximum score for matches by unique identifiers
            elif sum_scores:
                avg = sum_scores / total_weight
            else:
                avg = 0
            scored['score'] = avg

            scored['id'] = qid
            scored['name'] = self.item_store.get_label(qid, default_language)
            scored['type'] = current_types
            types_to_prefetch |= set(scored['type'])
            scored['match'] = False # will be changed later

            if not type_found and target_types and not unique_id_found:
                # Discount the score: we don't want any match
                # for these items, but they might be interesting
                # as potential matches for the user.
                scored['score'] /= 2
                no_type_items.append(scored)
            else:
                scored_items.append(scored)

        # Prefetch the labels for the types
        self.item_store.get_items(list(types_to_prefetch))

        # If no item had the right type, fall back on items with no type.
        # These items already have a much lower score, so there will be
        # no automatic match.
        if not scored_items:
            scored_items = no_type_items

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

    def fetch_values(self, args):
        """
        Same as fetch_property_by_batch, but for a single
        item (more convenient for testing).

        The `flat` parameter can be used to return just
        the value, without any JSON.
        """
        new_args = args.copy()
        qid = args.get('item', '')
        new_args['ids'] = qid
        results = self.fetch_property_by_batch(new_args)
        values = results['values'][0]
        if args.get('flat') == 'true':
            if values:
                return values[0]
            else:
                return ''
        else:
            return {'item':qid, 'prop':results['prop'], 'values':values}

    def fetch_property_by_batch(self, args):
        """
        Endpoint allowing clients to fetch the values associated
        to items and a property path.
        """
        lang = args.get('lang')
        if not lang:
            raise ValueError('No lang provided')
        prop = args.get('prop')
        if not prop:
            raise ValueError('No property provided')
        path = self.prepare_property({'pid':prop})['path']

        fetch_labels = ((args.get('label') or 'true') == 'true')

        items = args.get('ids','').split('|')
        items = [to_q(item) for item in items]
        if None in items:
            raise ValueError('Invalid Qid provided')

        values = [
            path.evaluate(
                ItemValue(id=qid),
                lang=lang,
                fetch_labels=fetch_labels,
            ) for qid in items ]

        return {'prop':prop, 'values':values}

    def fetch_properties_by_batch(self, args):
        """
        Endpoint allowing clients to fetch multiple properties
        (or property paths) on multiple items, simultaneously.

        This is complies with OpenRefine's data extension protocol.
        """
        lang = args.get('lang')
        if not lang:
            raise ValueError('No lang provided')

        query = args.get('extend', {})

        # Qids of the items to fetch
        ids = query.get('ids', [])
        ids = list(map(to_q, ids))
        if None in ids:
            raise ValueError('Invalid item id provided')

        # Property paths to fetch
        props = query.get('properties')
        if not props:
            raise ValueError("At least one property has to be provided")

        paths = {
            prop['id']: {
               'path': self.prepare_property({'pid':prop['id']})['path'],
               'settings': prop.get('settings', {}),
            }
            for prop in props
        }

        rows = {}
        for qid in ids:
            current_row = {}
            for pid, prop in paths.items():
                current_row[pid] = [
                    v.as_openrefine_cell(lang, self.item_store)
                    for v in prop['path'].step(
                        ItemValue(id=qid),
                        prop['settings'].get('references') or 'any',
                        prop['settings'].get('rank') or 'best')
                ]
                try:
                    limit = int(prop['settings'].get('limit') or 0)
                except ValueError:
                    limit = 0
                if limit > 0:
                    current_row[pid] = current_row[pid][:limit]
                if prop['settings'].get('count') == 'on':
                    current_row[pid] = [{'float':len(current_row[pid])}]
            rows[qid] = current_row


        # Prefetch property names
        self.item_store.get_items(paths.keys())

        meta = []
        for prop in props:
            pid = prop['id']
            path = paths[pid]['path']
            settings = paths[pid].get('settings') or {}
            dct = {
             'id':pid,
             'name':path.readable_name(lang),
            }
            if settings:
                dct['settings'] = settings
            expected_types = path.expected_types()
            if expected_types and not settings.get('count') == 'on':
                qid = expected_types[0]
                dct['type'] = {
                    'id':qid,
                    'name':self.item_store.get_label(qid, lang),
                }
            meta.append(dct)

        ret = {
            'rows': rows,
            'meta': meta,
        }
        return ret


