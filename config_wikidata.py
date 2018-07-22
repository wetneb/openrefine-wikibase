
"""
This file defines a few constants which configure
which Wikibase instance and which property/item ids
should be used
"""

# Endpoint of the MediaWiki API of the Wikibase instance
mediawiki_api_endpoint = 'https://www.wikidata.org/w/api.php'

# Regexes and group ids to extracts Qids and Pids from URLs
import re
q_re = re.compile(r'(<?https?://www.wikidata.org/(entity|wiki)/)?(Q[0-9]+)>?')
q_re_group_id = 3
p_re = re.compile(r'(<?https?://www.wikidata.org/(entity/|wiki/Property:))?(P[0-9]+)>?')
p_re_group_id = 3

# Identifier space and schema space exposed to OpenRefine.
# This should match the IRI prefixes used in RDF serialization.
# Note that you should be careful about using http or https there,
# because any variation will break comparisons at various places.
identifier_space = 'http://www.wikidata.org/entity/'
schema_space = 'http://www.wikidata.org/prop/direct/'

# Pattern used to form the URL of a Qid.
# This is only used for viewing so it is fine to use any protocol (therefore, preferably HTTPS if supported)
qid_url_pattern = 'https://www.wikidata.org/wiki/{{id}}'

# By default, filter out any items which are instance
# of a subclass of this class.
# For Wikidata, this is "Wikimedia internal stuff".
# This filters out the disambiguation pages, categories, ...
# Set to None to disable this filter
avoid_items_of_class = 'Q17442446'

# Service name exposed at various places,
# mainly in the list of reconciliation services of users
service_name = 'DEV Wikidata'

# URL (without the trailing slash) where this server runs
this_host = 'http://localhost:8000'

# The default limit on the number of results returned by us
default_num_results = 25

# The maximum number of search results to retrieve from the Wikidata search API
wd_api_max_search_results = 50 # need a bot account to get more

# The matching score above which we should automatically match an item
validation_threshold = 95

# Redis client used for caching at various places
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Redis prefix to use in front of all keys
redis_key_prefix = 'openrefine-wikidata:'

# Headers for the HTTP requests made by the tool
headers = {
    'User-Agent':service_name + ' (OpenRefine-Wikibase reconciliation service)',
}

# Previewing settings

# Dimensions of the preview
zoom_ratio = 1.0
preview_height = 500
preview_width = 400

# With which should be requested from Commons for the thumbnail
thumbnail_width = 130

# All properties to use to get an image
image_properties = [
    'P18',
    'P14',
    'P15',
    'P158',
    'P181',
    'P242',
    'P1766',
    'P1801',
    'P1846',
    'P2713',
    'P2716',
    'P2910',
    'P3311',
    'P3383',
    'P3451',
    'P1621',
    'P154',
]

# URL pattern to retrieve an image from its filename
image_download_pattern = 'https://upload.wikimedia.org/wikipedia/commons/thumb/%s/%s/%s/%dpx-%s'

# Fallback URL of the image to use when previewing an item with no image
fallback_image_url = this_host + '/static/wikidata.png'

# Alt text of the fallback image
fallback_image_alt = 'Wikidata'

# Autodescribe endpoint to use.
# this is used to generate automatic descriptions from item contents.
# (disable this with: autodescribe_endpoint = None )
autodescribe_endpoint = 'https://tools.wmflabs.org/autodesc/'

# Property proposal settings

# Default type : entity (Q35120)
default_type_entity = 'Q35120'

# Property to follow to fetch properties for a given type
property_for_this_type_property = 'P1963'

# Type expected as target of a given property
subject_item_of_this_property_pid = 'P1629'
