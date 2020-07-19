import time

class Monitoring(object):
    def __init__(self, redis_client):
        self.req_rate_bucket_durations = [24*3600,3600,60]
        self.r = redis_client

    def redis_bucket(self, duration):
        return ('openrefine_wikidata:monitoring:%d:%d' %
                (duration,time.time() // duration))

    async def log_request(self, queries, processing_time):
        for duration in self.req_rate_bucket_durations:
            key = self.redis_bucket(duration)
            await self.r.incr(key+':req_count')
            await self.r.expire(key+':req_count', duration)
            await self.r.incrby(key+':query_count', queries)
            await self.r.expire(key+':query_count', duration)
            await self.r.incrbyfloat(key+':processing_time', processing_time)
            await self.r.expire(key+':processing_time', duration)

    async def get_rates(self):
        rates = []
        for duration in self.req_rate_bucket_durations:
            key = self.redis_bucket(duration)
            req_count = float((await self.r.get(key+':req_count')) or 0)
            query_count = float((await self.r.get(key+':query_count')) or 0)
            processing_time = float((await self.r.get(key+':processing_time')) or 0)
            curtime = time.time()
            time_since_bucket_started = curtime - duration*(curtime // duration)
            rates.append({
                'request_rate': req_count / time_since_bucket_started,
                'query_rate': query_count / time_since_bucket_started,
                'processing_time_per_query': processing_time / query_count if query_count > 0 else None,
                'measure_duration': int(time_since_bucket_started),
                'measure_duration_target': duration,
            })
        return rates

