
import bottle
import json
import requests
from fuzzywuzzy import fuzz
from itemstore import ItemStore
from typematcher import TypeMatcher

from bottle import route, run, request, default_app, template, HTTPError
from docopt import docopt

from config import *

headers = {
    'User-Agent':service_name,
}

item_store = ItemStore(redis_client)
type_matcher = TypeMatcher(redis_client)

def wikidata_string_search(query_string):
    r = requests.get(
        'https://www.wikidata.org/w/api.php',
        {'action':'query',
         'format':'json',
         'list':'search',
         'srnamespace':0,
         'srlimit':wd_api_search_results,
         'srsearch':query_string},
        headers=headers)
    print(r.url)
    resp = r.json()
    return [item['title'] for item in resp.get('query', {}).get('search')]

def reconcile(query, default_language='en'):
    print(query)

    search_string = query['query']
    properties = query.get('properties', [])
    target_types = query.get('type', [])
    if type(target_types) != list:
        target_types = [target_types]

    # search using the target label as search string
    ids = wikidata_string_search(search_string)

    # retrieve corresponding items
    items = item_store.get_items(ids)

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
            current_types = item['P31']
            found = any([
                any([
                    type_matcher.is_subclass(typ, target_type)
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
    item_store.get_items(list(types_to_prefetch))

    # Add the labels to the response
    for i in range(len(scored_items)):
        scored_items[i]['type'] = [
            {'id':id, 'name':item_store.get_label(id, default_language)}
                for id in scored_items[i]['type']]

    return sorted(scored_items, key=lambda i: -i.get('score', 0))

def perform_query(q):
    type_strict = q.get('type_strict', 'any')
    if type_strict not in ['any','all','should']:
        raise ValueError('Invalid type_strict')
    return reconcile(q)

@route('/api', method=['GET','POST'])
def api():
    callback = request.query.get('callback') or request.forms.get('callback')
    query = request.query.get('query') or request.forms.get('query')
    queries = request.query.get('queries') or request.forms.queries
    print(queries)
    if query:
        try:
            query = json.loads(query)
            result = [perform_query(query)]
            return {'result':result}
        except ValueError as e:
            return {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}
    elif queries:
        try:
            queries = json.loads(queries)
            result = { k:{'result':perform_query(q)} for k, q in queries.items() }
            return result
        except (ValueError, AttributeError, KeyError) as e:
            print(e)
            return {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}

    else:
        identify = {
            'name':service_name,
            'view':{'url':'https://www.wikidata.org/wiki/{{id}}'},
            }
        if callback:
            return '%s(%s);' % (callback, json.dumps(identify))
        return identify

@route('/')
def home():
    with open('templates/index.html', 'r') as f:
        return template(f.read())

if __name__ == '__main__':
    run(host='localhost', port=8000, debug=True)

app = application = default_app()
