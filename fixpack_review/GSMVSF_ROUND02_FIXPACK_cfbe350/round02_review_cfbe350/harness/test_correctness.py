"""Expected-behavior tests against unmodified exported source.
Known incorrect behaviors FAIL rather than being recast as passing bug tests.
Infrastructure boundary: Lua 5.4 + KV/JSON fixture + matching fixture + ASGI.
"""
import asyncio
from datetime import datetime, timezone
import json
import pytest
from audit_support import *

@pytest.fixture
async def env():
    e=Environment()
    yield e
    await e.close()

@pytest.mark.asyncio
async def test_positive_matched_final_state_is_persisted(env):
    responses=await seed_match(env,'positive-match')
    got=await env.request(1,'GET','positive-match')
    p=responses[-1].json(); g=got.json()
    write_evidence('positive_match',{'post':as_json(responses[-1]),'get':as_json(got),'lua_evaluations':env.kv.eval_count})
    assert p['status']==g['status']=='MATCHED'
    assert p['last_match_time']==g['last_match_time'] and g['last_match_time']
    assert p['matched_position']['latitude']==g['matched_position']['latitude']
    assert p['total_match_calls']==g['total_match_calls']==1

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['NO_MATCH','ENGINE_UNAVAILABLE'])
async def test_positive_match_failure_status_is_persisted(env,mode):
    async def failing_match(*a,**kw):
        if mode=='NO_MATCH': return None,1.0
        raise api.MapMatchingEngineError('audit simulated matching outage')
    api._call_map_match=failing_match
    for i in range(3): post=await env.request(0,'POST',mode,payload(f'O{i+1}',i=i,seconds=i))
    get=await env.request(1,'GET',mode)
    write_evidence('positive_'+mode.lower(),{'post':as_json(post),'get':as_json(get)})
    assert post.status_code==get.status_code==200
    assert post.json()['status']==get.json()['status']==mode

@pytest.mark.asyncio
async def test_positive_older_observation_is_rejected_without_count_change(env):
    r=await env.request(0,'POST','stale',payload('new',seconds=3))
    old=await env.request(1,'POST','stale',payload('old',seconds=2))
    get=await env.request(0,'GET','stale')
    write_evidence('positive_stale',{'first':as_json(r),'stale':as_json(old),'get':as_json(get)})
    assert old.json()['status']=='STALE_OBSERVATION'
    assert get.json()['total_observations']==1

@pytest.mark.asyncio
async def test_positive_redis_health_failure_is_503(env):
    env.kv.fail_ping=True
    response=await env.request(0,'POST','read-outage',payload())
    write_evidence('positive_read_unavailable',as_json(response))
    assert response.status_code==503
    assert not env.kv.values

@pytest.mark.asyncio
async def test_positive_sequential_versions_actually_increase(env):
    await env.request(0,'POST','versions',payload('O1'))
    one=await env.snapshot('versions')
    await env.request(1,'POST','versions',payload('O2',seconds=1))
    two=await env.snapshot('versions')
    write_evidence('positive_versions',{'first_version':one['version'],'second_version':two['version']})
    assert two['version']>one['version']

@pytest.mark.asyncio
async def test_same_observation_retry_must_be_idempotent(env):
    body=payload('EXACT_SAME_ID')
    first=await env.request(0,'POST','duplicate',body)
    second=await env.request(1,'POST','duplicate',body)
    state=await env.snapshot('duplicate')
    ids=[o['observation_id'] for o in state['observations']]
    write_evidence('duplicate',{'first':as_json(first),'retry':as_json(second),'stored_ids':ids,'state':state})
    assert second.json()['total_observations']==first.json()['total_observations']==1, f'counts: first={first.json()["total_observations"]}, retry={second.json()["total_observations"]}; stored IDs={ids}'
    assert ids==['EXACT_SAME_ID']

@pytest.mark.asyncio
async def test_concurrent_http_writers_must_preserve_acked_observation_ids(env):
    await env.request(0,'POST','race',payload('O0'))
    both_read=asyncio.Event(); arrived=0; reads=[]
    for i,m in enumerate(env.managers):
        original=m.get_or_create
        async def barrier_read(driver,original=original,i=i):
            nonlocal arrived
            state=await original(driver)
            reads.append({'instance':i,'ids':[o.observation_id for o in state.observations]})
            arrived+=1
            if arrived>=2: both_read.set()
            await asyncio.wait_for(both_read.wait(),2)
            return state
        m.get_or_create=barrier_read
    ra,rb=await asyncio.gather(env.request(0,'POST','race',payload('OA',i=1,seconds=1)),env.request(1,'POST','race',payload('OB',i=2,seconds=2)))
    state=await env.snapshot('race'); ids=[o['observation_id'] for o in state['observations']]
    write_evidence('concurrent_lost_update',{'controlled_initial_reads':reads,'response_a':as_json(ra),'response_b':as_json(rb),'stored_ids':ids,'state':state,'lua_evaluations':env.kv.eval_count})
    # A correct retry may reject an older event as STALE_OBSERVATION.
    # Count only responses that actually acknowledge acceptance, not every HTTP 200.
    accepted_statuses={'WARMING_UP','GPS_ACCEPTED','MATCHED','PARTIAL_MATCH','NO_MATCH','ENGINE_UNAVAILABLE','GAP_RESET'}
    accepted={name for name,response in [('OA',ra),('OB',rb)]
              if response.status_code==200 and response.json().get('status') in accepted_statuses}
    assert accepted, 'Healthy two-writer scenario must accept at least one new event'
    assert {'O0'} | accepted <= set(ids), f'Lost ACKed IDs={ ({"O0"}|accepted)-set(ids) }; stored={ids}, version={state["version"]}'
    assert len(ids)==len(set(ids)), 'Duplicate IDs in persisted observations'

@pytest.mark.asyncio
async def test_pending_match_must_not_resurrect_reset_state(env):
    for i in range(2): await env.request(0,'POST','reset-race',payload(f'O{i+1}',i=i,seconds=i))
    started=asyncio.Event(); release=asyncio.Event(); events=[]
    async def delayed(*args,**kw):
        events.append('old_match_started'); started.set()
        await asyncio.wait_for(release.wait(),3)
        events.append('old_match_released'); return await matched_fixture(*args,**kw)
    api._call_map_match=delayed
    pending=asyncio.create_task(env.request(0,'POST','reset-race',payload('O3',i=2,seconds=2)))
    try:
        await asyncio.wait_for(started.wait(),3)
        deleted=await env.request(1,'DELETE','reset-race'); events.append('delete_completed')
        immediately=await env.snapshot('reset-race')
        release.set(); final_post=await asyncio.wait_for(pending,3); events.append('old_post_completed')
        state=await env.snapshot('reset-race'); get=await env.request(1,'GET','reset-race')
        write_evidence('reset_resurrection',{'timeline':events,'delete':as_json(deleted),'state_immediately_after_delete':immediately,'old_post':as_json(final_post),'final_get':as_json(get),'final_state':state})
        assert get.json()['buffered_points']==0, f'Reset succeeded, then pending request recreated {get.json()["buffered_points"]} old observations'
    finally:
        release.set()
        if not pending.done(): pending.cancel(); await asyncio.gather(pending,return_exceptions=True)

@pytest.mark.asyncio
async def test_older_match_must_not_overwrite_newer_acked_state(env):
    for i in range(2): await env.request(0,'POST','late-match',payload(f'O{i+1}',i=i,seconds=i))
    started=asyncio.Event(); release=asyncio.Event()
    async def delayed(observations,*args,**kw):
        if observations[-1].observation_id=='O3':
            started.set(); await asyncio.wait_for(release.wait(),3)
        return await matched_fixture(observations,*args,**kw)
    api._call_map_match=delayed
    pending=asyncio.create_task(env.request(0,'POST','late-match',payload('O3',i=2,seconds=2)))
    try:
        await asyncio.wait_for(started.wait(),3)
        newer=await env.request(1,'POST','late-match',payload('O4',i=3,seconds=3))
        before=await env.snapshot('late-match')
        release.set(); older=await asyncio.wait_for(pending,3)
        after=await env.snapshot('late-match')
        write_evidence('late_match_overwrite',{'newer_post':as_json(newer),'state_after_newer_ack':before,'older_post_after_release':as_json(older),'final_state':after})
        ids=[o['observation_id'] for o in after['observations']]
        assert 'O4' in ids, f'Newer O4 acknowledged as MATCHED then erased; final IDs={ids}, final time={after["last_observation_timestamp"]}'
    finally:
        release.set()
        if not pending.done(): pending.cancel(); await asyncio.gather(pending,return_exceptions=True)

@pytest.mark.asyncio
async def test_no_trigger_final_status_must_be_persisted(env):
    await seed_match(env,'no-trigger')
    body=payload('O4',i=2,seconds=3)
    post=await env.request(0,'POST','no-trigger',body)
    get=await env.request(1,'GET','no-trigger')
    write_evidence('no_trigger_persistence',{'post':as_json(post),'get':as_json(get),'state':await env.snapshot('no-trigger')})
    assert post.json()['status']==get.json()['status'], f'POST={post.json()["status"]}, GET={get.json()["status"]}'
    assert post.json()['trigger_reason']==get.json()['trigger_reason']

@pytest.mark.asyncio
async def test_gap_warmup_must_not_leave_matched_status_without_match(env):
    await seed_match(env,'gap')
    post=await env.request(0,'POST','gap',payload('AFTER_GAP',i=3,seconds=75))
    get=await env.request(1,'GET','gap')
    write_evidence('gap_status',{'post':as_json(post),'get':as_json(get),'state':await env.snapshot('gap')})
    assert post.json()['status']==get.json()['status'], f'POST={post.json()["status"]}, GET={get.json()["status"]}, matched_position={get.json()["matched_position"]}'

@pytest.mark.asyncio
async def test_equal_instants_utc_and_plus7_must_have_same_validation(env):
    utc=payload('SAME_INSTANT',timestamp='2026-09-25T03:31:00Z')
    plus7=payload('SAME_INSTANT',timestamp='2026-09-25T10:31:00+07:00')
    a=await env.request(0,'POST','utc-equivalence',utc)
    b=await env.request(1,'POST','offset-equivalence',plus7)
    write_evidence('timezone_equivalence',{'clock_utc':FIXED_NOW.isoformat()+'Z','utc_request':utc,'offset_request':plus7,'utc_response':as_json(a),'offset_response':as_json(b)})
    assert a.status_code==b.status_code==200, f'Equal instant: Z returned {a.status_code}, +07 returned {b.status_code}: {b.text}'

@pytest.mark.asyncio
async def test_eval_failure_must_not_silently_overwrite_stale_payload(env):
    await env.request(0,'POST','lua-fallback',payload('O1'))
    stale=await env.repos[0].get('lua-fallback')
    await env.request(1,'POST','lua-fallback',payload('O2',seconds=1))
    before=await env.snapshot('lua-fallback')
    env.kv.fail_eval=True
    error=None; save_ok=None
    try:
        save_ok=await env.repos[0].save(stale)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    after=await env.snapshot('lua-fallback')
    write_evidence('lua_fallback',{'injected_failure':'EVAL fails while GET/SET remain usable','before':before,'save_returned':save_ok,'error':error,'after':after})
    assert error is not None, 'EVAL failure must propagate, not report a successful save'
    assert after==before, 'EVAL failure must not invoke an unchecked SET'

@pytest.mark.asyncio
async def test_initial_write_outage_must_use_503_not_unhandled_500(env):
    env.kv.fail_eval=True; env.kv.fail_set=True
    response=await env.request(0,'POST','write-outage',payload())
    write_evidence('write_outage',{'fixture':'ping and get work; EVAL and SET fail','response':as_json(response)})
    assert response.status_code==503, f'Unhandled persistence error returned {response.status_code}: {response.text}'


def test_stale_test_timestamp_construction_must_work_at_hour_boundary():
    # Execute the actual timestamp assignment AST from the exported test, not an old expression.
    import ast
    path=SNAPSHOT/'backend/tests/test_shared_state_integration.py'
    tree=ast.parse(path.read_text())
    f=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='test_stale_observation_rejected')
    statement=next(n for n in ast.walk(f) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='stale_ts' for t in n.targets))
    now=datetime(2026,9,25,10,0,5,tzinfo=timezone.utc)
    scope={'now':now,'timedelta':timedelta}
    exec(compile(ast.Module(body=[statement],type_ignores=[]),str(path),'exec'),scope)
    actual=scope['stale_ts']
    parsed=datetime.fromisoformat(actual) if isinstance(actual,str) else actual
    write_evidence('stale_test_minute_zero',{'expression':ast.unparse(statement),'now':now.isoformat(),'result':actual})
    assert parsed==now-timedelta(minutes=1)
