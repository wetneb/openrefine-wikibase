from itemstore import ItemStore
from config import preview_height, preview_width, thumbnail_width
from config import image_properties
import requests
from bottle import template
import hashlib

def commons_image_url(filename):
    filename = filename.replace(' ', '_')
    m = hashlib.md5()
    m.update(filename.encode('utf-8'))
    hashed = m.hexdigest()
    return (
        'https://upload.wikimedia.org/wikipedia/commons/thumb/%s/%s/%s/%dpx-%s' %
        (hashed[0], hashed[0:2], filename, thumbnail_width, filename))

class SuggestEngine(object):
    def __init__(self, redis_client):
        self.r = redis_client
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
                    item.get('labels',{}).get(lang,id))

    def preview(self, args):
        id = args['id']
        item = self.store.get_item(id)
        lang = args.get('lang', 'en')
        image = self.get_image_for_item(item, lang)

        args = {
            'id':id,
            'label':item.get('labels', {}).get(lang, id),
            'description': item.get('descriptions', {}).get(lang, ''),
            'image': image,
            'url': 'https://www.wikidata.org/entity/'+id,
            'width': preview_width,
            'height': preview_height,
        }
        return template(self.preview_template,
            **args)

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
            {'id':item['id'],
             'name':item['label'],
            }
            for item in search_results]
        return {'result':result}

    def find_type(self, args):
        return self.find_something(args)

    def find_property(self, args):
        return self.find_something(args, 'property', "Property:")

    def find_entity(self, args):
        return self.find_something(args)

