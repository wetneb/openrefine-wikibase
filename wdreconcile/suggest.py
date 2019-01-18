import requests
from bottle import SimpleTemplate
from bottle import html_escape
import hashlib
import re
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

def autodescribe(qid, lang):
    """
    Calls the autodesc API by Magnus
    """
    if not autodescribe_endpoint:
        return ''
    try:
        r = requests.get(autodescribe_endpoint,
            {'q':qid,
            'format':'json',
            'mode':'short',
            'links':'wikidata',
            'get_infobox':'yes',
            'lang':lang},
            timeout=2)
        desc = r.json().get('result', '')
        desc = desc.replace('<a href', '<a target="_blank" href')
        return desc
    except (requests.exceptions.RequestException, ValueError) as e:
        print(e)
        print(e.request.url)
        return ''

class SuggestEngine(object):
    def __init__(self, redis_client):
        self.r = redis_client
        self.property_path_re = re.compile(r'(SPARQL ?:? ?)?(\(*(P\d+|[LAD][a-z\-]+)[/\|@].*)$')
        self.store = ItemStore(self.r)
        self.ft = PropertyFactory(self.store)
        self.store.ttl = 24*60*60 # one day
        self.image_path = self.ft.parse('|'.join(image_properties))
        with open('templates/preview.html') as f:
            self.preview_template = SimpleTemplate(f.read(), noescape=True)

    def get_image_statements(self, item_value):
        image_values = self.image_path.step(item_value)
        return [v.as_string() for v in image_values if not v.is_novalue()]

    def get_image_for_item(self, item_value, item, lang):
        """
        Returns a Wikimedia Commons file name
        for an image representing this item
        (or its type)
        :returns: a pair of (filename, alt text)
                 or None if we did not find anything
        """
        images = list(self.get_image_statements(item_value))
        if images:
            return (commons_image_url(images[0]),
                    lngfb(item.get('labels'), lang) or id)
        else:
            return (fallback_image_url, fallback_image_alt)

    def preview(self, args):
        id = args['id']
        item_value = ItemValue(id=id)
        item = self.store.get_item(id)
        lang = args.get('lang')
        image = self.get_image_for_item(item_value, item, lang)

        desc = self.get_description(item, lang)

        args = {
            'id':id,
            'label': html_escape(lngfb(item.get('labels'), lang) or id),
            'description': desc,
            'image': image,
            'url': qid_url_pattern.replace('{{id}}',id),
            'width': preview_width,
            'height': preview_height,
        }
        return self.preview_template.render(**args)

    def get_label(self, item, target_lang):
        """
        Gets a label from items returned from search
        results (not from full representations of JSON
        items, that's in ItemStore).
        """
        if 'label' in item:
            return item['label']
        return item['id']

    def get_description(self, item, lang):
        """
        Gets a description from an item and target language.
        """
        descriptions = item.get('descriptions')
        if lang in descriptions and ' ' in descriptions[lang]:
            return html_escape(descriptions[lang])
        else:
            return autodescribe(item['id'], lang)

    def find_something(self, args, typ='item', prefix=''):
        lang = args.get('lang', 'en')
        r = requests.get(mediawiki_api_endpoint,
                {'action':'wbsearchentities',
                 'format':'json',
                 'type':typ,
                 'search':args['prefix'],
                 'language':lang,
                 'uselang':lang,
                 })
        r.raise_for_status()
        resp = r.json()

        search_results = resp.get('search',[])

        result = [
            {
             'id': item['id'],
             'name': self.get_label(item, lang),
             'description': item.get('description'),
            }
            for item in search_results]
        return {'result':result}

    def find_type(self, args):
        return self.find_something(args)

    def find_property(self, args):
        # Check first if we are dealing with a path
        s = (args.get('prefix') or '').strip()

        sparql_match = []
        match = self.property_path_re.match(s)
        try:
            source_string = match.group(2) if match else s
            parsed = self.ft.parse(source_string)
            sparql_match = [{'id':source_string,'name':'SPARQL: '+source_string, 'description':'property path'}]
        except ValueError:
            pass

        # search for simple properties
        search_results =  self.find_something(args, 'property', "Property:")['result']
        return {'result':sparql_match + search_results}

    def flyout_type(self, args):
        return self.flyout(args)

    def flyout_entity(self, args):
        return self.flyout(args)

    def flyout_property(self, args):
        return self.flyout(args)

    def flyout(self, args):
        id = args.get('id')
        lang = args.get('lang', 'en')
        html = None
        if id:
            item = self.store.get_item(id)
            html = '<p style="font-size: 0.8em; color: black;">%s</p>' % self.get_description(item, lang)
        return {'id':id, 'html':html}

    def find_entity(self, args):
        return self.find_something(args)

    def propose_properties(self, args):
        """
        This method proposes properties to be fetched
        for a column reconcilied against a particular type (or none)
        """
        reconciled_type = (args.get('type') or default_type_entity)
        limit = int(args.get('limit') or 20)
        limit = min(limit, 50)

        # This SPARQL query uses GAS (don't worry, it's carbon-free)
        # https://wiki.blazegraph.com/wiki/index.php/RDF_GAS_API
        # We use GAS rather than a simple property path to
        # be able to order by depth, so that the most relevant properties
        # come first.

        property_for_this_type_property
        sparql_query = Template("""
        PREFIX wd: <$identifier_space>
        PREFIX wdt: <$schema_space>
        PREFIX gas: <http://www.bigdata.com/rdf/gas#>
        SELECT ?prop ?propLabel ?depth WHERE {
        SERVICE gas:service {
            gas:program gas:gasClass "com.bigdata.rdf.graph.analytics.BFS" .
            gas:program gas:in wd:$base_type .
            gas:program gas:out ?out .
            gas:program gas:out1 ?depth .
            gas:program gas:maxIterations 10 .
            gas:program gas:maxVisited 100 .
            gas:program gas:linkType wdt:P279 .
        }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "$lang" }
        ?out wdt:$property_for_this_type ?prop .
        }
        ORDER BY ?depth
        LIMIT $limit
        """)
        sparql_query = sparql_query.substitute(
            base_type=reconciled_type,
            property_for_this_type=property_for_this_type_property,
            lang=args['lang'],
            limit=limit,
            identifier_space=identifier_space,
            schema_space=schema_space,
        )
        results = sparql_wikidata(sparql_query)

        properties = []

        for result in results["bindings"]:
            pid = to_p(result["prop"]["value"])
            name = result.get('propLabel', {}).get('value') or pid
            properties.append({
                'name': name,
                'id': pid,
            })

        return {
            'type':reconciled_type,
            'properties':properties
        }

