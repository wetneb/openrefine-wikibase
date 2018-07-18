
import bottle
import json
import time

from bottle import route, run, request, default_app, template, HTTPError, abort, HTTPResponse
from docopt import docopt
from wdreconcile.engine import ReconcileEngine
from wdreconcile.suggest import SuggestEngine
from wdreconcile.monitoring import Monitoring

from config import *

reconcile = ReconcileEngine(redis_client)
suggest = SuggestEngine(redis_client)
monitoring = Monitoring(redis_client)

def jsonp(view):
    def wrapped(*posargs, **kwargs):
        args = {}
        # if we access the args via get(),
        # we can get encoding errors...
        for k in request.forms:
            args[k] = getattr(request.forms, k)
        for k in request.query:
            args[k] = getattr(request.query, k)
        callback = args.get('callback')
        status_code = 200
        try:
            result = view(args, *posargs, **kwargs)
        except (KeyError) as e:#ValueError, AttributeError, KeyError) as e:
            import traceback, sys
            traceback.print_exc(file=sys.stdout)
            result = {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}
            status_code = 403
        if callback:
            result = '%s(%s);' % (callback, json.dumps(result))

        if status_code == 200:
            return result
        else:
            result['arguments'] = args
            return HTTPResponse(result, status=status_code)

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
    extend = args.get('extend')
    lang = args.get('lang','en')
    start_time = time.time()

    if query:
        try:
       	    query = json.loads(query)
        except ValueError:
            query = {'query':query}
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

    elif extend:
        args['extend'] = json.loads(extend)
        return reconcile.fetch_properties_by_batch(args)

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
                    'flyout_service_path' : '/%s/flyout/type?id=${id}' % lang,
                },
                'property' : {
                    'service_url' : this_host,
                    'service_path' : '/%s/suggest/property' % lang,
                    'flyout_service_path' : '/%s/flyout/property?id=${id}' % lang,
                },
                'entity' : {
                    'service_url' : this_host,
                    'service_path' : '/%s/suggest/entity' % lang,
                    'flyout_service_path' : '/%s/flyout/entity?id=${id}' % lang,
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
            'extend' : {
                'propose_properties': {
                    'service_url' : this_host,
                    'service_path' : '/%s/propose_properties' % lang,
                },
                'property_settings': [
                    {
                        'name': 'limit',
                        'label': 'Limit',
                        'help_text': 'Maximum number of values to return per row (0 for no limit)',
                        'type': 'number',
                        'default': 0,
                    },
                    {
                        'name': 'rank',
                        'label': 'Ranks',
                        'help_text': 'Filter statements by rank',
                        'type': 'select',
                        'default': 'best',
                        'choices': [
                            {
                                'value': 'any',
                                'name': 'Any rank',
                            },
                            {
                                'value': 'best',
                                'name': 'Only the best rank',
                            },
                            {
                                'value': 'no_deprecated',
                                'name': 'Preferred and normal ranks',
                            }
                        ]
                    },
                    {
                        'name': 'references',
                        'label': 'References',
                        'help_text': 'Filter statements by their references',
                        'type': 'select',
                        'default' : 'any',
                        'choices': [
                            {
                                'value': 'any',
                                'name': 'Any statement',
                            },
                            {
                                'value': 'referenced',
                                'name': 'At least one reference',
                            },
                            {
                                'value': 'no_wiki',
                                'name': 'At least one non-wiki reference',
                            }
                        ]
                    },
                    {
                        'name': 'count',
                        'label': 'Return counts instead of values',
                        'help_text': 'The number of values will be returned.',
                        'type': 'checkbox',
                        'default': False,
                    }
                ]
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
def suggest_type(args, lang):
    args['lang'] = lang
    return suggest.find_type(args)

@route('/<lang>/suggest/property', method=['GET','POST'])
@jsonp
def suggest_property(args, lang):
    args['lang'] = lang
    return suggest.find_property(args)

@route('/<lang>/suggest/entity', method=['GET','POST'])
@jsonp
def suggest_entity(args, lang):
    args['lang'] = lang
    return suggest.find_entity(args)

@route('/<lang>/flyout/type', method=['GET','POST'])
@jsonp
def flyout_type(args, lang):
    args['lang'] = lang
    return suggest.flyout_type(args)

@route('/<lang>/flyout/property', method=['GET','POST'])
@jsonp
def flyout_property(args, lang):
    args['lang'] = lang
    return suggest.flyout_property(args)

@route('/<lang>/flyout/entity', method=['GET','POST'])
@jsonp
def flyout_entity(args, lang):
    args['lang'] = lang
    return suggest.flyout_entity(args)



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

@route('/<lang>/fetch_properties_by_batch', method=['GET','POST'])
@jsonp
def fetch_property_by_batch(args, lang):
    args['lang'] = lang
    args['extend'] = json.loads(args.get('extend', '{}'))
    return reconcile.fetch_properties_by_batch(args)

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
    run(host='0.0.0.0', port=8000, debug=True)

app = application = default_app()
