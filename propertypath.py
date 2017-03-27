
from funcparserlib.parser import skip
from funcparserlib.parser import some
from funcparserlib.parser import forward_decl
from funcparserlib.parser import finished
from funcparserlib.parser import NoParseError
from funcparserlib.lexer import make_tokenizer
from funcparserlib.lexer import LexerError
import itertools
from SPARQLWrapper import SPARQLWrapper, JSON
from collections import defaultdict

from language import language_fallback
from utils import to_q
from utils import to_p

property_lexer_specs = [
    ('DOT', (r'\.',)),
    ('PID', (r'P\d+',)),
    ('SLASH', (r'/',)),
    ('PIPE', (r'\|',)),
    ('LBRA', (r'\(',)),
    ('RBRA', (r'\)',)),
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
        self.unique_ids_key = 'openrefine_wikidata:unique_ids'
        self.ttl = 4*24*60*60 # 4 days
        self.sparql = SPARQLWrapper("https://query.wikidata.org/bigdata/namespace/wdq/sparql")

        self.parser = forward_decl()

        atomic = forward_decl()
        concat_path = forward_decl()
        pipe_path = forward_decl()

        atomic.define(
            (t('PID') >> self.make_leaf) |
            (t('DOT') >> self.make_empty) |
            (st('LBRA') + pipe_path + st('RBRA'))
        )

        concat_path.define(
            ((atomic + st('SLASH') + concat_path) >> self.make_slash) |
            atomic
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

    def make_slash(self, lst):
        return ConcatenatedPropertyPath(self, lst[0], lst[1])

    def make_pipe(self, lst):
        return DisjunctedPropertyPath(self, lst[0], lst[1])

    def parse(self, property_path_string):
        """
        Parses a string representing a property path
        """
        try:
            tokens = list(tokenize_property(property_path_string))
            return self.parser.parse(tokens)
        except (LexerError, NoParseError) as e:
            raise ValueError(str(e))

    def is_identifier_pid(self, pid):
        """
        Does this PID represent a unique identifier?
        """
        self.prefetch_unique_ids()
        return self.r.sismember(self.unique_ids_key, pid)

    def prefetch_unique_ids(self):
        """
        Prefetches the list of properties that correspond to unique
        identifiers
        """
        if self.r.exists(self.unique_ids_key):
            return # this list was already fetched

        # Q19847637 is "Wikidata property representing a unique
        # identifier"
        # https://www.wikidata.org/wiki/Q19847637

        sparql_query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        SELECT ?pid WHERE { ?pid wdt:P31/wdt:P279* wd:Q19847637 }
        """
        self.sparql.setQuery(sparql_query)
        self.sparql.setReturnFormat(JSON)
        results = self.sparql.query().convert()

        for results in results['results']['bindings']:
            pid = to_p(results['pid']['value'])
            self.r.sadd(self.unique_ids_key, pid)

        self.r.expire(self.unique_ids_key, self.ttl)


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

    def get_item(self, item):
        """
        Helper coercing a value to an item.
        If it is already a dict, it is returned
        untouched. Otherwise we convert it to a
        Wikidata id and fetch it.
        """
        if type(item) == dict:
            return item
        qid = to_q(item)
        if qid:
            return self.item_store.get_item(qid)

    def evaluate(self, item, lang=None, fetch_labels=True):
        """
        Evaluates the property path on the
        given item. Returns a list of values.

        :param lang: the language to use, if any labels are fetched
        :param fetch_labels: should we returns items or labels?
        """

        def fetch_label(v):
            item = self.get_item(v)
            if not item:
                return [v] # this is already a value

            if not lang:
                # return all labels and aliases
                labels = list(item.get('labels', {}).values())
                aliases = item.get('aliases', [])
                return labels+aliases
            else:
                labels = item.get('labels', {})
                return [language_fallback(labels, lang)]

        values = self.step(item)
        if fetch_labels:
            values = itertools.chain(
                *map(fetch_label, values)
            )

        return list(values)


    def step(self, v):
        """
        Evaluates the property path on the
        given value (most likely an item).
        Returns a list of other values.

        This is the method that should be
        reimplemented by subclasses.
        """
        raise NotImplemented

    def is_unique_identifier(self):
        """
        Given a path, does this path represent a unique identifier
        for the item it starts from?

        This only happens when the path is a disjunction of single
        properties which are all unique identifiers
        """
        try:
            return self.uniform_depth() == 1
        except ValueError: # the depth of the path is not uniform
            return False

    def uniform_depth(self):
        """
        The uniform depth of a path, if it exists, is the
        number of steps from the item to the target, in
        any disjunction.

        Moreover, all the properties involved in the path
        have to be unique identifiers.

        If any of these properties is not satisfied, ValueError is
        raised.
        """
        raise NotImplemented

    def ends_with_identifier(self):
        """
        Does this path only end with identifier properties?
        These identifiers are not necessarily unique.
        """
        raise NotImplemented

    def fetch_qids_by_values(self, values, lang):
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
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
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

        sparql = self.factory.sparql
        sparql.setQuery(sparql_query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()

        value_to_qid = defaultdict(list)

        for results in results['results']['bindings']:
            qid = to_q(results['qid']['value'])
            label = results['label'].get('value') or qid
            primary_id = results['value']['value']
            value_to_qid[primary_id].append((qid,label))

        return value_to_qid


    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

class EmptyPropertyPath(PropertyPath):
    """
    An empty path
    """

    def step(self, v):
        return [v]

    def __str__(self, add_prefix=False):
        return '.'

    def uniform_depth(self):
        return 0

    def ends_with_identifier(self):
        return False

class LeafProperty(PropertyPath):
    """
    A node for a leaf, just a simple property like "P31"
    """
    def __init__(self, factory, pid):
        super(LeafProperty, self).__init__(factory)
        self.pid = pid

    def step(self, v):
        item = self.get_item(v)
        return item.get(self.pid, [])

    def __str__(self, add_prefix=False):
        prefix = 'wdt:' if add_prefix else ''
        return prefix+self.pid

    def uniform_depth(self):
        if not self.factory.is_identifier_pid(self.pid):
            raise ValueError('One property is not an identifier')
        return 1

    def ends_with_identifier(self):
        return self.factory.is_identifier_pid(self.pid)

class ConcatenatedPropertyPath(PropertyPath):
    """
    Executes two property paths one after
    the other: this is the / operator
    """
    def __init__(self, factory, a, b):
        super(ConcatenatedPropertyPath, self).__init__(factory)
        self.a = a
        self.b = b

    def step(self, v):
        intermediate_values = self.a.step(v)
        final_values = [
            self.b.step(v2)
            for v2 in intermediate_values
        ]
        return itertools.chain(*final_values)

    def __str__(self, add_prefix=False):
        return self.a.__str__(add_prefix) + '/' + self.b.__str__(add_prefix)

    def uniform_depth(self):
        return self.a.uniform_depth() + self.b.uniform_depth()

    def ends_with_identifier(self):
        return self.b.ends_with_identifier()

class DisjunctedPropertyPath(PropertyPath):
    """
    A disjunction of two property paths
    """
    def __init__(self, factory, a, b):
        super(DisjunctedPropertyPath, self).__init__(factory)
        self.a = a
        self.b = b

    def step(self, v):
        va = self.a.step(v)
        vb = self.b.step(v)
        return itertools.chain(*[va,vb])

    def __str__(self, add_prefix=False):
        return '('+self.a.__str__(add_prefix) + '|' + self.b.__str__(add_prefix)+')'

    def uniform_depth(self):
        depth_a = self.a.uniform_depth()
        depth_b = self.b.uniform_depth()
        if depth_a != depth_b:
            raise ValueError('The depth is not uniform.')
        return depth_a

    def ends_with_identifier(self):
        return (self.a.ends_with_identifier() and
                self.b.ends_with_identifier())
