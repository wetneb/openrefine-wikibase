import pytest
import unittest
from funcparserlib.lexer import Token

from wdreconcile.propertypath import tokenize_property
from wdreconcile.wikidatavalue import QuantityValue, ItemValue, IdentifierValue, StringValue, TimeValue, MonolingualValue
from wdreconcile.itemstore import ItemStore

pytestmark = pytest.mark.asyncio

def test_lexer():
    assert list(tokenize_property('P17')) == [Token('PID','P17')]
    assert list(tokenize_property('P17/P297')) == [Token('PID','P17'),Token('SLASH','/'),Token('PID','P297')]
    assert list(tokenize_property('(P17/P297)')) == (
                [Token('LBRA', '('),
                Token('PID','P17'),
                Token('SLASH','/'),
                Token('PID','P297'),
                Token('RBRA',')')])

def test_parse(property_factory):
    samples = [
        '.',
        'P17',
        'P17/P297',
        '(P131/P17|P17)',
        'P14/(P131/P17|P17)',
        'P131/(P17|.)',
        'P17/Len',
        'P17/Sfrwiki',
        '(Len|Afi)',
        'P4424_P518',
        'P17/qid',
        'qid',
    ]
    for sample in samples:
        assert str(property_factory.parse(sample)) == sample

def test_invalid_expression(property_factory):
    with pytest.raises(ValueError):
        property_factory.parse('P') # lexing error

    with pytest.raises(ValueError):
        property_factory.parse('P78/') # parsing error

    with pytest.raises(ValueError):
        property_factory.parse('(P78/P17') # parsing error

@pytest.fixture
def resolve(property_factory):
    async def _resolve(exp, qid):
        path = property_factory.parse(exp)
        return list(await path.step(ItemValue(id=qid)))
    return _resolve

async def test_datetime(resolve):
    assert (await resolve('P571', 'Q34433') ==
        [TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1096-01-01T00:00:00Z')])

async def test_resolve_property_path(resolve):
    assert (await resolve('P297', 'Q142') ==
        [IdentifierValue(value='FR')])

    assert (
        IdentifierValue(value='FR') in
        await resolve('Afr', 'Q142'))

    assert (
        await resolve('P17/P297', 'Q83259') ==
        [IdentifierValue(value='FR')])

    assert (
        await resolve('P246', 'Q743') ==
        [StringValue(value='W')])

    assert (
        await resolve('P1449', 'Q1249148') == [
            MonolingualValue(text='Dick',language='en'),
            MonolingualValue(text='Rich',language='en'),
            MonolingualValue(text='Rik',language='en'),
            MonolingualValue(text='Richey',language='en'),
            MonolingualValue(text='Rick',language='en'),
            MonolingualValue(text='Ritchie',language='en')])

    assert (
        await resolve('P17', 'Q83259') ==
        [ItemValue(id='Q142')]
    )

    assert (
        await resolve('P17/qid', 'Q83259') ==
        [IdentifierValue(value='Q142')])

    assert (
        await resolve('qid', 'Q142') ==
        [IdentifierValue(value='Q142')])

    # Qualifier
    assert (
        await resolve('P4424_P518', 'Q42023001') ==
        [ItemValue(id='Q2106255')])

    # With dot
    assert (
        await resolve('./P2427', 'Q34433') ==
            [IdentifierValue(value='grid.4991.5')])
    assert (
        await resolve('P2427/.', 'Q34433') ==
            [IdentifierValue(value='grid.4991.5')])

    # With disjunction
    assert (
        set(await resolve('P17', # country
                    'Q30273752', # microsoft france
                    )) ==
                {ItemValue(id='Q142')}) # france
    assert (
        set(await resolve('P749/P17', # parent org. / country
                    'Q30273752', # microsoft france
                        )) ==
                {ItemValue(id='Q30')}) # USA
    assert (
        set(await resolve('P17|(P749/P17)', # brackets not actually needed
                    'Q30273752')) ==
                {ItemValue(id='Q142'),ItemValue(id='Q30')}) # USA + France

    # With term
    assert (
        await resolve('P17/Lfr', 'Q83259') ==
        [IdentifierValue(value='France')]
    )

    # With sitelink
    assert (
        await resolve('P17/Sfrwiki', 'Q83259') ==
        [IdentifierValue(value='France')]
    )

@pytest.fixture
def value_types(resolve):
    async def _value_types(path, qid):
        return {v.value_type
            for v in await resolve(path, qid) if not v.is_novalue()}
    return _value_types

async def test_value_types(value_types):
    assert (
        await value_types('P571', 'Q34433') ==
        {'time'})

    assert (
        await value_types('P2124', 'Q2994760') ==
        {'quantity'})

    assert (
        await value_types('P625', 'Q142') ==
        {"globe-coordinate"})

    assert (
        await value_types('P2427', 'Q34433') ==
        {"external-id"})

    assert (
        await value_types('P856', 'Q34433') ==
        {"url"})

    assert (
        await value_types('P31', 'Q34433') ==
        {"wikibase-item"})

    assert (
        await value_types('P1477', 'Q42') ==
        {"monolingualtext"})

    assert (
        await value_types('P18', 'Q34433') ==
        {"commonsMedia"})

async def test_subfields(resolve):
    assert (
        await resolve('P571@year', # inception year
                    'Q34433') == # oxford
        [QuantityValue(amount=1096)])

    assert (
        await resolve('P585@month', # point in time year
                    'Q30274958') == # grenfell tower fire
        [QuantityValue(amount=6)]) # June

    assert (
        await resolve('P625@lng', # longitude
                    'Q179385') == # Greenwich
        [QuantityValue(amount=0)]) # Reference!

async def test_is_unique_identifier(property_factory, mock_aioresponse):
    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0ASELECT+?pid+WHERE+%7B+?pid+wdt:P31/wdt:P279*+wd:Q19847637+%7D%0A',
        payload={'results':{'bindings':[
            {'pid':{'value':'http://www.wikidata.org/entity/P3500'}},
            {'pid':{'value':'http://www.wikidata.org/entity/P2427'}},
        ]}})

    assert (
        await property_factory.parse('P3500').is_unique_identifier())
    assert (
        await property_factory.parse('P2427').is_unique_identifier())
    assert (
        await property_factory.parse('./P2427').is_unique_identifier())
    assert (
        await property_factory.parse('(P2427|P3500)').is_unique_identifier())
    assert not (
        await property_factory.parse('.').is_unique_identifier())
    assert not (
        await property_factory.parse('P31').is_unique_identifier())
    assert not (
        await property_factory.parse('P3500/P2427').is_unique_identifier())
    assert not (
        await property_factory.parse('(P3500|P17)').is_unique_identifier())
    assert not (
        await property_factory.parse('(P3500|Len)').is_unique_identifier())

@pytest.fixture
def fetch_by_values(property_factory):
    async def _fetch_by_values(path_string, values, lang='en'):
        path = property_factory.parse(path_string)
        return await path.fetch_qids_by_values(values, lang)
    return _fetch_by_values

async def test_fetch_qids_by_values(fetch_by_values, mock_aioresponse):
    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+wdt:P214+?value.%0A++++++++++++VALUES+?value+%7B+%22142129514%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+4%0A++++++++',
        payload={
        'results':{
        'bindings': [
            {'qid':{'value':'http://www.wikidata.org/entity/Q34433'},
             'value':{'value':'142129514'},
             'label':{'value':'University of Oxford'}}
        ]}
    })

    # Just one value, VIAF id for Oxford
    assert (
        await fetch_by_values('P214', ['142129514']) ==
        {'142129514':[('Q34433', 'University of Oxford')]})

    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+(wdt:P214%7Cwdt:P3500)+?value.%0A++++++++++++VALUES+?value+%7B+%22142129514%22+%222167%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+8%0A++++++++',
        payload={
        'results':{
            'bindings': [
            {'qid':{'value':'http://www.wikidata.org/entity/Q34433'},
             'value':{'value':'142129514'},
             'label':{'value':'University of Oxford'}},
            {'qid':{'value':'http://www.wikidata.org/entity/Q49108'},
             'value':{'value':'2167'},
             'label':{'value':'Massachusetts Institute of Technology'}}
            ]
        }
    })

    # Two different properties
    assert (
        await fetch_by_values('(P214|P3500)', ['142129514','2167']) ==
        {'142129514':[('Q34433', 'University of Oxford')],
            '2167':[('Q49108', 'Massachusetts Institute of Technology')]})


@pytest.mark.xfail
async def test_expected_types(property_factory):
    # Property "country (P17)" has type country (Q6256) at least
    assert (
        'Q6256' in await property_factory.parse('P17').expected_types())
    # GRID identifier has no type
    assert (
        await property_factory.parse('P2427').expected_types() == [])
    # A property path followed by another
    assert (
        'Q6256' in await property_factory.parse('P131/P17').expected_types())
    # A disjunction
    assert (
        'Q6256' in await property_factory.parse('P131|P17').expected_types())
    assert (
        'Q56061' in await property_factory.parse('P131|P17').expected_types())

async def test_readable_name(property_factory):
    assert (
        'P131/P17' == await property_factory.parse('P131/P17').readable_name('fr'))
    assert (
        'official website' == await property_factory.parse('P856').readable_name('en'))

