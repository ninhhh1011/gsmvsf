"""Execute the six original integration test bodies WITHOUT changing them.

Boundary substitution is explicit: two in-process ASGI apps/managers, LuaKV
fixture instead of Redis, matching deliberately raises ENGINE_UNAVAILABLE.
This demonstrates assertion coverage, NOT real two-instance integration.
"""
import importlib.util
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlparse
import pytest
import audit_support as s

path=s.SNAPSHOT/'backend/tests/test_shared_state_integration.py'
spec=importlib.util.spec_from_file_location('exported_integration_tests',path)
original=importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
NAMES=[n for n in vars(original) if n.startswith('test_')]

@pytest.mark.asyncio
@pytest.mark.parametrize('name',NAMES)
async def test_original_test_body_with_matching_unavailable(name):
    e=s.Environment(); requests=[]
    saved_clock=s.api.datetime; saved_httpx=original.httpx; saved_redis=s.redis_stub.Redis
    async def no_matching(*a,**kw): raise s.api.MapMatchingEngineError('AUDIT: intentionally unavailable matching engine')
    s.api._call_map_match=no_matching
    s.api.datetime=datetime
    class RoutedClient:
        def __init__(self,*a,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def _request(self,method,url,payload=None):
            parsed=urlparse(url); instance=0 if parsed.port==8000 else 1
            driver=parsed.path.split('/')[-2]
            response=await e.request(instance,method,driver,payload)
            requests.append({'method':method,'instance':instance,'payload':payload,'response':s.as_json(response)})
            return response
        async def post(self,url,json=None,**kw): return await self._request('POST',url,json)
        async def get(self,url,**kw): return await self._request('GET',url)
        async def delete(self,url,**kw): return await self._request('DELETE',url)
    class SyncKVView:
        def __init__(self,*a,**kw): pass
        def get(self,key): return e.kv.values.get(key)
    original.httpx=SimpleNamespace(AsyncClient=RoutedClient)
    s.redis_stub.Redis=SyncKVView
    try:
        await getattr(original,name)(('http://127.0.0.1:8000','http://127.0.0.1:8001'))
    finally:
        s.write_evidence('original_body_'+name,{'boundary':'ASGI_INPROCESS_LUA_KV_FIXTURE; NOT LIVE REDIS OR TWO OS PROCESSES','matching':'intentionally ENGINE_UNAVAILABLE','test':name,'requests':requests})
        original.httpx=saved_httpx; s.redis_stub.Redis=saved_redis; s.api.datetime=saved_clock
        await e.close()
