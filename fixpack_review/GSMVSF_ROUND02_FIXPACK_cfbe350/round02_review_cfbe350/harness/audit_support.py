"""Audit-only harness. Does not modify exported application files.

Redis/GraphHopper are unavailable in this sandbox. This harness imports the
original handler, manager, repository, state and trigger modules. Their Lua
source is executed verbatim by the installed Lua 5.4 VM with JSON/GET/SET
fixtures. This is NOT a Redis/GraphHopper/full-stack integration test.
"""
from __future__ import annotations
import asyncio, ctypes as C, ctypes.util, fnmatch, hashlib, importlib, json, os, sys, types
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextvars import ContextVar

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / 'input'
SNAPSHOT = EXPORT / 'snapshot'
RESULTS = ROOT / 'results'
RESULTS.mkdir(exist_ok=True)
sys.path.insert(0, str(SNAPSHOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

class LuaKVFixture:
    """Execute repository-supplied Lua, with in-memory command/JSON fixtures.
    Deliberately exposes native Lua separately from mocked Redis commands.
    No network, persistence, TTL expiration, clustering or replication modeled.
    """
    NULL_SENTINEL = '__AUDIT_LUA_JSON_NULL_8640ff2__'
    def __init__(self):
        self.values = {}
        self.events = []
        self.eval_count = 0
        self.fail_eval = False
        self.fail_get = False
        self.fail_set = False
        self.fail_delete = False
        self.fail_ping = False
        self.callback_errors = []
        self.lib = C.CDLL(ctypes.util.find_library('lua5.4'))
        L = self.lib
        specs = {
          'luaL_newstate': ([], C.c_void_p),
          'luaL_openlibs': ([C.c_void_p], None),
          'lua_close': ([C.c_void_p], None),
          'luaL_loadstring': ([C.c_void_p, C.c_char_p], C.c_int),
          'lua_pcallk': ([C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_longlong,C.c_void_p], C.c_int),
          'lua_gettop': ([C.c_void_p], C.c_int),
          'lua_settop': ([C.c_void_p,C.c_int], None),
          'lua_type': ([C.c_void_p,C.c_int], C.c_int),
          'lua_tolstring': ([C.c_void_p,C.c_int,C.POINTER(C.c_size_t)], C.c_void_p),
          'lua_tonumberx': ([C.c_void_p,C.c_int,C.c_void_p], C.c_double),
          'lua_tointegerx': ([C.c_void_p,C.c_int,C.c_void_p], C.c_longlong),
          'lua_isinteger': ([C.c_void_p,C.c_int], C.c_int),
          'lua_toboolean': ([C.c_void_p,C.c_int], C.c_int),
          'lua_pushnil': ([C.c_void_p], None),
          'lua_pushboolean': ([C.c_void_p,C.c_int], None),
          'lua_pushinteger': ([C.c_void_p,C.c_longlong], None),
          'lua_pushnumber': ([C.c_void_p,C.c_double], None),
          'lua_pushlstring': ([C.c_void_p,C.c_char_p,C.c_size_t], C.c_void_p),
          'lua_createtable': ([C.c_void_p,C.c_int,C.c_int], None),
          'lua_rawseti': ([C.c_void_p,C.c_int,C.c_longlong], None),
          'lua_setfield': ([C.c_void_p,C.c_int,C.c_char_p], None),
          'lua_getfield': ([C.c_void_p,C.c_int,C.c_char_p], C.c_int),
          'lua_next': ([C.c_void_p,C.c_int], C.c_int),
          'lua_setglobal': ([C.c_void_p,C.c_char_p], None),
          'lua_getglobal': ([C.c_void_p,C.c_char_p], C.c_int),
          'lua_setmetatable': ([C.c_void_p,C.c_int], C.c_int),
          'lua_getmetatable': ([C.c_void_p,C.c_int], C.c_int),
        }
        for n,(args,ret) in specs.items():
            f=getattr(L,n); f.argtypes=args; f.restype=ret
        self.FUNC = C.CFUNCTYPE(C.c_int, C.c_void_p)
        L.lua_pushcclosure.argtypes=[C.c_void_p,self.FUNC,C.c_int]
        L.lua_pushcclosure.restype=None
        self.vm=L.luaL_newstate(); L.luaL_openlibs(self.vm)
        self.callbacks=[]
        for name,fn in [('audit_json_decode',self._decode),('audit_json_encode',self._encode),('audit_redis_call',self._redis_call)]:
            cb=self.FUNC(fn); self.callbacks.append(cb)
            L.lua_pushcclosure(self.vm,cb,0); L.lua_setglobal(self.vm,name.encode())
        self._execute('cjson={decode=audit_json_decode,encode=audit_json_encode}; redis={call=audit_redis_call}; os=nil; io=nil; package=nil; require=nil; dofile=nil; loadfile=nil; return true')

    def _text(self,S,i):
        n=C.c_size_t(); p=self.lib.lua_tolstring(S,i,C.byref(n))
        return C.string_at(p,n.value).decode('utf-8') if p else None
    def _push(self,S,obj):
        L=self.lib
        if obj is None:
            obj=self.NULL_SENTINEL
        if isinstance(obj,bool): L.lua_pushboolean(S,obj)
        elif isinstance(obj,int): L.lua_pushinteger(S,obj)
        elif isinstance(obj,float): L.lua_pushnumber(S,obj)
        elif isinstance(obj,str):
            raw=obj.encode(); L.lua_pushlstring(S,raw,len(raw))
        elif isinstance(obj,list):
            L.lua_createtable(S,len(obj),0)
            for i,v in enumerate(obj,1): self._push(S,v); L.lua_rawseti(S,-2,i)
            L.lua_createtable(S,0,1); L.lua_pushboolean(S,1); L.lua_setfield(S,-2,b'_audit_array'); L.lua_setmetatable(S,-2)
        elif isinstance(obj,dict):
            L.lua_createtable(S,0,len(obj))
            for k,v in obj.items(): self._push(S,v); L.lua_setfield(S,-2,str(k).encode())
        else: raise TypeError(type(obj))
    def _read(self,S,i):
        L=self.lib; i=i if i>0 else L.lua_gettop(S)+i+1; t=L.lua_type(S,i)
        if t==0: return None
        if t==1: return bool(L.lua_toboolean(S,i))
        if t==3: return L.lua_tointegerx(S,i,None) if L.lua_isinteger(S,i) else L.lua_tonumberx(S,i,None)
        if t==4:
            s=self._text(S,i); return None if s==self.NULL_SENTINEL else s
        if t==5:
            is_array=False
            if L.lua_getmetatable(S,i):
                L.lua_getfield(S,-1,b'_audit_array'); is_array=bool(L.lua_toboolean(S,-1)); L.lua_settop(S,-3)
            out={}; L.lua_pushnil(S)
            while L.lua_next(S,i):
                k=self._read(S,-2); v=self._read(S,-1); out[k]=v; L.lua_settop(S,-2)
            return [out[k] for k in sorted(out)] if is_array else out
        raise TypeError(f'Unexpected Lua type {t}')
    def _decode(self,S):
        try: self._push(S,json.loads(self._text(S,1))); return 1
        except Exception as e: self.callback_errors.append(repr(e)); self.lib.lua_pushnil(S); return 1
    def _encode(self,S):
        try: self._push(S,json.dumps(self._read(S,1),separators=(',',':'))); return 1
        except Exception as e: self.callback_errors.append(repr(e)); self.lib.lua_pushnil(S); return 1
    def _redis_call(self,S):
        try:
            args=[self._read(S,i) for i in range(1,self.lib.lua_gettop(S)+1)]
            cmd=args[0].upper(); self.events.append({'command':cmd,'key':args[1],'via':'Lua'})
            if cmd=='GET':
                raw=self.values.get(args[1])
                if raw is None: self.lib.lua_pushnil(S)
                else: self._push(S,raw)
            elif cmd=='SET':
                self.values[args[1]]=args[2]; self._push(S,'OK')
            else: raise ValueError(cmd)
            return 1
        except Exception as e: self.callback_errors.append(repr(e)); self.lib.lua_pushnil(S); return 1
    def _execute(self,script):
        L=self.lib; S=self.vm; L.lua_settop(S,0)
        status=L.luaL_loadstring(S,script.encode())
        if not status: status=L.lua_pcallk(S,0,1,0,0,None)
        if status: raise RuntimeError(self._text(S,-1))
        result=self._read(S,-1); L.lua_settop(S,0)
        if self.callback_errors: raise RuntimeError(self.callback_errors)
        return result
    async def eval(self,script,numkeys,*args):
        self.eval_count+=1
        if self.fail_eval: raise RuntimeError('audit-injected EVAL permission/error; GET/SET remain available')
        self._push(self.vm,list(args[:numkeys])); self.lib.lua_setglobal(self.vm,b'KEYS')
        self._push(self.vm,[str(x) for x in args[numkeys:]]); self.lib.lua_setglobal(self.vm,b'ARGV')
        self.last_script_sha256=hashlib.sha256(script.encode()).hexdigest()
        result = self._execute(script)
        # Redis RESP represents a top-level dense numeric Lua return table as a list.
        if isinstance(result, dict) and result and set(result) == set(range(1,len(result)+1)):
            result = [result[k] for k in range(1,len(result)+1)]
        self.events.append({'operation':'EVAL_RESULT','result':result,'script_sha256':self.last_script_sha256,'expected_version':args[-1] if len(args)==4 else None})
        return result
    async def ping(self):
        if self.fail_ping: raise ConnectionError('audit fixture ping failure')
        return True
    async def get(self,key):
        if self.fail_get: raise ConnectionError('audit fixture get failure')
        return self.values.get(key)
    async def set(self,key,value,ex=None):
        if self.fail_set: raise ConnectionError('audit fixture set failure')
        self.values[key]=value; self.events.append({'command':'SET','key':key,'via':'fallback/client'}); return True
    async def expire(self,key,ttl): return key in self.values
    async def delete(self,key):
        if self.fail_delete: raise ConnectionError('audit fixture delete failure')
        return int(self.values.pop(key,None) is not None)
    async def scan_iter(self,match='*',count=100):
        if self.fail_get: raise ConnectionError('audit fixture scan failure')
        for key in list(self.values):
            if fnmatch.fnmatch(key,match): yield key
    async def aclose(self): pass
    def close(self):
        if self.vm: self.lib.lua_close(self.vm); self.vm=None

# Import-only shims for packages unavailable in this sandbox.
# Actual application repository methods use LuaKVFixture via _client injection.
redis_stub=types.ModuleType('redis'); redis_stub.__path__=[]
redis_async=types.ModuleType('redis.asyncio'); redis_stub.asyncio=redis_async
redis_async.Redis=LuaKVFixture
redis_async.from_url=lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('Real redis-py unavailable; inject explicit fixture'))
redis_stub.Redis=LuaKVFixture
sys.modules.setdefault('redis',redis_stub); sys.modules.setdefault('redis.asyncio',redis_async)
psycopg=types.ModuleType('psycopg2'); psycopg.Error=type('AuditPsycopgError',(Exception,),{})
sys.modules.setdefault('psycopg2',psycopg)
map_provider=types.ModuleType('backend.app.api.v1.map_match')
map_provider.get_map_matching_service=lambda: (_ for _ in ()).throw(RuntimeError('GraphHopper provider missing from ZIP; use explicit matching fixture'))
sys.modules.setdefault(map_provider.__name__,map_provider)

from backend.app.api.v1 import realtime as api
from backend.app.services.realtime import driver_state_manager as manager_module
from backend.app.services.realtime import driver_state_repository as repo_module
from backend.app.services.realtime import state as state_module
from fastapi import FastAPI
import httpx

active_manager=ContextVar('audit_manager')
api.get_driver_state_manager=lambda: active_manager.get()

FIXED_NOW=datetime(2026,9,25,3,32,30)
class FixedDatetime(datetime):
    @classmethod
    def utcnow(cls): return FIXED_NOW
api.datetime=FixedDatetime

async def matched_fixture(observations,vehicle_category=None,vehicle_id=None):
    pts=[types.SimpleNamespace(observation_id=o.observation_id,matched=True,
           matched_latitude=o.latitude+0.00001,matched_longitude=o.longitude+0.00001,
           road_segment_id='audit_segment',osm_way_id=123,direction='FORWARD',confidence=0.99)
         for o in observations]
    return types.SimpleNamespace(observations=pts,overall_confidence=.99,trace_geometry='fixture-not-a-real-route'),1.0

class Environment:
    def __init__(self):
        self.kv=LuaKVFixture()
        self.repos=[]; self.managers=[]; self.apps=[]; self.clients=[]
        for _ in range(2):
            r=repo_module.RedisDriverStateRepository(redis_url='redis://audit-fixture.invalid/0'); r._client=self.kv
            m=manager_module.DriverStateManager(repository=r)
            app=FastAPI(); app.include_router(api.router,prefix='/api/v1')
            self.repos.append(r); self.managers.append(m); self.apps.append(app)
            self.clients.append(httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://audit-inprocess'))
        api._call_map_match=matched_fixture
    async def request(self,instance,method,driver,payload=None):
        token=active_manager.set(self.managers[instance])
        try:
            return await self.clients[instance].request(method,f'/api/v1/drivers/{driver}/location',json=payload)
        finally: active_manager.reset(token)
    async def direct(self,instance,func,*args):
        token=active_manager.set(self.managers[instance])
        try: return await func(*args)
        finally: active_manager.reset(token)
    async def snapshot(self,driver):
        s=await self.repos[0].get(driver)
        return json.loads(s.to_json()) if s else None
    async def close(self):
        for c in self.clients: await c.aclose()
        self.kv.close()

def payload(obs_id='O1',i=0,seconds=0,**updates):
    t=datetime(2026,9,1,7,0,tzinfo=timezone.utc)+timedelta(seconds=seconds)
    d=dict(observation_id=obs_id,vehicle_category='EV_CAR',timestamp=t.isoformat(),
           latitude=21.028+i*.001,longitude=105.854+i*.001,speed_kmh=30,heading_deg=90)
    d.update(updates); return d

def as_json(response):
    try: body=response.json()
    except ValueError: body=response.text
    return {'http_status':response.status_code,'body':body}

def write_evidence(name,result):
    (RESULTS/f'{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

async def seed_match(env,driver):
    out=[]
    for i in range(3): out.append(await env.request(0,'POST',driver,payload(f'O{i+1}',i=i,seconds=i)))
    assert out[-1].status_code==200 and out[-1].json()['status']=='MATCHED',as_json(out[-1])
    return out
