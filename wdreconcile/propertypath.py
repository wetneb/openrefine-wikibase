
from funcparserlib.parser import skip
from funcparserlib.parser import some
from funcparserlib.parser import forward_decl
from funcparserlib.parser import finished
from funcparserlib.parser import NoParseError
from funcparserlib.lexer import make_tokenizer
from funcparserlib.lexer import LexerError
import itertools
from collections import defaultdict

from .utils import to_p
from .utils import to_q
from .sparqlwikidata import sparql_wikidata
from .subfields import subfield_factory
from .wikidatavalue import WikidataValue, ItemValue, IdentifierValue
from config import wdt_prefix
from config import redis_key_prefix
from config import sparql_query_to_fetch_unique_id_properties
from .language import language_fallback

property_lexer_specs = [
    ('DOT', (r'\.',)),
    ('PID', (r'P\d+',)),
    ('TERM', (r'[LDA][a-z\-]+',)),
    ('SITELINK', (r'S[a-z\-]+',)),
    ('QID', (r'qid',)),
    ('SLASH', (r'/',)),
    ('PIPE', (r'\|',)),
    ('LBRA', (r'\(',)),
    ('RBRA', (r'\)',)),
    ('UNDER', (r'_',)),
    ('AT', (r'@',)),
    ('SUBFIELD', (r'[a-z]+',)),
]
tokenize_property = make_tokenizer(property_lexer_specs)

def t(code):
    return some(lambda x: x.type == code)

def st(code):
    return skip(t(code))

class PropertyFactory(object):
    """
    A class to build property paths
    """
    def __init__(self, item_store):
        self.item_store = item_store
        self.r = self.item_store.r # redis client
        self.unique_ids_key = redis_key_prefix+'unique_ids'
        self.ttl = 1*24*60*60 # 1 day

        self.parser = forward_decl()

        atomic = forward_decl()
        atomic_subfield = forward_decl()
        concat_path = forward_decl()
        pipe_path = forward_decl()

        atomic.define(
            (t('PID') + st('UNDER') + t('PID') >> self.make_qualifier) |
            (t('PID') >> self.make_leaf) |
            (t('QID') >> self.make_qid) |
            (t('TERM') >> self.make_term) |
            (t('SITELINK') >> self.make_sitelink) |
            (t('DOT') >> self.make_empty) |
            (st('LBRA') + pipe_path + st('RBRA'))
        )

        atomic_subfield.define(
            (atomic + st('AT') + t('SUBFIELD') >> self.make_subfield) |
            atomic
        )

        concat_path.define(
            ((atomic_subfield + st('SLASH') + concat_path) >> self.make_slash) |
            atomic_subfield
        )

        pipe_path.define(
            ((concat_path + st('PIPE') + pipe_path) >> self.make_pipe) |
            concat_path
        )

        self.parser.define(
            (
                pipe_path
            ) + finished >> (lambda x: x[0])
        )

    def make_identity(self, a):
        return a

    def make_empty(self, dot=None):
        return EmptyPropertyPath(self)

    def make_leaf(self, pid):
        return LeafProperty(self, pid.value)

    def make_qid(self, node):
        return QidProperty(self)

    def make_qualifier(self, pids):
        return QualifierProperty(self, pids[0].value, pids[1].value)

    def make_term(self, term):
        return TermPath(self, term.value[0], term.value[1:])

    def make_sitelink(self, sitelink):
        return SitelinkPath(self, sitelink.value[1:])

    def make_slash(self, lst):
        return ConcatenatedPropertyPath(self, lst[0], lst[1])

    def make_pipe(self, lst):
        return DisjunctedPropertyPath(self, lst[0], lst[1])

    def make_subfield(self, lst):
        return SubfieldPropertyPath(self, lst[0], lst[1].value)

    def parse(self, property_path_string):
        """
        Parses a string representing a property path
        """
        try:
            tokens = list(tokenize_property(property_path_string))
            return self.parser.parse(tokens)
        except (LexerError, NoParseError) as e:
            raise ValueError("Could not parse '{}': {}".format(property_path_string, str(e)))

    async def is_identifier_pid(self, pid):
        """
        Does this PID represent a unique identifier?
        """
        await self.prefetch_unique_ids()
        return await self.r.sismember(self.unique_ids_key, pid)

    async def prefetch_unique_ids(self):
        """
        Prefetches the list of properties that correspond to unique
        identifiers
        """
        if await self.r.exists(self.unique_ids_key):
            return # this list was already fetched

        for pid in await self._fetch_unique_ids():
            if pid:
                await self.r.sadd(self.unique_ids_key, pid)

        await self.r.expire(self.unique_ids_key, self.ttl)

    async def _fetch_unique_ids(self):
        # Q19847637 is "Wikidata property representing a unique
        # identifier"
        # https://www.wikidata.org/wiki/Q19847637

        results = await sparql_wikidata(self.item_store.http_session, sparql_query_to_fetch_unique_id_properties)
        return [to_p(result['pid']['value']) for result in results['bindings']]


class PropertyPath(object):
    """
    A class representing a SPARQL-like
    property path. At the moment it only
    supports the "/" and "|" operators.
    """

    def __init__(self, factory):
        """
        Initializes the property path and
        binds it to a given itemstore, for
        later evaluation
        """
        self.factory = factory
        self.item_store = factory.item_store

    async def get_item(self, item):
        """
        Helper coercing an ItemValue to
        the dict representing the item.
        """
        if not item.value_type == "wikibase-item":
            raise ValueError("get_item expects an ItemValue")
        return await self.item_store.get_item(item.id)

    async def evaluate(self, item_value, lang=None, fetch_labels=True):
        """
        Evaluates the property path on the
        given item, and returning strings (either qids or labels).

        :param lang: the language to use, if any labels are fetched
        :param fetch_labels: should we returns items or labels?
        """
        async def fetch_label(v):
            if v.value_type != "wikibase-item":
                return [v.as_string()]
            item = await self.get_item(v)

            if not lang:
                # return all labels and aliases
                labels = list(item.get('labels', {}).values())
                aliases = item.get('aliases', [])
                return labels+aliases
            else:
                labels = item.get('labels', {})
                return [language_fallback(labels, lang)]

        values = await self.step(item_value)
        if fetch_labels:
            new_values = []
            for v in values:
                new_values += await fetch_label(v)
            values = new_values
        else:
            values = [
                val.json.get('id')
                for val in values
            ]

        return list(values)


    async def step(self, v, referenced='any', rank='best'):
        """
        Evaluates the property path on the
        given value (most likely an item).
        Returns a list of other values.

        This is the method that should be
        reimplemented by subclasses.

        :param references: either 'any', 'referenced' or 'nonwiki'
            to filter which statements should be considered (all statements,
            only the ones with references, or only the ones with references
            to sources outside wikis)
        :param rank: the ranks of the statements to consider: 'any', 'best',
           or 'no_deprecated'
        """
        raise NotImplementedError()

    async def is_unique_identifier(self):
        """
        Given a path, does this path represent a unique identifier
        for the item it starts from?

        This only happens when the path is a disjunction of single
        properties which are all unique identifiers.

        This is async because we might need to fetch the set of unique
        identifiers from the Wikibase instance.
        """
        try:
            return await self.uniform_depth() == 1
        except ValueError: # the depth of the path is not uniform
            return False

    async def uniform_depth(self):
        """
        The uniform depth of a path, if it exists, is the
        number of steps from the item to the target, in
        any disjunction.

        Moreover, all the properties involved in the path
        have to be unique identifiers.

        If any of these properties is not satisfied, ValueError is
        raised.
        """
        raise NotImplementedError()

    async def fetch_qids_by_values(self, values, lang):
        """
        Fetches all the Qids and their labels in the selected language,
        which bear any of the given values along this property.

        The results are capped to four times the number of given
        values, as it is expected that the relevant property has
        a uniqueness constraint, so instances should be mostly unique.
        """
        values_str = ' '.join('"%s"' % v
                          for v in values )
        limit = 4*len(values)
        sparql_query = """
        SELECT ?qid ?value
        (SAMPLE(COALESCE(?best_label, ?fallback_label)) as ?label)
        WHERE {
            ?qid %s ?value.
            VALUES ?value { %s }
            OPTIONAL {
                ?qid rdfs:label ?best_label .
                FILTER(LANG(?best_label) = "%s")
            }
            OPTIONAL { ?qid rdfs:label ?fallback_label }
        }
        GROUP BY ?qid ?value
        LIMIT %d
        """ % (
            self.__str__(add_prefix=True),
            values_str,
            lang,
            limit)

        results = await sparql_wikidata(self.item_store.http_session, sparql_query)

        value_to_qid = defaultdict(list)

        for results in results['bindings']:
            qid = to_q(results['qid']['value'])
            label = (results.get('label') or {}).get('value') or qid
            primary_id = results['value']['value']
            value_to_qid[primary_id].append((qid,label))

        return value_to_qid

    async def expected_types(self):
        """
        Returns a list of possible types expected
        as values of this property.
        """
        return []

    async def readable_name(self, lang):
        """
        Returns a readable name of the property in the given
        language. By default it is just the string representation.
        """
        return self.__str__()

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

class EmptyPropertyPath(PropertyPath):
    """
    An empty path
    """

    async def step(self, v, referenced='any', rank='any'):
        return [v]

    def __str__(self, add_prefix=False):
        return '.'

    async def uniform_depth(self):
        return 0

    async def expected_types(self):
        return []

class QualifierProperty(PropertyPath):
    """
    Fetches the value of a qualifier of a given claim, like "P31_P642".
    """
    def __init__(self, factory, pid_property, pid_qualifier):
        super(QualifierProperty, self).__init__(factory)
        self.property_pid = pid_property
        self.qualifier_pid = pid_qualifier

    async def step(self, v, referenced='any', rank='any'):
        if v.value_type != 'wikibase-item':
            return []
        item = await self.get_item(v)
        datavalues = []
        claims = item.get(self.property_pid, [])

        if rank == 'best':
            ranks = [claim['rank'] for claim in claims]
            best_rank = max(ranks) if ranks else 'deprecated'
            rank = best_rank

        result = []
        for claim in claims:
            if claim['rank'] < rank:
                continue
            references = claim.get('references', [])
            if referenced == 'internal' and not references:
                continue
            for qualifier in (claim.get('qualifiers') or {}).get(self.qualifier_pid) or []:
                v = WikidataValue.from_datavalue(qualifier)
                result.append(v)
        return result

    def __str__(self, add_prefix=False):
        prefix = wdt_prefix if add_prefix else ''
        return prefix+self.property_pid+'_'+self.qualifier_pid

    async def uniform_depth(self):
        raise ValueError('One property is not an identifier')

    async def expected_types(self):
        """
        Retrieve the expected type from Wikibase
        """
        # TODO
        return []

    async def readable_name(self, lang):
        return await self.item_store.get_label(self.property_pid, lang)+', '+self.item_store.get_label(self.qualifier_pid, lang)


class LeafProperty(PropertyPath):
    """
    A node for a leaf, just a simple property like "P31"
    """
    def __init__(self, factory, pid):
        super(LeafProperty, self).__init__(factory)
        self.pid = pid

    async def step(self, v, referenced='any', rank='any'):
        if v.value_type != 'wikibase-item':
            return []
        item = await self.get_item(v)
        datavalues = []
        claims = item.get(self.pid, [])

        if rank == 'best':
            ranks = [claim['rank'] for claim in claims]
            best_rank = max(ranks) if ranks else 'deprecated'
            rank = best_rank

        result = []
        for claim in claims:
            if claim['rank'] < rank:
                continue
            references = claim.get('references', [])
            if referenced == 'internal' and not references:
                continue
            # TODO handle nowiki case
            mainsnak = claim.get('mainsnak')
            if not mainsnak:
                continue
            v = WikidataValue.from_datavalue(mainsnak)
            result.append(v)
        return result

    def __str__(self, add_prefix=False):
        prefix = wdt_prefix if add_prefix else ''
        return prefix+self.pid

    async def uniform_depth(self):
        if not await self.factory.is_identifier_pid(self.pid):
            raise ValueError('One property is not an identifier')
        return 1

    async def expected_types(self):
        """
        Retrieve the expected type from Wikibase
        """
        # TODO
        return []

    async def readable_name(self, lang):
        return await self.item_store.get_label(self.pid, lang)

class QidProperty(PropertyPath):
    """
    A node to extract the Qid of an item.
    """
    def __init__(self, factory):
        super(QidProperty, self).__init__(factory)

    async def step(self, v, referenced='any', rank='any'):
        if v.value_type != 'wikibase-item':
            return []
        return [IdentifierValue(value=v.id)]

    def __str__(self, add_prefix=False):
        return 'qid'

    async def uniform_depth(self):
        return 1

    async def expected_type(self):
        return []

    async def readable_name(self, lang):
        # We could potentially look up some 'Qid' item to get translations here…
        return 'Qid'

class TermPath(PropertyPath):
    """
    A node for accessing the terms (label, description and aliases) of an item
    """
    def __init__(self, factory, term_type, lang):
        super(TermPath, self).__init__(factory)
        self.term_type = term_type
        self.lang = lang

    async def step(self, v, referenced='any', rank='any'):
        if v.value_type != 'wikibase-item':
            return []

        item = await self.get_item(v)
        result = []
        if self.term_type == 'L':
            dct = item.get('labels') or {}
            if self.lang in dct:
                result.append(IdentifierValue(value=dct[self.lang]))
        elif self.term_type == 'D':
            dct = item.get('descriptions') or {}
            if self.lang in dct:
                result.append(IdentifierValue(value=dct[self.lang]))
        elif self.term_type == 'A':
            dct = item.get('full_aliases') or {}
            for alias in dct.get(self.lang) or []:
                result.append(IdentifierValue(value=alias))
        return result

    def __str__(self, add_prefix=False):
        return self.term_type + self.lang

    async def uniform_depth(self):
        raise ValueError('One property is not an identifier')

    async def expected_types(self):
        """
        Retrieve the expected type from Wikidata
        """
        return []

    async def readable_name(self, lang):
        return self.term_type + self.lang

class SitelinkPath(PropertyPath):
    """
    A node for accessing the sitelinks of an item
    """

    def __init__(self, factory, site):
        super(SitelinkPath, self).__init__(factory)
        self.site = site

    async def step(self, v, referenced='any', rank='any'):
        if v.value_type != 'wikibase-item':
            return []
        item = await self.get_item(v)

        if not item:
            return []
        sitelink = (item.get('sitelinks') or {}).get(self.site)
        if sitelink:
            return [IdentifierValue(value=sitelink)]

    def __str__(self, add_prefix=False):
        return 'S'+self.site

    async def uniform_depth(self):
        raise ValueError('One property is not an identifier')

    async def expected_types(self):
        return []

    async def readable_name(self, lang):
        return 'Sitelink ' + self.site

class ConcatenatedPropertyPath(PropertyPath):
    """
    Executes two property paths one after
    the other: this is the / operator
    """
    def __init__(self, factory, a, b):
        super(ConcatenatedPropertyPath, self).__init__(factory)
        self.a = a
        self.b = b

    async def step(self, v, referenced='any', rank='any'):
        intermediate_values = await self.a.step(v, referenced, rank)
        final_values = [
            (await self.b.step(v2, referenced, rank))
            for v2 in intermediate_values
        ]
        return itertools.chain(*final_values)

    def __str__(self, add_prefix=False):
        return self.a.__str__(add_prefix) + '/' + self.b.__str__(add_prefix)

    async def uniform_depth(self):
        return await self.a.uniform_depth() + await self.b.uniform_depth()

    async def expected_types(self):
        return await self.b.expected_types()

class DisjunctedPropertyPath(PropertyPath):
    """
    A disjunction of two property paths
    """
    def __init__(self, factory, a, b):
        super(DisjunctedPropertyPath, self).__init__(factory)
        self.a = a
        self.b = b

    async def step(self, v, referenced='any', rank='any'):
        va = await self.a.step(v, referenced, rank)
        vb = await self.b.step(v, referenced, rank)
        return itertools.chain(*[va,vb])

    def __str__(self, add_prefix=False):
        return '('+self.a.__str__(add_prefix) + '|' + self.b.__str__(add_prefix)+')'

    async def uniform_depth(self):
        depth_a = await self.a.uniform_depth()
        depth_b = await self.b.uniform_depth()
        if depth_a != depth_b:
            raise ValueError('The depth is not uniform.')
        return depth_a

    async def expected_types(self):
        return (await self.a.expected_types() + await self.b.expected_types())

class SubfieldPropertyPath(PropertyPath):
    """
    A property path that returns a subfield of another property path
    """
    def __init__(self, factory, path, subfield):
        super(SubfieldPropertyPath, self).__init__(factory)
        self.path = path
        self.subfield = subfield

    async def step(self, v, referenced='any', rank='any'):
        orig_values = list(await self.path.step(v, referenced, rank))
        images_values = list(map(lambda val: subfield_factory.run(self.subfield, val), orig_values))
        return (val for val in images_values if val is not None)

    async def uniform_depth(self):
        raise ValueError('One property bears a subfield')

    async def expected_types(self):
        return []

    def __str__(self, add_prefix=False):
        return self.path.__str__(add_prefix) + '@' + self.subfield
