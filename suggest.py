from itemstore import ItemStore
from language import language_fallback as lngfb
from config import preview_height, preview_width, thumbnail_width
from config import image_properties, this_host
from config import default_type_entity, property_for_this_type_property
from utils import to_p
from propertypath import PropertyFactory
from sparqlwikidata import sparql_wikidata

import requests
from bottle import SimpleTemplate
from bottle import html_escape
import hashlib
import re
from string import Template

def commons_image_url(filename):
    filename = filename.replace(' ', '_')
    m = hashlib.md5()
    m.update(filename.encode('utf-8'))
    hashed = m.hexdigest()
    base_fname = (
        'https://upload.wikimedia.org/wikipedia/commons/thumb/%s/%s/%s/%dpx-%s' %
        (hashed[0], hashed[0:2], filename, thumbnail_width, filename))
    if filename.lower().endswith('.svg'):
        base_fname += '.png'
    return base_fname

def autodescribe(qid, lang):
    """
    Calls the autodesc API by Magnus
    """
    try:
        r = requests.get('https://tools.wmflabs.org/autodesc/',
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
    except (requests.exceptions.RequestException, ValueError):
        return ''

class SuggestEngine(object):
    def __init__(self, redis_client):
        self.r = redis_client
        self.property_path_re = re.compile(r'(SPARQL ?:? ?)?(\(*P\d+[/\|].*)$')
        self.store = ItemStore(self.r)
        self.ft = PropertyFactory(self.store)
        self.store.ttl = 24*60*60 # one day
        with open('templates/preview.html') as f:
            self.preview_template = SimpleTemplate(f.read(), noescape=True)

    def get_image_statements(self, item):
        for pid in image_properties:
            for val in item.get(pid, []):
                yield val

    def get_image_for_item(self, item, lang):
        """
        Returns a Wikimedia Commons file name
        for an image representing this item
        (or its type)
        :returns: a pair of (filename, alt text)
                 or None if we did not find anything
        """
        images = list(self.get_image_statements(item))
        if images:
            return (commons_image_url(images[0]),
                    lngfb(item.get('labels'), lang) or id)
        else:
            return (this_host + '/static/wikidata.png', 'Wikidata')

    def preview(self, args):
        id = args['id']
        item = self.store.get_item(id)
        lang = args.get('lang')
        image = self.get_image_for_item(item, lang)

        desc = lngfb(item.get('descriptions'), lang)
        if desc:
            desc = html_escape(desc)

        # if the description is really too short
        if not desc or not ' ' in desc:
            desc = autodescribe(id, lang)

        args = {
            'id':id,
            'label': html_escape(lngfb(item.get('labels'), lang) or id),
            'description': desc,
            'image': image,
            'url': 'https://www.wikidata.org/entity/'+id,
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
        typ = item.get('match', {}).get('type')
        lang = item.get('match', {}).get('language')
        if typ == 'label' or typ == 'alias' and lang == target_lang:
            return item['match']['text']
        if 'label' in item:
            return item['label']
        aliases = item.get('aliases')
        if aliases:
            return aliases[0]

    def find_something(self, args, typ='item', prefix=''):
        lang = args.get('lang', 'en')
        r = requests.get('https://www.wikidata.org/w/api.php',
                {'action':'wbsearchentities',
                 'format':'json',
                 'type':typ,
                 'search':args['prefix'],
                 'language':lang,
                 })
        r.raise_for_status()
        resp = r.json()

        search_results = resp.get('search',[])

        result = [
            {
             'id': item['id'],
             'name': self.get_label(item, lang),
            }
            for item in search_results]
        return {'result':result}

    def find_type(self, args):
        return self.find_something(args)

    def find_property(self, args):
        # Check first if we are dealing with a path
        s = (args.get('prefix') or '').strip()
        match = self.property_path_re.match(s)
        if match:
            try:
                parsed = self.ft.parse(match.group(2))
                return {'result':[{'id':match.group(2),'name':'SPARQL: '+match.group(2)}]}
            except ValueError:
                pass
        return self.find_something(args, 'property', "Property:")

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
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
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

