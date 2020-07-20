
import pytest
import aiohttp
import aioredis
import os
import json
from quart import Quart

from aioresponses import aioresponses

from wdreconcile.sitelink import SitelinkFetcher
from wdreconcile.itemstore import ItemStore
from wdreconcile.propertypath import PropertyFactory
from wdreconcile.typematcher import TypeMatcher
from wdreconcile.engine import ReconcileEngine
from wdreconcile.suggest import SuggestEngine

from config import redis_uri

## Environment (HTTP, redis)

@pytest.fixture
async def http_session():
    async with aiohttp.ClientSession() as session:
        yield session

@pytest.fixture
async def redis_client():
    redis = await aioredis.create_redis_pool(redis_uri)
    await redis.flushdb()
    yield redis
    redis.close()
    await redis.wait_closed()

@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m

## Web app

@pytest.fixture
async def test_app():
    return Quart(__name__)

## Main classes of the reconciliation service

@pytest.fixture
def sitelink_fetcher(redis_client, http_session):
    return SitelinkFetcher(redis_client, http_session)

@pytest.fixture
def item_store(redis_client, http_session):
    return ItemStore(redis_client, http_session)

class ItemStoreStub(ItemStore):
    async def _fetch_items(self, qids):
        result = {}
        for qid in qids:
            datapath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'tests/entities', qid+'.json')
            try:
                with open(datapath, 'r') as f:
                    itemdata = json.load(f)
                    if itemdata:
                        result[qid] = itemdata
            except FileNotFoundError:
                fetch_result = (await super(ItemStoreStub, self)._fetch_items([qid]))
                actual_json = fetch_result.get(qid)
                with open(datapath, 'w') as f:
                    json.dump(actual_json, f)
                if actual_json:
                    result[qid] = actual_json
        return result

@pytest.fixture
def item_store_stub(redis_client, http_session):
    return ItemStoreStub(redis_client, http_session)

@pytest.fixture
def property_factory(item_store_stub):
    return PropertyFactory(item_store_stub)

@pytest.fixture
def type_matcher(redis_client, http_session):
    return TypeMatcher(redis_client, http_session)

class TypeMatcherStub(TypeMatcher):
    async def _fetch_children(self, qid):
        datapath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'tests/types', qid+'.json')
        try:
            with open(datapath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            fetched = await super(TypeMatcherStub, self)._fetch_children(qid)
            with open(datapath, 'w') as f:
                json.dump(fetched, f)
            return fetched

class PropertyFactoryStub(PropertyFactory):
    async def _fetch_unique_ids(self):
        return ['P214', 'P1566']

class EngineStub(ReconcileEngine):
    def __init__(self, redis_client, http_session):
        super(EngineStub, self).__init__(redis_client, http_session)
        self.item_store = ItemStoreStub(redis_client, http_session)
        self.pf = PropertyFactoryStub(self.item_store)
        self.type_matcher = TypeMatcherStub(redis_client, http_session)

    async def wikibase_string_search(self, query_string, num_results, default_language):
        key = '{}_{}_{}.json'.format(query_string.replace(' ', '_'), num_results, default_language)
        datapath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'tests/search', key)
        try:
            with open(datapath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            fetched = await super(EngineStub, self).wikibase_string_search(query_string, num_results, default_language)
            with open(datapath, 'w') as f:
                json.dump(fetched, f)
            return fetched

@pytest.fixture
def engine(redis_client, http_session, item_store_stub):
    engine = EngineStub(redis_client, http_session)
    return engine

@pytest.fixture
def suggest_engine(redis_client, http_session, item_store_stub):
    suggest = SuggestEngine(redis_client, http_session)
    suggest.store = item_store_stub
    return suggest
