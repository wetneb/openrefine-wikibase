import pytest

from wdreconcile.monitoring import Monitoring

pytestmark = pytest.mark.asyncio

async def test_resolve_redirects_for_titles(redis_client):
    monitoring = Monitoring(redis_client)

    await monitoring.log_request(10, 5.4)
    await monitoring.log_request(10, 5.3)
    await monitoring.log_request(10, 5.2)

    rates = await monitoring.get_rates()

    avg_time = rates[2]['processing_time_per_query']
    assert avg_time > 0.52 and avg_time < 0.54

