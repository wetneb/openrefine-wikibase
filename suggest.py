from itemstore import ItemStore
import requests

class SuggestEngine(object):
    def __init__(self, redis_client):
        self.r = redis_client
        self.store = ItemStore(self.r)
        self.store.ttl = 24*60*60 # one day

    def flyout(self, args):
        id = args['id']
        lang = args.get('lang', 'en')
        label = self.store.get_label(id, lang)
        return {'html':
            '<span class="wd_label">%s</span>' % label
        }

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

        prefixlen = len(prefix)
        props = [p['title'][prefixlen:]
                    for p in resp.get('query',{}).get('search',{})]

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

