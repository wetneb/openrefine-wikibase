

import json
import time
import aiohttp
import aioredis

from quart import Quart, render_template, request, g
from quart_cors import cors
from docopt import docopt
from wdreconcile.engine import ReconcileEngine
from wdreconcile.suggest import SuggestEngine
from wdreconcile.monitoring import Monitoring

from config import *

app = Quart(__name__, static_url_path='/static/', static_folder='static/')
app = cors(app, allow_origin='*')

@app.before_serving
async def setup():
    app.redis_client = await aioredis.create_redis_pool(redis_uri)
    app.http_connector = aiohttp.TCPConnector(limit_per_host=10)
    app.http_session_obj = aiohttp.ClientSession(connector=app.http_connector)
    app.http_session = await app.http_session_obj.__aenter__()

@app.before_request
async def request_context():
    g.reconcile = ReconcileEngine(app.redis_client, app.http_session)
    g.suggest = SuggestEngine(app.redis_client, app.http_session)
    g.monitoring = Monitoring(app.redis_client)

@app.after_serving
async def teardown():
    await app.http_session.__aexit__(None, None, None)
    app.redis_client.close()
    await app.redis_client.wait_closed()

def jsonp(view):
    async def wrapped(*posargs, **kwargs):
        args = {}
        # if we access the args via get(),
        # we can get encoding errors...
        post_data = await request.form
        for k in post_data:
            args[k] = post_data.get(k)
        for k in request.args:
            args[k] = request.args.get(k)
        callback = args.get('callback')
        status_code = 200
        try:
            result = await view(args, *posargs, **kwargs)
        except (Exception) as e:#ValueError, AttributeError, KeyError) as e:
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
            return result, status_code

    return wrapped

@app.route('/api', endpoint='api-default-lang', methods=['GET','POST'])
@jsonp
async def api_default_lang(args):
    if 'lang' not in args:
        args['lang'] = 'en'
    return await api(args)

@app.route('/<lang>/api', endpoint='api', methods=['GET','POST'])
@jsonp
async def api_custom_lang(args, lang):
    args['lang'] = lang
    return await api(args)

async def api(args):
    query = args.get('query')
    queries = args.get('queries')
    extend = args.get('extend')
    lang = fix_lang(args.get('lang'))
    start_time = time.time()

    if query:
        try:
       	    query = json.loads(query)
        except ValueError:
            query = {'query':query}
        result = await g.reconcile.process_single_query(query,
                default_language=lang)
        processing_time = time.time() - start_time
        await g.monitoring.log_request(1, processing_time)
        return result

    elif queries:
        queries = json.loads(queries)
        res = await g.reconcile.process_queries(queries,
                default_language=lang)
        processing_time = time.time() - start_time
        await g.monitoring.log_request(len(queries), processing_time)
        return res

    elif extend:
        args['extend'] = json.loads(extend)
        return await g.reconcile.fetch_properties_by_batch(args)

    else:
        identify = {
            'name':service_name + (' (%s)' % lang),
            'view':{'url':qid_url_pattern},
            'identifierSpace': identifier_space,
            'schemaSpace': schema_space,
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
                    'id': default_type_entity,
                    'name': await g.reconcile.item_store.get_label(default_type_entity, lang)
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


@app.route('/suggest/type', endpoint='suggest-type-default-lang', methods=['GET','POST'])
@jsonp
async def suggest_property(args):
    args['lang'] = fix_lang(args.get('lang'))
    return await g.suggest.find_type(args)

@app.route('/suggest/property', endpoint='suggest-property-default-lang', methods=['GET','POST'])
@jsonp
async def suggest_property(args):
    args['lang'] = fix_lang(args.get('lang'))
    return await g.suggest.find_property(args)

@app.route('/suggest/entity', endpoint='suggest-entity-default-lang', methods=['GET','POST'])
@jsonp
async def suggest_property(args):
    args['lang'] = fix_lang(args.get('lang'))
    return await g.suggest.find_entity(args)

@app.route('/preview', endpoint='preview-default-lang', methods=['GET','POST'])
@jsonp
async def preview(args):
    args['lang'] = fix_lang(args.get('lang'))
    return await g.suggest.preview(args)

@app.route('/<lang>/suggest/type', endpoint='suggest-type', methods=['GET','POST'])
@jsonp
async def suggest_type(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.find_type(args)

@app.route('/<lang>/suggest/property', endpoint='suggest-property', methods=['GET','POST'])
@jsonp
async def suggest_property(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.find_property(args)

@app.route('/<lang>/suggest/entity', endpoint='suggest-entity', methods=['GET','POST'])
@jsonp
async def suggest_entity(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.find_entity(args)

@app.route('/<lang>/flyout/type', endpoint='flyout-type', methods=['GET','POST'])
@jsonp
async def flyout_type(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.flyout_type(args)

@app.route('/<lang>/flyout/property', endpoint='flyout-property', methods=['GET','POST'])
@jsonp
async def flyout_property(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.flyout_property(args)

@app.route('/<lang>/flyout/entity', endpoint='flyout-entity', methods=['GET','POST'])
@jsonp
async def flyout_entity(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.flyout_entity(args)

@app.route('/<lang>/preview', endpoint='preview', methods=['GET','POST'])
@jsonp
async def preview(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.preview(args)

@app.route('/fetch_values', endpoint='fetch-values-default-lang', methods=['GET','POST'])
@jsonp
async def fetch_values(args):
    args['lang'] = fix_lang(args.get('lang'))
    return await g.reconcile.fetch_values(args)

@app.route('/<lang>/fetch_values', endpoint='fetch-values', methods=['GET','POST'])
@jsonp
async def fetch_values(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.reconcile.fetch_values(args)

@app.route('/<lang>/propose_properties', endpoint='propose-properties', methods=['GET','POST'])
@jsonp
async def propose_properties(args, lang):
    args['lang'] = fix_lang(lang)
    return await g.suggest.propose_properties(args)

@app.route('/<lang>/fetch_property_by_batch', endpoint='fetch-property-batch', methods=['GET','POST'])
@jsonp
async def fetch_property_by_batch(args, lang):
    args['lang'] = fix_lang(lang)
    return await reconcile.fetch_property_by_batch(args)

@app.route('/<lang>/fetch_properties_by_batch', endpoint='fetch-properties-batch', methods=['GET','POST'])
@jsonp
async def fetch_property_by_batch(args, lang):
    args['lang'] = fix_lang(lang)
    args['extend'] = json.loads(args.get('extend', '{}'))
    return await reconcile.fetch_properties_by_batch(args)

@app.route('/', endpoint='home')
async def home():
    context = {
        'service_status_url': this_host+'/monitoring',
        'endpoint_url': this_host+'/en/api',
    }
    return await render_template('index.html', **context)

@app.route('/monitoring')
async def monitor():
    return {'stats': await g.monitoring.get_rates()}

def fix_lang(lng):
    if not lng:
        return 'en'
    if lng == 'jp':
        return 'ja'
    return lng

if __name__ == '__main__':
    app.run(debug=True)

