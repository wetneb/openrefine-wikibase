import redis

max_results = 20
service_name = 'Wikidata Reconciliation for OpenRefine'

wd_api_search_results = 10 # max 50

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)


