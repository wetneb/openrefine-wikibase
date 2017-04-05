
import bottle
import json
import time

from bottle import route, run, request, default_app, template, HTTPError
from docopt import docopt
from engine import ReconcileEngine
from suggest import SuggestEngine
from monitoring import Monitoring

from config import *

reconcile = ReconcileEngine(redis_client)
suggest = SuggestEngine(redis_client)
monitoring = Monitoring(redis_client)

def jsonp(view):
    def wrapped(*posargs, **kwargs):
        args = {}
        # if we access the args via get(),
        # we can get encoding errors…
        for k in request.forms:
            args[k] = getattr(request.forms, k)
        for k in request.query:
            args[k] = getattr(request.query, k)
        callback = args.get('callback')
        try:
            result =  view(args, *posargs, **kwargs)
        except (KeyError) as e:#ValueError, AttributeError, KeyError) as e:
            result = {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}
        if callback:
            return '%s(%s);' % (callback, json.dumps(result))
        else:
            return result
    return wrapped

@route('/api', method=['GET','POST'])
@jsonp
def api_default_lang(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return api(args)

@route('/<lang>/api', method=['GET','POST'])
@jsonp
def api_custom_lang(args, lang):
    args['lang'] = lang
    return api(args)

def api(args):
    query = args.get('query')
    queries = args.get('queries')
    lang = args.get('lang','en')
    start_time = time.time()

    if query:
        query = json.loads(query)
        result = reconcile.process_single_query(query,
                default_language=lang)
        processing_time = time.time() - start_time
        monitoring.log_request(1, processing_time)
        return result

    elif queries:
        queries = json.loads(queries)
        res = reconcile.process_queries(queries,
                default_language=lang)
        processing_time = time.time() - start_time
        monitoring.log_request(len(queries), processing_time)
        return res

    else:
        identify = {
            'name':service_name + (' (%s)' % lang),
            'view':{'url':'https://www.wikidata.org/wiki/{{id}}'},
            'identifierSpace':'http://www.wikidata.org/entity/',
            'schemaSpace':'http://www.wikidata.org/prop/direct/',
            'suggest' : {
                'type' : {
                    'service_url' : this_host,
                    'service_path' : '/%s/suggest/type' % lang,
                },
                'property' : {
                    'service_url' : this_host,
                    'service_path' : '/%s/suggest/property' % lang,
                },
                'entity' : {
                    'service_url' : this_host,
                    'service_path' : '/%s/suggest/entity' % lang,
                }
            },
            'preview' : {
                'url': this_host+'/%s/preview?id={{id}}' % lang,
                'width' : preview_width,
                'height': preview_height,
            },
            'defaultTypes': [
                {
                    'id':'Q35120', # entity
                    'name': reconcile.item_store.get_label('Q35120', lang)
                }
            ],
            'augment' : {
                'propose_properties': {
                    'url': '/%s/propose_properties',
                },
                'add_column': {
                    'url': '/%s/fetch_property_by_batch',
                },
            },
        }
        return identify


@route('/suggest/type', method=['GET','POST'])
@jsonp
def suggest_property(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return suggest.find_type(args)

@route('/suggest/property', method=['GET','POST'])
@jsonp
def suggest_property(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return suggest.find_property(args)

@route('/suggest/entity', method=['GET','POST'])
@jsonp
def suggest_property(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return suggest.find_entity(args)

@route('/preview', method=['GET','POST'])
@jsonp
def preview(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return suggest.preview(args)

@route('/<lang>/suggest/type', method=['GET','POST'])
@jsonp
def suggest_property(args, lang):
    args['lang'] = lang
    return suggest.find_type(args)

@route('/<lang>/suggest/property', method=['GET','POST'])
@jsonp
def suggest_property(args, lang):
    args['lang'] = lang
    return suggest.find_property(args)

@route('/<lang>/suggest/entity', method=['GET','POST'])
@jsonp
def suggest_property(args, lang):
    args['lang'] = lang
    return suggest.find_entity(args)

@route('/<lang>/preview', method=['GET','POST'])
@jsonp
def preview(args, lang):
    args['lang'] = lang
    return suggest.preview(args)

@route('/fetch_values', method=['GET','POST'])
@jsonp
def fetch_values(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return reconcile.fetch_values(args)

@route('/<lang>/fetch_values', method=['GET','POST'])
@jsonp
def fetch_values(args, lang):
    args['lang'] = lang
    return reconcile.fetch_values(args)

@route('/<lang>/propose_properties', method=['GET','POST'])
@jsonp
def propose_properties(args, lang):
    args['lang'] = lang
    return suggest.propose_properties(args)

@route('/<lang>/fetch_property_by_batch', method=['GET','POST'])
@jsonp
def fetch_property_by_batch(args, lang):
    args['lang'] = lang
    return reconcile.fetch_property_by_batch(args)

@route('/')
def home():
    with open('templates/index.html', 'r') as f:
        context = {
            'service_status_url': this_host+'/monitoring',
        }
        return template(f.read(), **context)

@route('/static/<fname>')
def static(fname):
    return bottle.static_file(fname, root='static/')

@route('/monitoring')
def monitor():
    return {'stats':monitoring.get_rates()}

if __name__ == '__main__':
    run(host='localhost', port=8000, debug=True)

app = application = default_app()
