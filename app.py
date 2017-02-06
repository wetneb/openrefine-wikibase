
import bottle
import json

from bottle import route, run, request, default_app, template, HTTPError
from docopt import docopt
from engine import ReconcileEngine
from suggest import SuggestEngine

from config import *

reconcile = ReconcileEngine(redis_client)
suggest = SuggestEngine(redis_client)

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
        except (ValueError, AttributeError, KeyError) as e:
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

    if query:
        query = json.loads(query)
        return reconcile.process_single_query(query,
                default_language=lang)

    elif queries:
        queries = json.loads(queries)
        res = reconcile.process_queries(queries,
                default_language=lang)
        return res

    else:
        identify = {
            'name':service_name + (' (%s)' % lang),
            'view':{'url':'https://www.wikidata.org/wiki/{{id}}'},
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
        }
        return identify


@route('/suggest/type', method=['GET','POST'])
@jsonp
def suggest_property(args):
    return suggest.find_type(args)

@route('/suggest/property', method=['GET','POST'])
@jsonp
def suggest_property(args):
    return suggest.find_property(args)

@route('/suggest/entity', method=['GET','POST'])
@jsonp
def suggest_property(args):
    return suggest.find_entity(args)

@route('/preview', method=['GET','POST'])
@jsonp
def preview(args):
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



@route('/')
def home():
    with open('templates/index.html', 'r') as f:
        return template(f.read())

@route('/static/<fname>')
def static(fname):
    return bottle.static_file(fname, root='static/')


if __name__ == '__main__':
    run(host='localhost', port=8000, debug=True)

app = application = default_app()
