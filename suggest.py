from itemstore import ItemStore
from language import language_fallback as lngfb
from config import preview_height, preview_width, thumbnail_width
from config import image_properties, this_host
import requests
from bottle import template
import hashlib
import re

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

class SuggestEngine(object):
    def __init__(self, redis_client):
        self.r = redis_client
        self.property_path_re = re.compile(r'(SPARQL ?:? ?)?(P\d+(/P\d+){1,2})$')
        self.store = ItemStore(self.r)
        self.store.ttl = 24*60*60 # one day
        with open('templates/preview.html') as f:
            self.preview_template = f.read()

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

        args = {
            'id':id,
            'label': lngfb(item.get('labels'), lang) or id,
            'description': lngfb(item.get('descriptions'), lang) or '',
            'image': image,
            'url': 'https://www.wikidata.org/entity/'+id,
            'width': preview_width,
            'height': preview_height,
        }
        return template(self.preview_template,
            **args)

    def get_label(self, item, target_lang):
        typ = item.get('match', {}).get('type')
        lang = item.get('match', {}).get('language')
        if typ == 'label' and lang == target_lang:
            return item['match']['text']
        return item['label']

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
            return {'result':[{'id':match.group(2),'name':'SPARQL: '+match.group(2)}]}
        return self.find_something(args, 'property', "Property:")

    def find_entity(self, args):
        return self.find_something(args)

