# Source evidence — snapshot cfbe350

HEAD khai báo: `cfbe350eea862cca734fc28b334b3da63ec732bc`. Đường dẫn dưới đây nằm trong `input/snapshot/`. Số dòng giữ theo source export; không chỉnh source.

## S1. CAS primitive có điều kiện, EVAL không còn fallback SET
`backend/app/services/realtime/driver_state_repository.py:309–440`

```text
0309: 
0310:     def _key(self, driver_id: str) -> str:
0311:         return f"{self.KEY_PREFIX}{driver_id}"
0312: 
0313:     async def get(self, driver_id: str) -> Optional[DriverTraceStateSnapshot]:
0314:         client = await self._get_client()
0315:         raw = await client.get(self._key(driver_id))
0316:         if raw is None:
0317:             return None
0318: 
0319:         # Refresh TTL on access
0320:         await client.expire(self._key(driver_id), self._driver_state_ttl)
0321: 
0322:         return DriverTraceStateSnapshot.from_json(raw)
0323: 
0324:     async def save(self, snapshot: DriverTraceStateSnapshot) -> bool:
0325:         client = await self._get_client()
0326:         key = self._key(snapshot.driver_id)
0327: 
0328:         # Use atomic Lua script for compare-and-swap to prevent lost updates.
0329:         # The script reads the current version, increments it atomically, and saves.
0330:         # This prevents two writers from both succeeding with the same version.
0331:         lua_script = """
0332:         local key = KEYS[1]
0333:         local new_value = ARGV[1]
0334:         local ttl = tonumber(ARGV[2])
0335: 
0336:         local current = redis.call('GET', key)
0337:         local new_version = 1
0338: 
0339:         if current then
0340:             local current_snapshot = cjson.decode(current)
0341:             local current_version = current_snapshot.version or 0
0342:             new_version = current_version + 1
0343:         end
0344: 
0345:         -- Update version in the snapshot
0346:         local updated = cjson.decode(new_value)
0347:         updated.version = new_version
0348: 
0349:         -- Save with TTL
0350:         redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
0351:         return new_version
0352:         """
0353: 
0354:         try:
0355:             new_version = await client.eval(
0356:                 lua_script,
0357:                 1,
0358:                 key,
0359:                 snapshot.to_json(),
0360:                 self._driver_state_ttl,
0361:             )
0362:             return new_version is not None
0363:         except Exception as e:
0364:             # CRITICAL: Do NOT fallback to unchecked SET - this would bypass
0365:             # the atomic version increment and potentially cause lost updates.
0366:             # If Lua script fails, the save must fail so the caller can retry.
0367:             logger.error(f"Redis Lua script failed, save aborted: {e}")
0368:             raise
0369: 
0370:     async def save_with_expected_version(
0371:         self, snapshot: DriverTraceStateSnapshot, expected_version: int
0372:     ) -> tuple[bool, int]:
0373:         """
0374:         Conditional save using CAS (Compare-And-Swap).
0375: 
0376:         Only saves if the current version in Redis matches expected_version.
0377:         This prevents lost updates when two requests try to update simultaneously.
0378: 
0379:         Returns:
0380:             (success, actual_version): success=True if saved, actual_version is current version
0381:         """
0382:         client = await self._get_client()
0383:         key = self._key(snapshot.driver_id)
0384: 
0385:         # Lua script for atomic CAS
0386:         lua_script = """
0387:         local key = KEYS[1]
0388:         local new_value = ARGV[1]
0389:         local ttl = tonumber(ARGV[2])
0390:         local expected_version = tonumber(ARGV[3])
0391: 
0392:         local current = redis.call('GET', key)
0393: 
0394:         if current then
0395:             local current_snapshot = cjson.decode(current)
0396:             local current_version = current_snapshot.version or 0
0397: 
0398:             -- Check if version matches
0399:             if current_version ~= expected_version then
0400:                 -- Conflict: return current version
0401:                 return {0, current_version}
0402:             end
0403: 
0404:             -- Version matches, save with incremented version
0405:             local updated = cjson.decode(new_value)
0406:             updated.version = current_version + 1
0407:             redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
0408:             return {1, current_version + 1}
0409:         else
0410:             -- No existing state, this is a new driver
0411:             -- Only save if expected_version is 0 (meaning no state existed)
0412:             if expected_version ~= 0 then
0413:                 return {0, 0}
0414:             end
0415: 
0416:             local updated = cjson.decode(new_value)
0417:             updated.version = 1
0418:             redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
0419:             return {1, 1}
0420:         end
0421:         """
0422: 
0423:         try:
0424:             result = await client.eval(
0425:                 lua_script,
0426:                 1,
0427:                 key,
0428:                 snapshot.to_json(),
0429:                 self._driver_state_ttl,
0430:                 expected_version,
0431:             )
0432:             success = bool(result[0])
0433:             actual_version = int(result[1])
0434:             return success, actual_version
0435:         except Exception as e:
0436:             logger.error(f"Redis CAS failed: {e}")
0437:             raise
0438: 
0439:     async def delete(self, driver_id: str) -> bool:
0440:         client = await self._get_client()
```

## S2. Manager đọc version mới rồi ghi nguyên payload cũ
`backend/app/services/realtime/driver_state_manager.py:36–63`

```text
0036: def snapshot_to_trace_state(snapshot: DriverTraceStateSnapshot) -> DriverTraceState:
0037:     """
0038:     Convert a Redis snapshot to a DriverTraceState object.
0039: 
0040:     This reconstructs the full runtime state including the observations deque.
0041:     """
0042:     state = DriverTraceState(driver_id=snapshot.driver_id)
0043:     state.observations = snapshot.to_observations_deque()
0044:     state.seen_observation_ids = snapshot.to_seen_ids_set()
0045:     state.movement_since_match = snapshot.movement_since_match
0046:     state.observations_since_match = snapshot.observations_since_match
0047:     state.consecutive_stationary = snapshot.consecutive_stationary
0048:     state.total_observations_received = snapshot.total_observations_received
0049:     state.total_match_calls = snapshot.total_match_calls
0050:     state.last_trigger_reason = snapshot.last_trigger_reason
0051:     state.last_match_latency_ms = snapshot.last_match_latency_ms
0052:     state.current_status = snapshot.current_status
0053:     state.generation = getattr(snapshot, 'generation', 1)  # Default to 1 for old snapshots
0054: 
0055:     if snapshot.last_match_time:
0056:         state.last_match_time = datetime.fromisoformat(snapshot.last_match_time)
0057: 
0058:     state.last_matched_state = snapshot.to_matched_state()
0059: 
0060:     if snapshot.last_observation_timestamp:
0061:         state.last_observation_timestamp = datetime.fromisoformat(snapshot.last_observation_timestamp)
0062: 
0063:     return state
```

## S3. save_with_retry và đường update_with_cas khác biệt
`backend/app/services/realtime/driver_state_manager.py:266–433`

```text
0266:     async def save_with_retry(self, state: DriverTraceState, max_retries: int = 3) -> None:
0267:         """
0268:         Persist driver state with CAS retry.
0269: 
0270:         Uses Compare-And-Swap to prevent lost updates:
0271:         1. Read current state and version
0272:         2. Attempt conditional save with expected version
0273:         3. If conflict, retry from step 1
0274: 
0275:         In production (Redis configured):
0276:         - Uses CAS to prevent lost updates
0277:         - Retries on conflict (max_retries times)
0278:         - Raises after max_retries if still conflicting
0279: 
0280:         In local mode (InMemory):
0281:         - Simple save without retry
0282: 
0283:         Raises:
0284:             DriverStateUnavailableError: When Redis is required but unavailable or after max retries
0285:         """
0286:         repo = self._get_repo()
0287: 
0288:         if repo is None:
0289:             return
0290: 
0291:         if isinstance(repo, InMemoryDriverStateRepository):
0292:             await repo.save_local(state)
0293:             return
0294: 
0295:         # Redis mode - require Redis to be available
0296:         try:
0297:             if not await repo.health_check():
0298:                 raise DriverStateUnavailableError(
0299:                     f"Redis driver state store is not available. "
0300:                     f"Cannot persist driver state without shared state store."
0301:                 )
0302:         except DriverStateUnavailableError:
0303:             raise
0304:         except Exception as e:
0305:             raise DriverStateUnavailableError(
0306:                 f"Failed to check Redis driver state store: {e}"
0307:             ) from e
0308: 
0309:         # CAS with retry
0310:         for attempt in range(max_retries):
0311:             try:
0312:                 current = await repo.get(state.driver_id)
0313:                 expected_version = current.version if current else 0
0314:                 snapshot = trace_state_to_snapshot(state, version=expected_version + 1)
0315: 
0316:                 success, actual_version = await repo.save_with_expected_version(
0317:                     snapshot, expected_version
0318:                 )
0319: 
0320:                 if success:
0321:                     logger.debug(
0322:                         f"Driver {state.driver_id} state persisted at version {actual_version}"
0323:                     )
0324:                     return
0325:                 else:
0326:                     logger.debug(
0327:                         f"Driver {state.driver_id} CAS conflict: expected {expected_version}, "
0328:                         f"actual {actual_version}, retrying (attempt {attempt + 1}/{max_retries})"
0329:                     )
0330:                     # Conflict - reload state and retry
0331:                     # Note: The caller's state may be stale; they need to re-read
0332: 
0333:             except DriverStateUnavailableError:
0334:                 raise
0335:             except Exception as e:
0336:                 raise DriverStateUnavailableError(
0337:                     f"Failed to persist driver state to Redis: {e}"
0338:                 ) from e
0339: 
0340:         # All retries exhausted
0341:         raise DriverStateUnavailableError(
0342:             f"Failed to persist driver state after {max_retries} retries due to conflicts"
0343:         )
0344: 
0345:     async def update_with_cas(
0346:         self,
0347:         driver_id: str,
0348:         update_fn,  # async def(state: DriverTraceState) -> DriverTraceState
0349:         max_retries: int = 3,
0350:     ) -> tuple[DriverTraceState, bool]:
0351:         """
0352:         Atomic read-modify-write using CAS.
0353: 
0354:         This method:
0355:         1. Reads current state from Redis
0356:         2. Applies update_fn to the state
0357:         3. Attempts CAS save
0358:         4. On conflict, re-reads and retries
0359: 
0360:         This prevents lost updates in concurrent scenarios.
0361: 
0362:         Args:
0363:             driver_id: Driver ID to update
0364:             update_fn: Async function that takes state and returns modified state
0365:             max_retries: Maximum retry attempts on conflict
0366: 
0367:         Returns:
0368:             (final_state, was_successful): The final state and whether save succeeded
0369: 
0370:         Raises:
0371:             DriverStateUnavailableError: When Redis is unavailable or retries exhausted
0372:         """
0373:         repo = self._get_repo()
0374: 
0375:         if repo is None:
0376:             local = get_state_store()
0377:             state = local.get_or_create(driver_id)
0378:             state = await update_fn(state)
0379:             local._states[driver_id] = state
0380:             return state, True
0381: 
0382:         if isinstance(repo, InMemoryDriverStateRepository):
0383:             state = await repo.get_or_create_local(driver_id)
0384:             state = await update_fn(state)
0385:             await repo.save_local(state)
0386:             return state, True
0387: 
0388:         # Redis mode
0389:         for attempt in range(max_retries):
0390:             # Read current state
0391:             current = await repo.get(driver_id)
0392:             if current is not None:
0393:                 state = snapshot_to_trace_state(current)
0394:                 expected_version = current.version
0395:             else:
0396:                 state = DriverTraceState(driver_id=driver_id)
0397:                 expected_version = 0
0398: 
0399:             # Apply update
0400:             state = await update_fn(state)
0401: 
0402:             # Prepare snapshot with version
0403:             snapshot = trace_state_to_snapshot(state, version=expected_version + 1)
0404: 
0405:             # Attempt CAS
0406:             try:
0407:                 success, actual_version = await repo.save_with_expected_version(
0408:                     snapshot, expected_version
0409:                 )
0410: 
0411:                 if success:
0412:                     logger.debug(
0413:                         f"Driver {driver_id} updated at version {actual_version}"
0414:                     )
0415:                     return state, True
0416:                 else:
0417:                     logger.debug(
0418:                         f"Driver {driver_id} CAS conflict: expected {expected_version}, "
0419:                         f"actual {actual_version}, retry {attempt + 1}/{max_retries}"
0420:                     )
0421:                     # Conflict - loop will retry
0422: 
0423:             except DriverStateUnavailableError:
0424:                 raise
0425:             except Exception as e:
0426:                 raise DriverStateUnavailableError(
0427:                     f"Failed to update driver state: {e}"
0428:                 ) from e
0429: 
0430:         # All retries exhausted
0431:         raise DriverStateUnavailableError(
0432:             f"Failed to update driver {driver_id} after {max_retries} retries due to conflicts"
0433:         )
```

## S4. API append flow; generation bị reset về mặc định ở nhánh retry
`backend/app/api/v1/realtime.py:129–214`

```text
0129: async def _persist_state(driver_id: str, state: DriverTraceState):
0130:     """Persist driver state to shared store. Raises error if unavailable."""
0131:     state_manager = get_driver_state_manager()
0132:     await state_manager.save(state)
0133: 
0134: 
0135: async def _persist_state_with_retry(driver_id: str, state: DriverTraceState):
0136:     """Persist driver state with CAS retry. Raises error if unavailable or retries exhausted."""
0137:     state_manager = get_driver_state_manager()
0138:     await state_manager.save_with_retry(state)
0139: 
0140: 
0141: async def _add_observation_with_cas(
0142:     driver_id: str,
0143:     obs: GPSObservation,
0144:     max_retries: int = 3,
0145: ) -> tuple[DriverTraceState, bool, bool, str]:
0146:     """
0147:     Add observation to driver state using CAS to prevent lost updates.
0148: 
0149:     This function:
0150:     1. Reads current state from Redis
0151:     2. Checks for stale observation
0152:     3. Checks generation for reset detection
0153:     4. Adds observation to state
0154:     5. Attempts CAS save
0155:     6. On conflict, re-reads and retries
0156: 
0157:     Returns:
0158:         (state, stale, gap_reset, gap_reason): The final state and flags
0159: 
0160:     Raises:
0161:         DriverStateUnavailableError: When Redis unavailable or retries exhausted
0162:     """
0163:     state_manager = get_driver_state_manager()
0164: 
0165:     # Normalize observation timestamp for comparison
0166:     obs_ts = obs.timestamp
0167:     if obs_ts.tzinfo is not None:
0168:         obs_ts = obs_ts.replace(tzinfo=None)
0169: 
0170:     expected_generation = None  # Track generation to detect resets
0171: 
0172:     for attempt in range(max_retries):
0173:         # Read current state
0174:         state = await state_manager.get_or_create(driver_id)
0175: 
0176:         # Check generation - if reset occurred, start fresh
0177:         if expected_generation is not None and state.generation != expected_generation:
0178:             # Reset occurred during processing - start with fresh state
0179:             logger.debug(
0180:                 f"Driver {driver_id}: generation changed from {expected_generation} to {state.generation}, "
0181:                 f"reset detected, starting fresh"
0182:             )
0183:             state = DriverTraceState(driver_id=driver_id)
0184:             state.generation = state.generation  # Keep current generation
0185: 
0186:         expected_generation = state.generation
0187: 
0188:         # Check stale
0189:         last_ts = state.last_observation_timestamp
0190:         if last_ts and last_ts.tzinfo is not None:
0191:             last_ts = last_ts.replace(tzinfo=None)
0192: 
0193:         if last_ts and obs_ts < last_ts:
0194:             # Stale observation - return current state without modification
0195:             return state, True, False, ""
0196: 
0197:         # Add observation
0198:         gap_reset, gap_reason = state.add_observation(obs)
0199: 
0200:         # Try to persist with CAS
0201:         try:
0202:             await state_manager.save_with_retry(state)
0203:             return state, False, gap_reset, gap_reason
0204:         except DriverStateUnavailableError:
0205:             raise
0206:         except Exception:
0207:             if attempt < max_retries - 1:
0208:                 # Retry - state may have changed
0209:                 continue
0210:             raise
0211: 
0212:     raise DriverStateUnavailableError(
0213:         f"Failed to add observation after {max_retries} retries"
0214:     )
```

## S5. Reset tăng generation nhưng không có conditional generation check; fallback DELETE
`backend/app/services/realtime/driver_state_manager.py:435–472`

```text
0435:     async def delete(self, driver_id: str) -> None:
0436:         """
0437:         Delete driver state.
0438: 
0439:         In Redis mode, we create a fresh state with incremented generation
0440:         instead of deleting. This prevents old requests (that started before
0441:         reset) from resurrecting state if they complete after reset.
0442:         """
0443:         repo = self._get_repo()
0444: 
0445:         if repo is None:
0446:             local = get_state_store()
0447:             local.remove(driver_id)
0448:             return
0449: 
0450:         if isinstance(repo, InMemoryDriverStateRepository):
0451:             await repo.delete(driver_id)
0452:             return
0453: 
0454:         # Redis mode - create fresh state with incremented generation
0455:         # This prevents old pending requests from resurrecting state
0456:         try:
0457:             # Read current state to get generation
0458:             current = await repo.get(driver_id)
0459:             current_gen = current.generation + 1 if current else 1
0460: 
0461:             # Create fresh state
0462:             new_state = DriverTraceState(driver_id=driver_id)
0463:             new_state.generation = current_gen
0464:             snapshot = trace_state_to_snapshot(new_state, version=1)
0465: 
0466:             # Save with CAS (use version=0 to always succeed for new state)
0467:             await repo.save(snapshot)
0468:         except Exception as e:
0469:             # If save fails, try to delete anyway
0470:             await repo.delete(driver_id)
0471:             logger.warning(f"Failed to reset driver state, fell back to delete: {e}")
0472: 
```

## S6. Nuốt final persistence failure
`backend/app/api/v1/realtime.py:273–303`

```text
0273:     if gap_reset:
0274:         state.current_status = MatchingStatus.GAP_RESET.value
0275: 
0276:     # Check warm-up
0277:     if state.is_warming_up():
0278:         state.current_status = MatchingStatus.WARMING_UP.value
0279:         # Persist state (in case it was modified by gap reset)
0280:         try:
0281:             await _persist_state_with_retry(driver_id, state)
0282:         except DriverStateUnavailableError:
0283:             pass
0284:         return LocationResponse(
0285:             driver_id=driver_id,
0286:             status=MatchingStatus.WARMING_UP,
0287:             message=f"Warming up: {len(state.observations)} observations (need 3+)",
0288:             total_observations=state.total_observations_received,
0289:             total_match_calls=state.total_match_calls,
0290:             buffered_points=len(state.observations),
0291:             movement_since_match_m=state.movement_since_match,
0292:         )
0293: 
0294:     # Check stationary suppression
0295:     if state.is_stationary() and state.last_matched_state is not None:
0296:         state.current_status = MatchingStatus.GPS_ACCEPTED.value
0297:         state.last_trigger_reason = "STATIONARY_SUPPRESSED"
0298:         # Persist state
0299:         try:
0300:             await _persist_state_with_retry(driver_id, state)
0301:         except DriverStateUnavailableError:
0302:             pass
0303:         return LocationResponse(
```

## S7. No-trigger, MATCHED và failure branches
`backend/app/api/v1/realtime.py:329–469`

```text
0329:     # Get trigger policy
0330:     policy = get_default_policy()
0331: 
0332:     # Check trigger
0333:     should_trigger, reason = policy.should_trigger(obs.timestamp, state)
0334:     state.last_trigger_reason = reason
0335: 
0336:     if not should_trigger:
0337:         state.current_status = MatchingStatus.GPS_ACCEPTED.value
0338:         # Persist state
0339:         try:
0340:             await _persist_state_with_retry(driver_id, state)
0341:         except DriverStateUnavailableError:
0342:             pass
0343:         return LocationResponse(
0344:             driver_id=driver_id,
0345:             status=MatchingStatus.GPS_ACCEPTED,
0346:             trigger_reason=reason,
0347:             raw_position={
0348:                 "latitude": obs.latitude,
0349:                 "longitude": obs.longitude,
0350:                 "timestamp": obs.timestamp.isoformat(),
0351:             },
0352:             last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
0353:             last_match_latency_ms=state.last_match_latency_ms,
0354:             total_observations=state.total_observations_received,
0355:             total_match_calls=state.total_match_calls,
0356:             buffered_points=len(state.observations),
0357:             movement_since_match_m=state.movement_since_match,
0358:             is_stationary=state.is_stationary(),
0359:         )
0360: 
0361:     # Trigger map matching
0362:     context = state.get_context()
0363:     if len(context) < 2:
0364:         state.current_status = MatchingStatus.WARMING_UP.value
0365:         return LocationResponse(
0366:             driver_id=driver_id,
0367:             status=MatchingStatus.WARMING_UP,
0368:             message=f"Not enough context: {len(context)} observations",
0369:             total_observations=state.total_observations_received,
0370:             total_match_calls=state.total_match_calls,
0371:             buffered_points=len(state.observations),
0372:         )
0373: 
0374:     # Call map matching
0375:     try:
0376:         response, latency_ms = await _call_map_match(context, request.vehicle_category, request.vehicle_id)
0377:     except ValueError as exc:
0378:         raise HTTPException(400, str(exc)) from exc
0379:     except (MapMatchingEngineError, psycopg2.Error) as exc:
0380:         state.current_status = MatchingStatus.ENGINE_UNAVAILABLE.value
0381:         # Try to persist ENGINE_UNAVAILABLE state, but return even if fails
0382:         try:
0383:             await _persist_state_with_retry(driver_id, state)
0384:         except DriverStateUnavailableError:
0385:             pass  # Best effort
0386:         return LocationResponse(
0387:             driver_id=driver_id, status=MatchingStatus.ENGINE_UNAVAILABLE,
0388:             trigger_reason=reason, message=str(exc),
0389:             raw_position={"latitude": obs.latitude, "longitude": obs.longitude, "timestamp": obs.timestamp.isoformat()},
0390:             total_observations=state.total_observations_received,
0391:             total_match_calls=state.total_match_calls, buffered_points=len(state.observations),
0392:         )
0393:     state.last_match_latency_ms = latency_ms
0394: 
0395:     latest_match = next((o for o in reversed(response.observations) if o.observation_id == context[-1].observation_id), None) if response else None
0396:     if latest_match is None or not latest_match.matched:
0397:         state.current_status = MatchingStatus.NO_MATCH.value
0398:         state.last_trigger_reason = f"NO_MATCH({reason})"
0399:         # Persist NO_MATCH state to maintain observation continuity
0400:         try:
0401:             await _persist_state_with_retry(driver_id, state)
0402:         except DriverStateUnavailableError:
0403:             pass  # Best effort
0404:         return LocationResponse(
0405:             driver_id=driver_id,
0406:             status=MatchingStatus.NO_MATCH,
0407:             trigger_reason=reason,
0408:             raw_position={
0409:                 "latitude": obs.latitude,
0410:                 "longitude": obs.longitude,
0411:                 "timestamp": obs.timestamp.isoformat(),
0412:             },
0413:             last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
0414:             last_match_latency_ms=latency_ms,
0415:             total_observations=state.total_observations_received,
0416:             total_match_calls=state.total_match_calls,
0417:             buffered_points=len(state.observations),
0418:             movement_since_match_m=state.movement_since_match,
0419:             is_stationary=state.is_stationary(),
0420:             message="No matched position for the latest observation",
0421:         )
0422: 
0423:     # Parse response and update state
0424:     match_resp = response
0425:     state.current_status = MatchingStatus.MATCHED.value
0426: 
0427:     matched_state = MatchedState(
0428:         matched_latitude=latest_match.matched_latitude,
0429:         matched_longitude=latest_match.matched_longitude,
0430:         road_segment_id=latest_match.road_segment_id,
0431:         osm_way_id=latest_match.osm_way_id,
0432:         direction=latest_match.direction,
0433:         confidence=latest_match.confidence if latest_match.confidence is not None else match_resp.overall_confidence,
0434:         route_geometry=match_resp.trace_geometry,
0435:     )
0436: 
0437:     state.reset_after_match(matched_state)
0438: 
0439:     # Persist the matched state to shared store
0440:     try:
0441:         await _persist_state_with_retry(driver_id, state)
0442:     except DriverStateUnavailableError:
0443:         pass  # Best effort - return response anyway
0444: 
0445:     return LocationResponse(
0446:         driver_id=driver_id,
0447:         status=MatchingStatus.MATCHED,
0448:         trigger_reason=reason,
0449:         raw_position={
0450:             "latitude": obs.latitude,
0451:             "longitude": obs.longitude,
0452:             "timestamp": obs.timestamp.isoformat(),
0453:         },
0454:         matched_position={
0455:             "latitude": matched_state.matched_latitude,
0456:             "longitude": matched_state.matched_longitude,
0457:             "road_segment_id": matched_state.road_segment_id,
0458:             "osm_way_id": matched_state.osm_way_id,
0459:             "direction": matched_state.direction,
0460:             "confidence": matched_state.confidence,
0461:         },
0462:         last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
0463:         last_match_latency_ms=latency_ms,
0464:         total_observations=state.total_observations_received,
0465:         total_match_calls=state.total_match_calls,
0466:         buffered_points=len(state.observations),
0467:         movement_since_match_m=state.movement_since_match,
0468:         is_stationary=state.is_stationary(),
0469:         message=f"Matched: {len(context)} points, confidence {matched_state.confidence:.4f}",
```

## S8. Validation timestamp vẫn bỏ offset
`backend/app/api/v1/realtime.py:89–106`

```text
0089: def _validate_observation(req: LocationIngestionRequest) -> tuple[bool, Optional[str]]:
0090:     """Validate GPS observation."""
0091:     # Check coordinates
0092:     if not (-90 <= req.latitude <= 90):
0093:         return False, "Invalid latitude"
0094:     if not (-180 <= req.longitude <= 180):
0095:         return False, "Invalid longitude"
0096: 
0097:     # Check timestamp is not in the future
0098:     # Handle both naive and aware datetimes
0099:     now = datetime.utcnow()
0100:     ts = req.timestamp
0101:     if ts.tzinfo is not None:
0102:         ts = ts.replace(tzinfo=None)
0103:     if ts > now:
0104:         return False, "Timestamp in the future"
0105: 
0106:     return True, None
```

## S9. ensure_utc, dedup IDs và giới hạn state
`backend/app/services/realtime/state.py:31–53`

```text
0031: 
0032: def make_naive(dt: datetime) -> datetime:
0033:     """Convert datetime to naive (no timezone) UTC for consistent comparison."""
0034:     if dt is None:
0035:         return None
0036:     if dt.tzinfo is not None:
0037:         dt = dt.replace(tzinfo=None)
0038:     return dt
0039: 
0040: 
0041: def ensure_utc(dt: datetime) -> datetime:
0042:     """
0043:     Ensure datetime is in UTC and naive format for consistent storage.
0044: 
0045:     - Naive datetimes are assumed to be UTC (legacy behavior)
0046:     - Aware datetimes are converted to UTC then made naive
0047:     """
0048:     if dt is None:
0049:         return None
0050:     if dt.tzinfo is not None:
0051:         dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
0052:     # Naive datetimes are kept as-is (assumed UTC)
0053:     return dt
```

## S10. Dedup không so payload và không có pruning seen IDs
`backend/app/services/realtime/state.py:129–205`

```text
0129: 
0130:     Maintains a bounded window of recent GPS observations and match state.
0131:     """
0132:     driver_id: str
0133:     observations: deque[GPSObservation] = field(default_factory=lambda: deque(maxlen=1000))
0134:     last_match_time: Optional[datetime] = None
0135:     last_matched_state: Optional[MatchedState] = None
0136:     movement_since_match: float = 0.0
0137:     last_observation_timestamp: Optional[datetime] = None
0138:     observations_since_match: int = 0
0139:     consecutive_stationary: int = 0
0140:     total_observations_received: int = 0
0141:     total_match_calls: int = 0
0142:     last_trigger_reason: Optional[str] = None
0143:     last_match_latency_ms: Optional[float] = None
0144:     current_status: str = "WARMING_UP"
0145:     generation: int = 1  # Incremented on reset to invalidate old requests
0146:     seen_observation_ids: set = field(default_factory=set)  # For deduplication
0147: 
0148:     def add_observation(self, obs: GPSObservation) -> tuple[bool, str]:
0149:         """
0150:         Add an observation and update state.
0151: 
0152:         Returns:
0153:             (was_gap_reset, gap_reason)
0154:         """
0155:         gap_reset = False
0156:         gap_reason = ""
0157: 
0158:         # Normalize timestamp to UTC for consistent storage
0159:         normalized_ts = ensure_utc(obs.timestamp)
0160:         obs.timestamp = normalized_ts
0161: 
0162:         # Check for duplicate observation
0163:         if obs.observation_id and obs.observation_id in self.seen_observation_ids:
0164:             # Skip duplicate - do not increment counters
0165:             return gap_reset, gap_reason
0166: 
0167:         # Check for gap (session reset)
0168:         last_ts = self.last_observation_timestamp
0169:         if last_ts:
0170:             last_ts_normalized = ensure_utc(last_ts)
0171:             gap_seconds = (normalized_ts - last_ts_normalized).total_seconds()
0172:             if gap_seconds > DEFAULT_GAP_THRESHOLD_SECONDS:
0173:                 # Reset state
0174:                 self.observations.clear()
0175:                 self.last_match_time = None
0176:                 self.last_matched_state = None
0177:                 self.movement_since_match = 0.0
0178:                 self.observations_since_match = 0
0179:                 self.consecutive_stationary = 0
0180:                 gap_reset = True
0181:                 gap_reason = f"gap({gap_seconds:.0f}s)"
0182: 
0183:         # Calculate movement from last observation
0184:         if self.observations:
0185:             prev = self.observations[-1]
0186:             dist = haversine_distance(
0187:                 prev.latitude, prev.longitude,
0188:                 obs.latitude, obs.longitude
0189:             )
0190:             self.movement_since_match += dist
0191: 
0192:             # Check for stationary (GPS jitter)
0193:             if dist < DEFAULT_STATIONARY_DISTANCE_M:
0194:                 self.consecutive_stationary += 1
0195:             else:
0196:                 self.consecutive_stationary = 0
0197: 
0198:         # Add observation
0199:         self.observations.append(obs)
0200:         if obs.observation_id:
0201:             self.seen_observation_ids.add(obs.observation_id)
0202:         self.last_observation_timestamp = obs.timestamp
0203:         self.observations_since_match += 1
0204:         self.total_observations_received += 1
0205: 
```

## S11. reset_state() có tồn tại; không được handler/manager hiện tại gọi
`backend/app/services/realtime/state.py:231–252`

```text
0231: 
0232:     def reset_after_match(self, matched_state: Optional[MatchedState] = None):
0233:         """Reset after successful match."""
0234:         self.last_match_time = self.last_observation_timestamp
0235:         self.movement_since_match = 0.0
0236:         self.observations_since_match = 0
0237:         self.last_matched_state = matched_state
0238:         self.total_match_calls += 1
0239: 
0240:     def reset_state(self):
0241:         """Reset state and increment generation to invalidate old requests."""
0242:         self.observations.clear()
0243:         self.seen_observation_ids.clear()  # Clear dedup set
0244:         self.last_match_time = None
0245:         self.last_matched_state = None
0246:         self.movement_since_match = 0.0
0247:         self.observations_since_match = 0
0248:         self.consecutive_stationary = 0
0249:         self.total_match_calls = 0
0250:         self.generation += 1  # Invalidate requests from previous generation
0251: 
0252:     def get_current_raw_position(self) -> Optional[tuple[float, float]]:
```

## S12. Integration A chỉ kiểm tra MATCHED có điều kiện
`backend/tests/test_shared_state_integration.py:81–148`

```text
0081: 
0082: 
0083: @pytest.mark.asyncio
0084: async def test_post_instance_a_get_instance_b(two_instances):
0085:     """
0086:     A: POST matched state on instance A, GET from instance B via Redis.
0087: 
0088:     Strong assertion: After multiple observations, both instances must see:
0089:     - Same status (both MATCHED or both NO_MATCH)
0090:     - Same total_observations count
0091:     - Same buffered_points count
0092:     - Same last_match_time if matched
0093:     """
0094:     url_a, url_b = two_instances
0095:     driver = f"{DRIVER_ID}_a_to_b"
0096: 
0097:     async with httpx.AsyncClient(timeout=30) as client:
0098:         # Clear any existing state
0099:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0100:         await asyncio.sleep(0.5)
0101: 
0102:         # Send multiple observations to trigger matching
0103:         for i in range(5):
0104:             obs = {
0105:                 "latitude": 21.028 + i * 0.002,
0106:                 "longitude": 105.854 + i * 0.002,
0107:                 "timestamp": datetime.now(timezone.utc).isoformat(),
0108:                 "speed_kmh": 30,
0109:                 "heading_deg": 90,
0110:                 "vehicle_category": "EV_CAR",
0111:             }
0112:             resp = await client.post(
0113:                 f"{url_a}/api/v1/drivers/{driver}/location",
0114:                 json=obs
0115:             )
0116:             await asyncio.sleep(0.5)
0117: 
0118:         # Get state from both instances
0119:         resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
0120:         resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
0121: 
0122:         assert resp_a.status_code == 200, f"GET A failed: {resp_a.text}"
0123:         assert resp_b.status_code == 200, f"GET B failed: {resp_b.text}"
0124: 
0125:         data_a = resp_a.json()
0126:         data_b = resp_b.json()
0127: 
0128:         # CRITICAL: Both must agree on status
0129:         assert data_a["status"] == data_b["status"], \
0130:             f"Status mismatch: A={data_a['status']} B={data_b['status']}"
0131: 
0132:         # CRITICAL: Both must see same counts
0133:         assert data_a["buffered_points"] == data_b["buffered_points"], \
0134:             f"Buffered points mismatch: A={data_a['buffered_points']} B={data_b['buffered_points']}"
0135:         assert data_a["total_observations"] == data_b["total_observations"], \
0136:             f"Total observations mismatch: A={data_a['total_observations']} B={data_b['total_observations']}"
0137: 
0138:         # CRITICAL: If matched, both must have matched_position
0139:         if data_a["status"] == "MATCHED":
0140:             assert data_a["matched_position"] is not None, "Instance A should have matched_position"
0141:             assert data_b["matched_position"] is not None, "Instance B should have matched_position"
0142:             assert data_a["last_match_time"] == data_b["last_match_time"], \
0143:                 f"last_match_time mismatch: A={data_a['last_match_time']} B={data_b['last_match_time']}"
0144: 
0145:         # CRITICAL: At least 5 observations should be accepted
0146:         assert data_a["total_observations"] >= 5, \
0147:             f"Expected >=5 observations, got {data_a['total_observations']}"
0148: 
```

## S13. Test concurrent gửi tuần tự
`backend/tests/test_shared_state_integration.py:151–218`

```text
0151: 
0152: 
0153: @pytest.mark.asyncio
0154: async def test_concurrent_writes(two_instances):
0155:     """
0156:     B: Concurrent writes from both instances must not lose observations.
0157: 
0158:     Strong assertion:
0159:     - Both requests succeed (200 OK)
0160:     - Final observation count >= number of unique observations sent
0161:     - Both instances see the same final count
0162:     - No observation IDs are silently dropped
0163:     """
0164:     url_a, url_b = two_instances
0165:     driver = f"{DRIVER_ID}_concurrent"
0166: 
0167:     async with httpx.AsyncClient(timeout=30) as client:
0168:         # Clear
0169:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0170:         await asyncio.sleep(0.5)
0171: 
0172:         # Send observations from BOTH instances sequentially (testing state consistency)
0173:         obs_a = {
0174:             "latitude": 21.005,
0175:             "longitude": 105.005,
0176:             "timestamp": datetime.now(timezone.utc).isoformat(),
0177:             "speed_kmh": 30,
0178:             "heading_deg": 90,
0179:             "vehicle_category": "EV_CAR",
0180:         }
0181:         resp_a = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs_a)
0182:         assert resp_a.status_code == 200, f"Write A failed: {resp_a.text}"
0183:         count_a_after_first = resp_a.json()["total_observations"]
0184: 
0185:         obs_b = {
0186:             "latitude": 21.006,
0187:             "longitude": 105.006,
0188:             "timestamp": datetime.now(timezone.utc).isoformat(),
0189:             "speed_kmh": 35,
0190:             "heading_deg": 95,
0191:             "vehicle_category": "EV_CAR",
0192:         }
0193:         resp_b = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs_b)
0194:         assert resp_b.status_code == 200, f"Write B failed: {resp_b.text}"
0195: 
0196:         # Both instances should see consistent count
0197:         resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
0198:         resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
0199: 
0200:         data_a = resp_a.json()
0201:         data_b = resp_b.json()
0202: 
0203:         # CRITICAL: No lost updates - count must be >= 2 (both obs accepted)
0204:         assert data_a["total_observations"] >= 2, \
0205:             f"Lost update: expected >=2 observations, got {data_a['total_observations']}"
0206:         assert data_b["total_observations"] >= 2, \
0207:             f"Lost update: expected >=2 observations, got {data_b['total_observations']}"
0208: 
0209:         # CRITICAL: Both instances must agree on final count
0210:         assert data_a["total_observations"] == data_b["total_observations"], \
0211:             f"Inconsistent counts: A={data_a['total_observations']} B={data_b['total_observations']}"
0212: 
0213:         # Cleanup
0214:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0215: 
0216: 
0217: @pytest.mark.asyncio
0218: async def test_reset_during_pending_request(two_instances):
```

## S14. Test pending reset không tạo pending request
`backend/tests/test_shared_state_integration.py:220–291`

```text
0220:     D2: Reset during pending request - old state should not resurrect.
0221: 
0222:     Scenario:
0223:     1. Send observation O1 (accepted)
0224:     2. Send observation O2 (pending)
0225:     3. Reset state via DELETE
0226:     4. O2 request completes
0227:     5. Final state should be empty (reset), not include O2
0228: 
0229:     Strong assertion:
0230:     - After reset, both instances see buffered_points == 0
0231:     - total_observations resets to 0
0232:     - No old observations resurrect after reset
0233:     """
0234:     url_a, url_b = two_instances
0235:     driver = f"{DRIVER_ID}_reset_pending"
0236: 
0237:     async with httpx.AsyncClient(timeout=30) as client:
0238:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0239:         await asyncio.sleep(0.5)
0240: 
0241:         # Step 1: Send O1
0242:         obs1 = {
0243:             "latitude": 21.05,
0244:             "longitude": 105.05,
0245:             "timestamp": datetime.now(timezone.utc).isoformat(),
0246:             "speed_kmh": 30,
0247:             "heading_deg": 90,
0248:             "vehicle_category": "EV_CAR",
0249:         }
0250:         resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
0251:         assert resp1.status_code == 200
0252:         assert resp1.json()["total_observations"] == 1
0253: 
0254:         # Step 2: Reset via DELETE
0255:         resp_del = await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0256:         assert resp_del.status_code == 200
0257:         assert resp_del.json()["reset"] == True
0258: 
0259:         # Step 3: Verify both instances see empty state
0260:         resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
0261:         resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
0262: 
0263:         data_a = resp_a.json()
0264:         data_b = resp_b.json()
0265: 
0266:         # CRITICAL: Both see 0 observations after reset
0267:         assert data_a["buffered_points"] == 0, \
0268:             f"Instance A should see 0 points after reset, got {data_a['buffered_points']}"
0269:         assert data_b["buffered_points"] == 0, \
0270:             f"Instance B should see 0 points after reset, got {data_b['buffered_points']}"
0271:         assert data_a["total_observations"] == 0, \
0272:             f"Instance A should see 0 total after reset, got {data_a['total_observations']}"
0273:         assert data_b["total_observations"] == 0, \
0274:             f"Instance B should see 0 total after reset, got {data_b['total_observations']}"
0275: 
0276:         # Step 4: New observation starts fresh (generation increment)
0277:         obs2 = {
0278:             "latitude": 21.06,
0279:             "longitude": 105.06,
0280:             "timestamp": datetime.now(timezone.utc).isoformat(),
0281:             "speed_kmh": 30,
0282:             "heading_deg": 90,
0283:             "vehicle_category": "EV_CAR",
0284:         }
0285:         resp2 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs2)
0286:         assert resp2.status_code == 200
0287:         assert resp2.json()["total_observations"] == 1, \
0288:             "New observation after reset should start from 1"
0289: 
0290:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0291: 
```

## S15. Test stale đã sửa timedelta
`backend/tests/test_shared_state_integration.py:294–364`

```text
0294: async def test_stale_observation_rejected(two_instances):
0295:     """
0296:     C: Stale observation (before last timestamp) is rejected.
0297: 
0298:     Strong assertion:
0299:     - Status is STALE_OBSERVATION
0300:     - Counters do not increment for rejected observation
0301:     - Next valid observation continues correctly
0302:     """
0303:     url_a, url_b = two_instances
0304:     driver = f"{DRIVER_ID}_stale"
0305: 
0306:     async with httpx.AsyncClient(timeout=30) as client:
0307:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0308:         await asyncio.sleep(0.5)
0309: 
0310:         # Send observation with recent timestamp
0311:         now = datetime.now(timezone.utc)
0312:         obs1 = {
0313:             "latitude": 21.01,
0314:             "longitude": 105.01,
0315:             "timestamp": now.isoformat(),
0316:             "speed_kmh": 30,
0317:             "heading_deg": 90,
0318:             "vehicle_category": "EV_CAR",
0319:         }
0320:         resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
0321:         assert resp1.status_code == 200
0322:         count_after_valid = resp1.json()["total_observations"]
0323: 
0324:         # Try to send stale observation (1 minute earlier)
0325:         # Use timedelta instead of replace(minute=minute-1) to handle minute=0 correctly
0326:         stale_ts = (now - timedelta(minutes=1)).isoformat()
0327:         obs2 = {
0328:             "latitude": 21.02,
0329:             "longitude": 105.02,
0330:             "timestamp": stale_ts,
0331:             "speed_kmh": 30,
0332:             "heading_deg": 90,
0333:             "vehicle_category": "EV_CAR",
0334:         }
0335:         resp2 = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs2)
0336: 
0337:         assert resp2.status_code == 200
0338:         data2 = resp2.json()
0339:         # CRITICAL: Status must be STALE_OBSERVATION
0340:         assert data2["status"] == "STALE_OBSERVATION", \
0341:             f"Expected STALE_OBSERVATION, got {data2['status']}"
0342: 
0343:         # CRITICAL: Count must NOT increment for stale observation
0344:         assert data2["total_observations"] == count_after_valid, \
0345:             f"Stale observation should not increment count: expected {count_after_valid}, got {data2['total_observations']}"
0346: 
0347:         # Send valid observation - should increment correctly
0348:         obs3 = {
0349:             "latitude": 21.03,
0350:             "longitude": 105.03,
0351:             "timestamp": datetime.now(timezone.utc).isoformat(),
0352:             "speed_kmh": 30,
0353:             "heading_deg": 90,
0354:             "vehicle_category": "EV_CAR",
0355:         }
0356:         resp3 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs3)
0357:         assert resp3.status_code == 200
0358:         # CRITICAL: Count should be count_after_valid + 1
0359:         assert resp3.json()["total_observations"] == count_after_valid + 1, \
0360:             f"Valid obs should increment: expected {count_after_valid + 1}, got {resp3.json()['total_observations']}"
0361: 
0362:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0363: 
0364: 
```

## S16. Test duplicate chỉ gửi unique observations
`backend/tests/test_shared_state_integration.py:367–428`

```text
0367:     """
0368:     E: No duplicate observations - each unique observation is counted once.
0369: 
0370:     Strong assertion:
0371:     - After N unique observations, total_observations == N
0372:     - Both instances see the same count
0373:     - Subsequent observation continues to increment
0374:     """
0375:     url_a, url_b = two_instances
0376:     driver = f"{DRIVER_ID}_dup"
0377: 
0378:     async with httpx.AsyncClient(timeout=30) as client:
0379:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0380:         await asyncio.sleep(0.5)
0381: 
0382:         # Send N=3 unique observations
0383:         expected_count = 0
0384:         for i in range(3):
0385:             obs = {
0386:                 "latitude": 21.03 + i * 0.001,
0387:                 "longitude": 105.03 + i * 0.001,
0388:                 "timestamp": datetime.now(timezone.utc).isoformat(),
0389:                 "speed_kmh": 30,
0390:                 "heading_deg": 90,
0391:                 "vehicle_category": "EV_CAR",
0392:             }
0393:             resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
0394:             assert resp.status_code == 200
0395:             expected_count += 1
0396:             data = resp.json()
0397:             # CRITICAL: Each unique observation increments count by exactly 1
0398:             assert data["total_observations"] == expected_count, \
0399:                 f"Expected {expected_count} after {i+1} observations, got {data['total_observations']}"
0400: 
0401:         # Both instances must agree
0402:         resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
0403:         resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
0404: 
0405:         count_a = resp_a.json()["total_observations"]
0406:         count_b = resp_b.json()["total_observations"]
0407: 
0408:         # CRITICAL: Both see exact count
0409:         assert count_a == expected_count, f"Instance A: expected {expected_count}, got {count_a}"
0410:         assert count_b == expected_count, f"Instance B: expected {expected_count}, got {count_b}"
0411:         assert count_a == count_b, f"Inconsistent counts: A={count_a} B={count_b}"
0412: 
0413:         # Send 4th observation - count must be 4
0414:         obs4 = {
0415:             "latitude": 21.04,
0416:             "longitude": 105.04,
0417:             "timestamp": datetime.now(timezone.utc).isoformat(),
0418:             "speed_kmh": 30,
0419:             "heading_deg": 90,
0420:             "vehicle_category": "EV_CAR",
0421:         }
0422:         resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs4)
0423:         assert resp.json()["total_observations"] == 4, "4th observation should increment to 4"
0424: 
0425:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0426: 
0427: 
0428: @pytest.mark.asyncio
```

## S17. Test version chỉ assert >= 1
`backend/tests/test_shared_state_integration.py:431–486`

```text
0431:     F: Sequential writes increment version atomically.
0432: 
0433:     Strong assertion:
0434:     - Version increments on each save
0435:     - Both instances see consistent state
0436:     - State is correctly persisted to Redis
0437:     """
0438:     import redis
0439:     url_a, url_b = two_instances
0440:     driver = f"{DRIVER_ID}_seq"
0441: 
0442:     r = redis.Redis(host='127.0.0.1', port=6379)
0443: 
0444:     async with httpx.AsyncClient(timeout=30) as client:
0445:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0446:         await asyncio.sleep(0.5)
0447: 
0448:         # Send 3 sequential observations with vehicle_category
0449:         for i in range(3):
0450:             obs = {
0451:                 "latitude": 21.04 + i * 0.001,
0452:                 "longitude": 105.04 + i * 0.001,
0453:                 "timestamp": datetime.now(timezone.utc).isoformat(),
0454:                 "speed_kmh": 30 + i * 5,
0455:                 "heading_deg": 90,
0456:                 "vehicle_category": "EV_CAR",
0457:             }
0458:             resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
0459:             assert resp.status_code == 200
0460: 
0461:         # Both instances should see same final state
0462:         resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
0463:         resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
0464: 
0465:         data_a = resp_a.json()
0466:         data_b = resp_b.json()
0467: 
0468:         assert data_a["buffered_points"] == data_b["buffered_points"], \
0469:             f"Points mismatch: {data_a['buffered_points']} vs {data_b['buffered_points']}"
0470:         assert data_a["total_observations"] == data_b["total_observations"], \
0471:             f"Total observations mismatch: {data_a['total_observations']} vs {data_b['total_observations']}"
0472: 
0473:         # CRITICAL: Check version in Redis
0474:         snapshot = r.get(f"driver_state:{driver}")
0475:         assert snapshot is not None, "State should be in Redis"
0476:         import json
0477:         s = json.loads(snapshot)
0478:         assert s["version"] >= 1, f"Version should be >= 1, got {s['version']}"
0479:         print(f"DEBUG: Redis version={s['version']} obs={len(s.get('observations', []))}")
0480: 
0481:         await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
0482: 
0483: 
0484: if __name__ == "__main__":
0485:     # Run as standalone script for manual testing
0486:     pytest.main([__file__, "-v", "-s"])
```

## S18. Diff integration tests so với 8640ff2
```diff
--- 8640ff2/backend/tests/test_shared_state_integration.py
+++ cfbe350/backend/tests/test_shared_state_integration.py
@@ -16,7 +16,7 @@
 import sys
 import httpx
 import pytest
-from datetime import datetime, timezone
+from datetime import datetime, timezone, timedelta
 
 
 BASE_URL_A = "http://127.0.0.1:8000"
@@ -322,11 +322,12 @@
         count_after_valid = resp1.json()["total_observations"]
 
         # Try to send stale observation (1 minute earlier)
-        stale_ts = now.replace(minute=now.minute - 1)
+        # Use timedelta instead of replace(minute=minute-1) to handle minute=0 correctly
+        stale_ts = (now - timedelta(minutes=1)).isoformat()
         obs2 = {
             "latitude": 21.02,
             "longitude": 105.02,
-            "timestamp": stale_ts.isoformat(),
+            "timestamp": stale_ts,
             "speed_kmh": 30,
             "heading_deg": 90,
             "vehicle_category": "EV_CAR",

```
Ba file unit tests trong `test_source_comparison.json` có nội dung không đổi.