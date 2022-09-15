from quart import render_template
from markupsafe import escape
import hashlib
import re
from aiohttp import ClientError
from string import Template

from .itemstore import ItemStore
from .language import language_fallback as lngfb
from .utils import to_p
from .propertypath import PropertyFactory
from .sparqlwikidata import sparql_wikidata
from .wikidatavalue import ItemValue

from config import preview_height, preview_width, thumbnail_width
from config import image_properties, this_host
from config import default_type_entity, property_for_this_type_property
from config import image_download_pattern, qid_url_pattern
from config import mediawiki_api_endpoint, autodescribe_endpoint
from config import fallback_image_url, fallback_image_alt
from config import identifier_space, schema_space
from config import sparql_query_to_propose_properties

def commons_image_url(filename):
    filename = filename.replace(' ', '_')
    m = hashlib.md5()
    m.update(filename.encode('utf-8'))
    hashed = m.hexdigest()
    base_fname = (
        image_download_pattern %
        (hashed[0], hashed[0:2], filename, thumbnail_width, filename))
    if filename.lower().endswith('.svg'):
        base_fname += '.png'
    return base_fname

async def autodescribe(http_session, qid, lang):
    """
    Calls the autodesc API by Magnus
    """
    if not autodescribe_endpoint:
        return ''
    try:
        async with http_session.get(autodescribe_endpoint,
                    params={'q':qid,
                    'format':'json',
                    'mode':'short',
                    'links':'wikidata',
                    'get_infobox':'yes',
                    'lang':lang},
                    timeout=2) as r:
            desc = (await r.json()).get('result', '')
            desc = desc.replace('<a href', '<a target="_blank" href')
            return desc
    except ClientError as e:
        return ''
    except ValueError as e:
        return ''

class SuggestEngine(object):
    def __init__(self, redis_client, http_session):
        self.r = redis_client
        self.http_session = http_session
        self.property_path_re = re.compile(r'(SPARQL ?:? ?)?(\(*(P\d+|[LADS][a-z\-]+)[/\|@].*)$')
        self.pid_re = re.compile('^P[1-9][0-9]*$')
        self.store = ItemStore(self.r, http_session)
        self.ft = PropertyFactory(self.store)
        self.store.ttl = 24*60*60 # one day
        if image_properties:
            self.image_path = self.ft.parse('|'.join(image_properties))
        else:
            self.image_path = None

    async def get_image_statements(self, item_value):
        if not self.image_path:
            return []
        image_values = await self.image_path.step(item_value)
        return [v.as_string() for v in image_values if not v.is_novalue()]

    async def get_image_for_item(self, item_value, item, lang):
        """
        Returns a Wikimedia Commons file name
        for an image representing this item
        (or its type)
        :returns: a pair of (filename, alt text)
                 or None if we did not find anything
        """
        images = list(await self.get_image_statements(item_value))
        if images:
            return (commons_image_url(images[0]),
                    lngfb(item.get('labels'), lang) or id)
        else:
            return (fallback_image_url, fallback_image_alt)

    async def preview(self, args):
        id = args['id']
        item_value = ItemValue(id=id)
        item = await self.store.get_item(id)
        lang = args.get('lang')
        image = await self.get_image_for_item(item_value, item, lang)

        desc = await self.get_description(item, lang)

        args = {
            'id':id,
            'label': lngfb(item.get('labels'), lang) or id,
            'description': desc,
            'image': image,
            'url': qid_url_pattern.replace('{{id}}',id),
            'width': preview_width,
            'height': preview_height,
        }
        return await render_template('preview.html', **args)

    def get_label(self, item, target_lang):
        """
        Gets a label from items returned from search
        results (not from full representations of JSON
        items, that's in ItemStore).
        """
        if 'label' in item:
            return item['label']
        return item['id']

    async def get_description(self, item, lang):
        """
        Gets a description from an item and target language.
        """
        descriptions = item.get('descriptions')
        if lang in descriptions and ' ' in descriptions[lang]:
            return escape(descriptions[lang])
        else:
            return await autodescribe(self.http_session, item['id'], lang) or descriptions.get(lang) or ''

    async def find_something(self, args, typ='item', prefix=''):
        lang = args.get('lang', 'en')
        async with self.http_session.get(mediawiki_api_endpoint,
                params={'action':'wbsearchentities',
                 'format':'json',
                 'type':typ,
                 'search':args['prefix'],
                 'language':lang,
                 'uselang':lang,
                 },
                raise_for_status=True) as r:
            resp = await r.json()

            search_results = resp.get('search',[])

            result = [
                {
                'id': item['id'],
                'name': self.get_label(item, lang),
                'description': item.get('description'),
                }
                for item in search_results]
            return {'result':result}

    async def find_type(self, args):
        return await self.find_something(args)

    async def find_property(self, args):
        # Check first if we are dealing with a path
        s = (args.get('prefix') or '').strip()

        sparql_match = []
        match = self.property_path_re.match(s)
        try:
            source_string = match.group(2) if match else s
            parsed = self.ft.parse(source_string)
            if not self.pid_re.match(s):
                sparql_match = [{'id':source_string,'name':'SPARQL: '+source_string, 'description':'property path'}]
        except ValueError:
            pass

        # search for simple properties
        search_results = (await self.find_something(args, 'property', "Property:"))['result']
        return {'result':sparql_match + search_results}

    async def flyout_type(self, args):
        return await self.flyout(args)

    async def flyout_entity(self, args):
        return await self.flyout(args)

    async def flyout_property(self, args):
        return await self.flyout(args)

    async def flyout(self, args):
        id = args.get('id')
        lang = args.get('lang', 'en')
        html = None
        if id:
            item = await self.store.get_item(id)
            html = '<p style="font-size: 0.8em; color: black;">%s</p>' % (await self.get_description(item, lang))
        return {'id':id, 'html':html}

    async def find_entity(self, args):
        return await self.find_something(args)

    async def propose_properties(self, args):
        """
        This method proposes properties to be fetched
        for a column reconcilied against a particular type (or none)
        """
        reconciled_type = (args.get('type') or default_type_entity)
        properties = []

        if reconciled_type and property_for_this_type_property and sparql_query_to_propose_properties:
            limit = int(args.get('limit') or 20)
            limit = min(limit, 50)

            # This SPARQL query uses GAS (don't worry, it's carbon-free)
            # https://wiki.blazegraph.com/wiki/index.php/RDF_GAS_API
            # We use GAS rather than a simple property path to
            # be able to order by depth, so that the most relevant properties
            # come first.

            sparql_query = Template(sparql_query_to_propose_properties)
            sparql_query = sparql_query.substitute(
                base_type=reconciled_type,
                property_for_this_type=property_for_this_type_property,
                lang=args['lang'],
                limit=limit,
                identifier_space=identifier_space,
                schema_space=schema_space,
            )
            results = await sparql_wikidata(self.http_session, sparql_query)

            for result in results["bindings"]:
                pid = to_p(result["prop"]["value"])
                if not pid: # https://github.com/wetneb/openrefine-wikibase/issues/145
                    continue
                name = result.get('propLabel', {}).get('value') or pid
                properties.append({
                    'name': name,
                    'id': pid,
                })

        if not properties:
            properties.append({
                'name': 'Qid',
                'id': 'qid'
            })

        return {
            'type':reconciled_type,
            'properties':properties
        }

