
import bottle
import json

from bottle import route, run, request, default_app, template, HTTPError
from docopt import docopt
from engine import ReconcileEngine

from config import *

engine = ReconcileEngine(redis_client)

@route('/api', method=['GET','POST'])
def api():
    callback = request.query.get('callback') or request.forms.get('callback')
    query = request.query.get('query') or request.forms.get('query')
    queries = request.query.get('queries') or request.forms.queries
    print(queries)
    if query:
        try:
            query = json.loads(query)
            result = [engine.perform_query(query)]
            return {'result':result}
        except ValueError as e:
            return {'status':'error',
                    'message':'invalid query',
                    'details': str(e)}
    elif queries:
        try:
            queries = json.loads(queries)
            result = { k:{'result':engine.perform_query(q)} for k, q in queries.items() }
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
