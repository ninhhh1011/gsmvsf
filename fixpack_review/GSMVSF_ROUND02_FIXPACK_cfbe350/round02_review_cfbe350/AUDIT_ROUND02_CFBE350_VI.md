# Audit độc lập ROUND 02 — snapshot cfbe350

## Kết luận

**ROUND_02_NOT_COMPLETE.** Có thay đổi đúng so với snapshot 8640ff2: primitive CAS từ chối expected version sai; retry cùng observation ID/payload ở tình huống đơn giản không tăng count; các nhánh GPS_ACCEPTED/gap/stationary được persist khi không có lỗi ghi; fallback EVAL → unchecked SET đã bỏ; test timestamp ở phút 00 đã sửa.

Tuy nhiên, các counterexample mất cập nhật, matching cũ ghi đè, reset resurrection và UTC ở API vẫn tái hiện. Thêm vào đó, final write thất bại bị handler nuốt lỗi rồi trả MATCHED thành công. Đây là kết quả kiểm thử implementation, không chỉ nhận xét báo cáo.

## 1. Source và ranh giới bằng chứng

Gói được gửi: `gsmvsf_round02_audit_cfbe350_20260925_150337(1).zip`.
HEAD do manifest khai báo: `cfbe350eea862cca734fc28b334b3da63ec732bc`.
Branch khai báo: `week5-realtime-api-evaluation`.

Đã xác minh lại hash 39/39 source files, tổng 43/43 entries có hash trong manifest; trước/sau kiểm tra đều khớp. Không sửa source trong `input/snapshot`. Đây là kiểm tra nội dung ZIP, không phải chứng thực Git history, image Docker hoặc working tree hiện tại trên máy người dùng.

Export tự ghi `MISSING_EVIDENCE`: không có raw pytest output của 6 integration tests/385 backend tests và không có raw source-verification log hai API. Báo cáo Markdown trong gói không được coi là raw evidence của một lần chạy mới.

### Môi trường thực thi ở lần audit này

- Import handler, manager, repository, state và trigger trực tiếp từ source snapshot.
- FastAPI router thật được mount trên hai ASGI app/manager, trong **một Python process**.
- Thực thi nguyên văn Lua từ repository bằng Lua 5.4 VM có sẵn.
- GET/SET/EVAL transport và JSON conversion dùng fixture trong bộ nhớ, không phải Redis server. Lua return-array được chuyển sang Python list theo kiểu trả về cần cho repository.
- Matching dùng fixture trả kết quả xác định hoặc lỗi có kiểm soát.
- Shim import cho redis-py/psycopg2 và matching provider vì dependency/đường khởi tạo không sẵn có. Không thay implementation CAS/state manager bằng fake implementation.
- Python 3.13.5; versions chi tiết trong `results/SUMMARY.json`.
- Redis server/Docker không có; pip install bị lỗi DNS; tải Redis tarball cũng thất bại. Không có live Redis, GraphHopper, PostGIS hoặc hai OS process được nghiệm thu ở đây.
- Không mô hình hóa TTL expiry, replication, cluster, network hay Redis cjson đầy đủ. Empty arrays được fixture giữ nguyên. Các phát hiện không được dùng như một chứng nhận tương thích Redis runtime.

Các race được điều phối ở ranh giới read/matching bằng barrier/event. Không tạo interleaving bên trong Lua. Như vậy counterexample không phụ thuộc vào việc phá tính nguyên tử của script.

## 2. Kết quả thực thi

| Nhóm | Kết quả | Ranh giới |
|---|---:|---|
| 28 checks hành vi độc lập | **17 PASS, 11 FAIL, 0 ERROR, 0 SKIP** | Original modules + ASGI/Lua/KV/matching fixtures |
| 26 unit tests có trong ZIP | **26 PASS** | Chạy 3 file: shared(11), manager(8), repository(7); bỏ conftest toàn app, có import shims |
| 6 thân hàm integration nguyên bản | **6 PASS** | Thay network/Redis bằng harness; matching cố ý ENGINE_UNAVAILABLE |
| Lặp 3 test race, mỗi test 3 lần | **9/9 lần vẫn tái hiện failure**, 0 lỗi harness | Không cộng vào 28 unique checks |
| Bộ 385 tests của repository | **Không chạy lại** | ZIP không phải toàn bộ repository/môi trường |

11 failing checks không đồng nghĩa 11 root causes riêng biệt. Xem danh sách test/assertion trong `results/SUMMARY.json`, raw outputs và JUnit XML.

## 3. Điểm đã sửa đúng — giữ lại

1. `RedisDriverStateRepository.save_with_expected_version()` thực sự có kiểm tra version. Test primitive tạo state ở v1, update đúng lên v2, rồi thử stale expected v1: trả `(False, 2)`, dữ liệu không bị ghi đè. Evidence: `positive_cas_primitive.json`.
2. Retry cùng ID/cùng payload ở tình huống warm-up giữ count 1 và chỉ một ID được lưu. Evidence: `duplicate.json`.
3. Reset tuần tự tăng generation và observation mới bắt đầu count 1. Evidence: `positive_reset_generation.json`. Chưa suy thành reset race đúng.
4. MATCHED, NO_MATCH, ENGINE_UNAVAILABLE, GPS_ACCEPTED no-trigger, gap warm-up và stationary suppression đọc lại đúng trong các bài không inject lỗi ghi. Evidence: các `positive_*`, `no_trigger_persistence.json`, `gap_status.json`.
5. `ensure_utc()` tự nó chuyển đúng offset. Evidence: `positive_utc_helper.json`. Helper đúng không đồng nghĩa API đã gọi đúng chỗ.
6. EVAL lỗi không còn plain SET trong `repository.save()`. Evidence: `lua_fallback.json` giờ ghi exception được ném ra và snapshot không thay đổi.
7. Lỗi ghi observation ban đầu trả 503, không còn 500 trong bài tương ứng. Evidence: `write_outage.json`. Final write là trường hợp khác.
8. Biểu thức timedelta mới của test stale hoạt động tại phút 00. Evidence: `stale_test_minute_zero.json`.

## 4. Finding F1 — CAS primitive đúng nhưng manager dùng sai base version

**Mức độ: chặn nghiệm thu shared-state correctness.**

`driver_state_manager.py:309–318` đọc snapshot hiện tại ngay trong `save_with_retry()`, lấy `expected_version` mới, nhưng serialize lại biến `state` cũ do caller đưa vào. Khi retry, payload không được tính lại. `DriverTraceState` không giữ version từ lần đọc dùng để tính payload; `snapshot_to_trace_state()` cũng không chuyển base version.

`update_with_cas()` có đường read → update_fn → conditional save riêng, nhưng không được realtime ingestion gọi. `_add_observation_with_cas()` gọi `save_with_retry(state)` và nhánh conflict bị biến thành `DriverStateUnavailableError`, không tạo chu trình tính lại mutation đúng như tên hàm hứa.

### Counterexample không cần race timing

1. O1 đã lưu; caller A giữ state chỉ có O1.
2. B nhận O2 và trả thành công: snapshot chứa O1/O2, version 4.
3. A gọi `save_with_retry(stale_state)`.
4. Manager đọc version 4 rồi commit payload chỉ có O1 thành version 5.

Kết quả: O2 biến mất, không có conflict. Evidence: `manager_fresh_version_stale_payload.json`.

### Counterexample concurrent API

Hai handler cùng đọc `[O0]` bằng barrier. A thêm OA, B thêm OB. Cả hai trả HTTP 200/WARMING_UP và total_observations=2. State cuối chỉ có `[O0, OA]`, version 6. OB đã được xác nhận chấp nhận nhưng bị mất. Test phân biệt accepted business status với HTTP 200/STALE, không bắt hệ thống phải chấp nhận observation cũ sau retry.

Evidence: `concurrent_lost_update.json`; source S1–S4.

### Counterexample matching trả muộn

O3 bị giữ ở matching; O4 được instance còn lại nhận và trả MATCHED. Sau khi O3 hoàn tất, state lùi từ `[O1,O2,O3,O4]` về `[O1,O2,O3]`.

Evidence: `late_match_overwrite.json`.

**Sửa đúng hướng:** truyền base version/generation từ lần đọc tới commit; retry phải load và tính lại mutation; kết quả matching cũ phải bị loại hoặc được đánh giá lại với context mới, không gắn version mới vào payload cũ. Không cần bỏ primitive CAS đã có.

## 5. Finding F2 — Generation chỉ được lưu, chưa ngăn stale commit

**Mức độ: chặn nghiệm thu reset race.**

DELETE bình thường tạo snapshot rỗng có generation tăng. Nhưng `save_with_retry()` và Lua CAS không kiểm tra generation của payload; pending matching không bị chặn trước final commit.

Tình huống chạy:

```
O1/O2 đã nhận, generation 1.
O3 vào matching và bị giữ pending.
DELETE qua manager B → state rỗng, generation 2.
Cho O3 hoàn tất.
POST O3 trả MATCHED.
GET B → 3 observations cũ, generation quay về 1.
```

Evidence: `reset_resurrection.json`; source S4–S5. Đã chờ request cũ hoàn tất trước khi assert, không chỉ đọc state ngay sau DELETE.

Ngoài ra, `state.reset_state()` tồn tại nhưng không được luồng DELETE/ingest hiện tại gọi. Nhánh generation-change trong `_add_observation_with_cas()` tạo mới state rồi gán `state.generation = state.generation`, không giữ generation vừa đọc; đây là lỗi đọc code bổ sung, không cần dựa vào nó để tái hiện pending matching failure.

Nếu lưu reset snapshot lỗi, `manager.delete()` fallback sang DELETE key và trả thành công; evidence `reset_unchecked_delete_fallback.json` cho thấy không còn generation fence. Không đồng nhất với fallback EVAL→SET cũ: đó là đường lỗi mới cần sửa.

## 6. Finding F3 — Final write lỗi vẫn ACK MATCHED/GPS_ACCEPTED

**Mức độ: chặn nghiệm thu tính nhất quán response/state.**

`realtime.py:439–443`:

```python
try:
    await _persist_state_with_retry(driver_id, state)
except DriverStateUnavailableError:
    pass  # Best effort - return response anyway
```

Tôi chỉ inject EVAL failure sau khi matching xong; bước nhận/lưu raw observation đã thành công. POST trả 200/MATCHED, matched_position có dữ liệu, total_match_calls=1. GET qua manager B vẫn WARMING_UP, matched_position=null, total_match_calls=0.

Evidence: `final_matched_write_failure.json`. Nhánh no-trigger cũng trả GPS_ACCEPTED khi final write lỗi và GET vẫn MATCHED; evidence `final_no_trigger_write_failure.json`.

Đây không phải yêu cầu luôn loại bỏ observation đã được nhận khi engine gặp lỗi. Vấn đề là response đang xác nhận final match/status chưa được lưu mà không nêu persistence failure. Contract đợt 2 yêu cầu lỗi ghi final state được phản ánh rõ.

Các nhánh warm-up, stationary, NO_MATCH và ENGINE_UNAVAILABLE cũng có catch/pass tương tự khi đọc source. Bài chạy final-write đã cô lập MATCHED và no-trigger; không khẳng định đã fault-inject từng nhánh còn lại.

## 7. Finding F4 — ensure_utc() chưa được dùng trước validation/stale check

**Mức độ: sai xử lý observation và thứ tự thời gian.**

`ensure_utc()` trong state.py đúng, nhưng `_validate_observation()` và `_add_observation_with_cas()` vẫn bỏ offset bằng replace(tzinfo=None). `state.add_observation()` chỉ normalize sau hai bước quyết định đó.

### Kết quả A: cùng instant nhưng response khác

Clock kiểm thử cố định `2026-09-25T03:32:30Z`:
- `2026-09-25T03:31:00Z` → 200.
- `2026-09-25T10:31:00+07:00` → 400, Timestamp in the future.

Evidence: `timezone_equivalence.json`.

### Kết quả B: timestamp cũ được nhận và làm lùi state

Đã nhận 07:00Z. Gửi 13:59+07:00 (tức 06:59Z). API nhận WARMING_UP thay vì STALE_OBSERVATION, total tăng lên 2, last timestamp lùi về 06:59.

Evidence: `timezone_stale_regression.json`.

### Kết quả C: timestamp mới bị từ chối

Đã nhận 07:00Z. Gửi 00:01-07:00 (tức 07:01Z). API trả STALE_OBSERVATION.

Evidence: `timezone_newer_rejected.json`; source S8–S10.

**Sửa đúng hướng:** normalize tại boundary trước mọi validation/comparison; áp dụng thống nhất khi load snapshot cũ; không chỉ thêm helper ở bước append.

## 8. Finding F5 — Dedup cải thiện nhưng chưa đủ contract

Retry cùng ID/cùng payload ở case đơn giản đã PASS. Tuy nhiên cùng ID/payload khác vẫn bị coi là retry và trả 200/WARMING_UP mà không báo xung đột. Evidence `duplicate_payload_conflict.json`.

`seen_observation_ids` chỉ là set ID, không lưu fingerprint payload, nên không phân biệt retry hợp lệ với reuse ID sai. Không nên bỏ dedup; cần bổ sung xử lý conflict theo contract.

Diagnostic riêng (không tính vào 28 tests): thêm 2.000 observation vào state, deque giữ 1.000 nhưng seen IDs giữ 2.000. Trong source được gửi không có pruning cho seen IDs ngoài reset_state; TTL của whole-state lại được refresh khi truy cập. Đây là rủi ro retention đối với driver hoạt động lâu, không phải khẳng định đã benchmark memory leak production. Evidence `dedup_retention_diagnostic.json`.

## 9. Tests và report vẫn tuyên bố quá phạm vi được thực thi

So sánh trực tiếp hai snapshot:
- Integration file chỉ đổi import/tạo stale timestamp sang timedelta. Logic concurrent, pending/reset, duplicate và MATCHED conditional không đổi.
- Ba unit files shared/manager/repository có nội dung không đổi.
- Evidence: `diff_test_0.patch`, `test_source_comparison.json`.

| Tên test | Thân hàm thực tế |
|---|---|
| concurrent_writes | Chờ POST A xong mới POST B; còn comment “sequentially”. Không có request overlap/barrier. |
| reset_during_pending_request | POST O1 đã xong rồi DELETE. Không có task pending để chờ release. |
| no_duplicate_observation_counting | Gửi 3 observation mới rồi observation thứ 4; không gửi lại cùng ID/payload. |
| post_instance_a_get_instance_b | So sánh hai GET; matched assertions nằm trong if status == MATCHED. |
| sequential_writes_increment_version | Chỉ assert version cuối >=1; không assert transition version. |

Sáu thân hàm vẫn PASS trong harness khi matching cố ý luôn ENGINE_UNAVAILABLE. Test A quan sát WARMING_UP, WARMING_UP, ENGINE_UNAVAILABLE ×3 và hai GET ENGINE_UNAVAILABLE nhưng vẫn PASS. Đây là minh chứng về coverage, **không phải chạy lại integration thật**.

Không có căn cứ kết luận agent bịa số 385. Kết luận có bằng chứng: những tests được cung cấp không tạo các lịch xử lý đã gây lỗi; kết quả PASS của chúng không chứng minh các invariant được gắn trong báo cáo.

## 10. Đánh giá R2-01…R2-08

| Requirement | Đánh giá snapshot |
|---|---|
| R2-01 CAS/no lost update | Primitive PASS; manager/handler composition FAIL. |
| R2-02 Generation/reset | Sequential reset PASS; pending reset/late result FAIL. |
| R2-03 Dedup | Same-ID same-payload simple retry PASS; conflicting payload chưa xử lý; retention chưa bounded trong source. |
| R2-04 Final state | Các happy-path branches đã kiểm tra PASS; failure path liên quan R2-07 vẫn không bảo đảm. |
| R2-05 UTC | Helper PASS; API validation/order FAIL. |
| R2-06 EVAL fallback | Unsafe SET fallback đã bỏ, positive test PASS. Reset fallback DELETE vẫn là finding riêng. |
| R2-07 Error contract | Read/initial write 503 PASS; final write bị nuốt lỗi FAIL. |
| R2-08 Timestamp test | PASS ở boundary phút 00. |

## 11. Việc cần giao sửa tiếp

Không rollback toàn repo, không thêm technology và không chuyển ROUND 03.

1. Hoàn thiện duy nhất một protocol commit xuyên handler/manager/repository: base version + generation, bounded retry có tính lại mutation, guard final matching và reset.
2. Bỏ đường catch/pass tạo success cho final state chưa lưu; bỏ reset fallback phá generation. Giữ lỗi conflict khác lỗi unavailable.
3. Normalize UTC trước quyết định nghiệp vụ; bổ sung fingerprint/retention phù hợp cho dedup.
4. Port counterexamples vào test tooling local với production Redis thật. Tạo concurrency/pending thật, không gửi tuần tự. Giữ các positive regressions hiện đã đạt.
5. Chạy two-process/live Redis gate và full regression trên source cuối; kèm raw logs/source fingerprint. Không lấy bộ harness này thay thế live acceptance.

## 12. Tệp và cách tái hiện

Xem `README.md` để chạy harness trong môi trường tương thích. Harness đòi liblua5.4 và một số Python packages; có import shims và không thiết kế để đưa vào production.

Người thực hiện Windows không cần dựng thêm Lua 5.4 chỉ để bắt chước sandbox. Có thể dùng input/timeline/assertion trong tests để port sang test suite hiện có với Redis thật. Không sửa source snapshot trong gói; sửa repository làm việc thực tế.

Raw evidence chính: `results/SUMMARY.json`, `independent_tests.txt/xml`, `original_unit_tests.txt/xml`, `original_6_bodies_fixture.txt/xml`, các JSON theo từng finding, `deterministic_repetitions.json`.

Source có số dòng: `SOURCE_EVIDENCE.md`.

### Tài liệu chính thức đối chiếu

- Redis, Scripting with Lua: https://redis.io/docs/latest/develop/programmability/eval-intro/
- Redis, Transactions/optimistic locking: https://redis.io/docs/latest/develop/using-commands/transactions/
- Python datetime, astimezone/replace: https://docs.python.org/3/library/datetime.html

Các URL chỉ giải thích semantics chung; evidence lỗi dự án là source và kết quả thực thi đính kèm, không phải tài liệu bên ngoài.
