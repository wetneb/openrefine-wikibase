import pytest
import re

pytestmark = pytest.mark.asyncio

async def test_label(item_store, mock_aioresponse):
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids=Q3918&props=aliases%7Clabels%7Cdescriptions%7Cclaims%7Csitelinks',
        payload={
        "entities": {
        "Q3918": {
            "type": "item",
            "id": "Q3918",
            "labels": {
                "en": {
                    "language": "en",
                    "value": "university"
                }}
        }}})
    label = await item_store.get_label('Q3918', 'en')
    assert label == 'university'

async def test_label_fallback(item_store, mock_aioresponse):
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids=Q3578062&props=aliases%7Clabels%7Cdescriptions%7Cclaims%7Csitelinks',
        payload={
        "entities": {
        "Q3578062": {
            "type": "item",
            "id": "Q3578062",
            "labels": {
                "es": {
                    "language": "es",
                    "value": "Escola Nacional d'Administració"
                }}
        }}})
    # this item does not have a catalan label, so we fall back on another one
    label = await item_store.get_label('Q3578062', 'ca')
    assert label == "Escola Nacional d'Administració"

async def test_preferred_rank(item_store_stub):
    """
    The first value in the list should be the preferred rank,
    if any. This item (Australia) contains various currencies
    that have been in use before, and Australian Dollar
    is the preferred one.
    """
    item = await item_store_stub.get_item('Q408')
    assert item['P38'][0]['mainsnak']['datavalue']['value']['id'] == 'Q259502'


