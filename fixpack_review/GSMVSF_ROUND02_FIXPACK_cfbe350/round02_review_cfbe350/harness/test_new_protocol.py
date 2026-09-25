"""Additional checks for the changes introduced after 8640ff2.
Tests assert desired contracts; known counterexamples fail, not pass-as-bug tests.
Boundary: original Python source/Lua 5.4 VM; ASGI/KV/matching fixtures.
"""
import asyncio
from datetime import datetime,timezone,timedelta
from copy import deepcopy
import pytest
from audit_support import *

@pytest.fixture
async def env():
    e=Environment()
    yield e
    await e.close()

@pytest.mark.asyncio
async def test_repository_cas_rejects_stale_expected_version(env):
    repo=env.repos[0]
    original=repo_module.DriverTraceStateSnapshot(driver_id='direct-cas',total_observations_received=1)
    first=await repo.save_with_expected_version(original,0)
    a=await repo.get('direct-cas'); b=await repo.get('direct-cas')
    a.total_observations_received=2
    ok=await repo.save_with_expected_version(a,a.version)
    b.total_observations_received=777
    rejected=await repo.save_with_expected_version(b,b.version)
    final=await env.snapshot('direct-cas')
    write_evidence('positive_cas_primitive',{'initial':first,'first_update':ok,'stale_update':rejected,'final_state':final,'lua_events':env.kv.events})
    assert first==(True,1) and ok==(True,2) and rejected==(False,2)
    assert final['total_observations_received']==2

@pytest.mark.asyncio
async def test_sequential_reset_increases_generation_and_clears_state(env):
    await env.request(0,'POST','reset-sequential',payload('O1'))
    before=await env.snapshot('reset-sequential')
    r=await env.request(1,'DELETE','reset-sequential')
    after=await env.snapshot('reset-sequential')
    fresh=await env.request(0,'POST','reset-sequential',payload('NEW',seconds=1))
    final=await env.snapshot('reset-sequential')
    write_evidence('positive_reset_generation',{'before':before,'reset':as_json(r),'after':after,'new_post':as_json(fresh),'final':final})
    assert after['generation']>before['generation'] and after['total_observations_received']==0
    assert final['generation']==after['generation']
    assert [o['observation_id'] for o in final['observations']]==['NEW']

@pytest.mark.asyncio
async def test_manager_must_not_save_stale_payload_under_fresh_version(env):
    await env.request(0,'POST','manager-stale',payload('O1'))
    stale=await env.managers[0].get_or_create('manager-stale')
    await env.request(1,'POST','manager-stale',payload('O2',seconds=1))
    before=await env.snapshot('manager-stale')
    error=None
    try:
        await env.managers[0].save_with_retry(stale)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    after=await env.snapshot('manager-stale')
    write_evidence('manager_fresh_version_stale_payload',{'stale_state_ids':[o.observation_id for o in stale.observations],'before':before,'after':after,'error':error,'lua_events':env.kv.events})
    assert {o['observation_id'] for o in after['observations']}=={'O1','O2'}, 'Manager fetched new version but committed the caller\'s old payload'

@pytest.mark.asyncio
async def test_final_matched_write_failure_must_not_ack_uncommitted_match(env):
    for i in range(2): await env.request(0,'POST','final-outage',payload(f'O{i+1}',i=i,seconds=i))
    async def matching_then_write_failure(*a,**kw):
        result=await matched_fixture(*a,**kw)
        env.kv.fail_eval=True
        return result
    api._call_map_match=matching_then_write_failure
    post=await env.request(0,'POST','final-outage',payload('O3',i=2,seconds=2))
    got=await env.request(1,'GET','final-outage')
    write_evidence('final_matched_write_failure',{'fault':'EVAL failure starts only after matching; initial observation write already succeeded','post':as_json(post),'get':as_json(got),'stored':await env.snapshot('final-outage')})
    assert post.status_code==503, 'Final persistence failed but POST still ACKed MATCHED'

@pytest.mark.asyncio
async def test_no_trigger_final_write_failure_must_be_visible(env):
    await seed_match(env,'no-trigger-outage')
    original=env.managers[0].save_with_retry
    writes=0
    async def save(state,*args,**kwargs):
        nonlocal writes
        writes+=1
        if writes==2: env.kv.fail_eval=True
        return await original(state,*args,**kwargs)
    env.managers[0].save_with_retry=save
    post=await env.request(0,'POST','no-trigger-outage',payload('O4',i=2,seconds=3))
    get=await env.request(1,'GET','no-trigger-outage')
    write_evidence('final_no_trigger_write_failure',{'post':as_json(post),'get':as_json(get),'write_calls':writes})
    assert post.status_code==503, 'GPS_ACCEPTED returned although final status write failed'

@pytest.mark.asyncio
async def test_same_id_different_payload_must_be_rejected(env):
    p=payload('SAME_ID')
    first=await env.request(0,'POST','dup-conflict',p)
    changed=dict(p,latitude=22.5)
    second=await env.request(1,'POST','dup-conflict',changed)
    state=await env.snapshot('dup-conflict')
    write_evidence('duplicate_payload_conflict',{'first':as_json(first),'conflicting_request':changed,'second':as_json(second),'stored':state})
    assert second.status_code in (400,409,422) or second.json().get('status')=='DUPLICATE_CONFLICT', 'Conflicting payload silently treated as the same accepted observation'
    assert state['observations'][0]['latitude']==p['latitude']

@pytest.mark.asyncio
async def test_utc_stale_check_must_compare_instants_not_wall_clock(env):
    first=await env.request(0,'POST','utc-stale',payload('NEW',timestamp='2026-09-01T07:00:00Z'))
    stale=await env.request(1,'POST','utc-stale',payload('OLD',timestamp='2026-09-01T13:59:00+07:00'))
    state=await env.snapshot('utc-stale')
    write_evidence('timezone_stale_regression',{'first':as_json(first),'older_instant':as_json(stale),'state':state})
    assert stale.json()['status']=='STALE_OBSERVATION', '06:59Z accepted after 07:00Z because +07 wall-clock was compared'
    assert state['total_observations_received']==1

@pytest.mark.asyncio
async def test_utc_newer_negative_offset_is_not_stale(env):
    first=await env.request(0,'POST','utc-newer',payload('OLD',timestamp='2026-09-01T07:00:00Z'))
    newer=await env.request(1,'POST','utc-newer',payload('NEW',timestamp='2026-09-01T00:01:00-07:00'))
    state=await env.snapshot('utc-newer')
    write_evidence('timezone_newer_rejected',{'first':as_json(first),'newer_instant':as_json(newer),'state':state})
    assert newer.json()['status']!='STALE_OBSERVATION', '07:01Z rejected after 07:00Z because -07 wall-clock was compared'
    assert state['total_observations_received']==2

def test_ensure_utc_helper_itself_converts_offsets():
    a=state_module.ensure_utc(datetime.fromisoformat('2026-09-01T07:00:00+00:00'))
    b=state_module.ensure_utc(datetime.fromisoformat('2026-09-01T14:00:00+07:00'))
    write_evidence('positive_utc_helper',{'utc':a,'plus7':b})
    assert a==b==datetime(2026,9,1,7,0)

@pytest.mark.asyncio
async def test_reset_failure_must_not_destroy_fence_and_ack_success(env):
    await env.request(0,'POST','reset-failure',payload('O1'))
    before=await env.snapshot('reset-failure')
    env.kv.fail_eval=True
    delete=await env.request(1,'DELETE','reset-failure')
    after=await env.snapshot('reset-failure')
    write_evidence('reset_unchecked_delete_fallback',{'before':before,'reset':as_json(delete),'after':after,'fault':'EVAL fails; GET/DELETE succeed'})
    assert delete.status_code==503, 'Could not persist reset generation, fell back to DELETE and reported success'
    assert after is not None, 'Generation fence was destroyed by fallback delete'

@pytest.mark.asyncio
async def test_stationary_final_state_persists_without_fault(env):
    await seed_match(env,'stationary')
    for i in range(4,7):
        post=await env.request(0,'POST','stationary',payload(f'O{i}',i=2,seconds=i-1))
    get=await env.request(1,'GET','stationary')
    write_evidence('positive_stationary_persistence',{'post':as_json(post),'get':as_json(get)})
    assert post.json()['trigger_reason']=='STATIONARY_SUPPRESSED'
    assert get.json()['trigger_reason']==post.json()['trigger_reason']
    assert post.json()['status']==get.json()['status']=='GPS_ACCEPTED'

@pytest.mark.asyncio
async def test_concurrent_identical_duplicate_before_match_is_counted_once(env):
    p=payload('IDENTICAL')
    responses=await asyncio.gather(env.request(0,'POST','dup-concurrent',p),env.request(1,'POST','dup-concurrent',p))
    state=await env.snapshot('dup-concurrent')
    write_evidence('positive_duplicate_concurrent_observed',{'responses':[as_json(r) for r in responses],'state':state,'note':'No deliberate barrier here; narrow positive control, not proof of all schedules'})
    assert state['total_observations_received']==1
    assert [o['observation_id'] for o in state['observations']]==['IDENTICAL']
