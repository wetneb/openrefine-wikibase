
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
    def wrapped():
        args = {}
        # if we access the args via get(),
        # we can get encoding errors…
        for k in request.forms:
            args[k] = getattr(request.forms, k)
        for k in request.query:
            args[k] = getattr(request.query, k)
        callback = args.get('callback')
        try:
            result =  view(args)
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
def api(args):
    query = args.get('query')
    queries = args.get('queries')

    if query:
        query = json.loads(query)
        return reconcile.process_single_query(query)

    elif queries:
        queries = json.loads(queries)
        res = reconcile.process_queries(queries)
        return res

    else:
        identify = {
            'name':service_name,
            'view':{'url':'https://www.wikidata.org/wiki/{{id}}'},
            'suggest' : {
                'type' : {
                    'service_url' : this_host,
                    'service_path' : '/suggest/type',
                },
                'property' : {
                    'service_url' : this_host,
                    'service_path' : '/suggest/property',
                },
                'entity' : {
                    'service_url' : this_host,
                    'service_path' : '/suggest/entity',
                }
            },
            'preview' : {
                'url': this_host+'/preview?id={{id}}',
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

@route('/')
def home():
    with open('templates/index.html', 'r') as f:
        return template(f.read())

if __name__ == '__main__':
    run(host='localhost', port=8000, debug=True)

app = application = default_app()
