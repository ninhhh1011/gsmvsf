# PROMPT — Hoàn tất ROUND 02 sau audit cfbe350

Bạn là Senior Backend Engineer + Concurrency QA. Tiếp tục làm việc tại repository thật `E:\build6week`. Đây là phần sửa tiếp ROUND 02, không phải ROUND 03.

Bộ giao việc này chứa audit của snapshot `cfbe350eea862cca734fc28b334b3da63ec732bc`. Kết luận lịch sử của audit: `ROUND_02_NOT_COMPLETE`. Đối chiếu với HEAD/working tree hiện tại trước khi quyết định sửa; không mặc định mọi lỗi vẫn còn nếu source đã thay đổi.

## 1. Mục tiêu và cách làm bắt buộc

Audit repository → lập implementation plan chi tiết → chia Phase → Task → tự triển khai từng task → tự kiểm thử sau từng task → review code/diff → chỉ chuyển phase khi exit gate đạt → chạy regression và final audit toàn bộ yêu cầu.

Sau khi lập plan, bắt đầu triển khai ngay, không chờ duyệt từng phase. Không trả menu lựa chọn hoặc chỉ viết báo cáo “đã hiểu”. Có blocker thật thì ghi command, exit code, logs và phần đã hoàn thành; không hỏi lại mục tiêu đã được giao.

Mỗi task phải có: requirement/invariant, file liên quan, thay đổi dự kiến, test/node ID, evidence và điều kiện hoàn thành. Tên hàm, comment, commit message, HTTP 200 hoặc tổng test count không thay thế bằng chứng hành vi.

Ưu tiên sửa đúng luồng gọi hiện tại bằng một protocol nhất quán xuyên handler → manager → repository. Không thêm một API/hàm CAS mới rồi để ingestion tiếp tục gọi đường cũ. Không đổi framework, thêm queue/service, viết lại frontend replay, redesign Tech View hay thay demand/ranking/routing objective.

## 2. Đọc đúng tài liệu, không sửa nhầm snapshot

Giải nén bộ này vào thư mục audit riêng ngoài `E:\build6week`. Đọc:

1. `00_START_HERE_VI.md`.
2. `round02_review_cfbe350/AUDIT_ROUND02_CFBE350_VI.md`.
3. `round02_review_cfbe350/SOURCE_EVIDENCE.md`.
4. `round02_review_cfbe350/results/SUMMARY.json` và các JSON theo từng finding.
5. `round02_review_cfbe350/harness/test_correctness.py`, `test_new_protocol.py`, `audit_support.py`.
6. `02_ACCEPTANCE_MATRIX.md`.

`round02_review_cfbe350/input/snapshot/` là bằng chứng cũ, KHÔNG phải workspace để sửa. Không copy đè snapshot lên repository và không chỉnh evidence lịch sử thành PASS. Sửa source thật tại `E:\build6week`; lưu evidence mới riêng.

Harness audit dùng modules từ snapshot, ASGI apps trong một process, fixture GET/SET/matching và Lua 5.4. Nó không xác minh Redis server, TTL/cjson đầy đủ, hai OS process hoặc live GraphHopper. Audit cũng không chạy lại 385 tests. Đọc kỹ giới hạn đó.

Dùng timeline/input/assertions làm đặc tả regression và port sang tooling local. Không đưa fake Redis, import shims hoặc `--noconftest` của audit vào production/acceptance suite. Không cài Lua 5.4 chỉ để bắt chước sandbox. Xác minh `module.__file__`/hash để tests chạy code local mới, không vô tình chạy snapshot hoặc image cũ.

## 3. Giữ nguyên dữ liệu và phần đã sửa đúng

Trước khi sửa, ghi branch, full HEAD, git status, diff; đọc hướng dẫn repository và scope/workbook nếu có. Không reset/clean/checkout đè/stash/revert hàng loạt, không làm mất thay đổi người dùng, không tự push/tag.

Không sửa `dataset_v1`, PBF hoặc workbook; lấy hash trước/sau. Không ghi secrets vào reports/logs. Không dùng `down -v`, `FLUSHALL`, `--remove-orphans` hoặc kill hàng loạt để chữa môi trường. Chỉ quản lý process/container/test keys do runner tạo hoặc đã được xác định rõ để nghiệm thu; không tác động phiên agent khác.

Giữ các positive regressions của snapshot:
- Primitive `save_with_expected_version()` từ chối expected version sai.
- Retry cùng ID/payload trong tình huống đơn giản không đếm thêm.
- Reset tuần tự tăng generation và cho observation mới bắt đầu sạch.
- Các nhánh MATCHED/NO_MATCH/ENGINE_UNAVAILABLE/no-trigger/gap/stationary lưu đúng khi write thành công.
- EVAL lỗi không quay về unchecked SET ở repository.
- Initial write failure trả lỗi, helper UTC chuyển offset đúng, stale test dùng timedelta.

Không revert các phần này chỉ để viết lại. Lỗi cần sửa nằm ở sự phối hợp và failure/concurrency paths.

## 4. Các finding còn lại và nghiệm thu cụ thể

### FIX-01 — Không dùng version mới để ghi payload cũ

Evidence: `results/manager_fresh_version_stale_payload.json`, `concurrent_lost_update.json`, `late_match_overwrite.json`.

Manager `save_with_retry(state)` đọc current version nhưng serialize state do caller tính từ lần đọc cũ; retry không tính lại mutation. Primitive CAS đúng vẫn cho phép stale overwrite vì caller đã đưa version mới vào.

Yêu cầu:
- State/envelope mang immutable base version và generation của lần đọc tạo ra payload; serialization/manager không làm mất token.
- Conditional write nguyên tử so sánh đúng token. Không refresh token để hợp thức hóa payload cũ.
- Conflict được phân biệt với unavailable; retry có giới hạn phải load state mới và chạy lại mutation/validation trên đó.
- Nếu vẫn cần nhận raw observation và finalize matching bằng hai commit, mô tả rõ token sau từng commit và context/observation mà kết quả matching thuộc về.
- Late result không được overwrite whole-state cũ, xóa observation mới, lùi vị trí hoặc generation. Bỏ/recompute/merge kết quả chỉ theo một policy được chứng minh không ghi đè state mới.
- Không giữ mutex trong một Python process rồi kết luận multi-instance đúng. Không chạy matching/network I/O trong Redis Lua.
- Khi TTL/key lifecycle làm token cũ không còn hợp lệ, không tự coi request cũ là một create mới hợp lệ.

### FIX-02 — Reset phải duy trì hàng rào generation, cả khi ghi lỗi

Evidence: `results/reset_resurrection.json`, `reset_unchecked_delete_fallback.json`.

Reset snapshot thành generation 2 nhưng request pending ghi lại generation 1. Khi lưu reset lỗi, manager còn fallback DELETE key rồi báo success.

Yêu cầu:
- Reset là chuyển generation/epoch nguyên tử hoặc cơ chế tương đương. Final write từ generation cũ phải bị chặn, không rebase thành generation mới.
- Không giảm/reuse generation theo cách cho phép stale request quay lại. Chốt reset, create-after-reset và TTL semantics phù hợp phạm vi, không thêm dịch vụ ngoài hệ thống hiện có.
- Không fallback sang DELETE phá generation fence khi ghi reset thất bại; response phải phản ánh lỗi.
- Reset test phải release và await request cũ hoàn tất trước khi assert không resurrection; sau đó kiểm tra observation mới bắt đầu đúng generation mới.

### FIX-03 — Không nuốt final-write failure rồi ACK MATCHED/GPS_ACCEPTED

Evidence: `results/final_matched_write_failure.json`, `final_no_trigger_write_failure.json`.

Yêu cầu:
- Loại đường `except DriverStateUnavailableError: pass`/best-effort đang báo final state chưa commit là thành công.
- Audit tất cả return paths, không chỉ MATCHED. Dependency failure của final commit trả lỗi rõ theo contract đợt 2, ưu tiên HTTP 503 cho state-store unavailable; conflict có code riêng, không dùng nhầm candidate conflict.
- Phân biệt raw observation đã được commit với derived match chưa commit. Không giả rollback raw event; client retry sau lỗi cũng không được double-count hoặc bị coi là đã finalize khi chưa finalize.
- No success response khẳng định final state mà read-back không thể quan sát do write đã thất bại. Khi write thành công và không có update xen giữa, response/read-back phải nhất quán.
- Không gom lỗi lập trình, conflict và unavailable thành một catch-all để che nguyên nhân.

### FIX-04 — Normalize UTC trước validation, stale check và dedup identity

Evidence: `results/timezone_equivalence.json`, `timezone_stale_regression.json`, `timezone_newer_rejected.json`.

Yêu cầu:
- Dùng `ensure_utc()` hoặc helper duy nhất ở boundary trước các phép so sánh và khi load snapshot cần normalize; không chỉ normalize khi append.
- Không dùng `replace(tzinfo=None)` để chuyển instant. Policy naive timestamp phải rõ và nhất quán với compatibility của project.
- Clock inject được cho test. Equivalent Z/+07/negative-offset trả quyết định tương đương, event cũ không làm lùi state, event mới không bị từ chối chỉ vì wall clock nhỏ hơn.
- Retry cùng dữ liệu nhưng timestamp viết bằng offset tương đương phải được đánh giá theo canonical instant, không tùy chuỗi hiển thị.

### FIX-05 — Dedup phải phân biệt retry hợp lệ với reuse ID sai

Evidence: `results/duplicate_payload_conflict.json`; `dedup_retention_diagnostic.json` là diagnostic retention, KHÔNG phải benchmark memory leak.

Yêu cầu:
- Cùng ID/cùng canonical payload: giữ logical accepted count, không nhân đôi record và vẫn có hành vi retry/finalization đúng contract.
- Cùng ID/payload khác: trả conflict/error rõ, không ACK như observation hợp lệ; không đổi state/counter trái phép.
- So sánh payload đã normalize; không để server-generated receipt time tạo conflict giả. Dùng fingerprint hoặc canonical payload phù hợp kiến trúc hiện có.
- Chốt thứ tự kiểm tra duplicate/stale theo contract; retry không được kéo state về event cũ.
- Dedup cũng đúng qua hai instances. Chốt retention có giới hạn/cleanup và giới hạn bảo đảm retry; không giữ set tăng vô hạn hoặc âm thầm quên ID trước window được công bố.

### TEST-01 — Sửa tests cho đúng lịch xử lý và assertion

Evidence: `results/diff_test_0.patch`, `test_source_comparison.json`, `original_6_bodies_fixture.txt`.

Test tên concurrent không được await POST A hoàn tất rồi mới POST B. Test reset pending phải có request pending. Duplicate phải gửi lại cùng ID/payload. MATCHED test phải bắt buộc có MATCHED, không bọc assertion trong `if`. Version test quan sát transition/conditional-write semantics, không chỉ `>= 1`.

Không dùng tổng count tối thiểu, A == B hoặc cả hai HTTP 200 làm bằng chứng duy nhất. Kiểm tra expected IDs/payload, trước/sau và outcome của từng request. Event bị từ chối stale/conflict rõ ràng không phải accepted event bị mất; cũng không được để mọi request bị no-op/conflict rồi gọi progress đạt.

## 5. Plan triển khai theo Phase → Task

### PHASE 0 — Audit, reproducible baseline, thiết kế commit protocol

- Đọc call graph thực: validation → read → append/dedup → trigger → matching → commit → response → GET/reset. Kiểm tra mọi public write path và caller, không chỉ hàm có tên CAS.
- Đối chiếu FIX-01…05/TEST-01 với HEAD mới. Port deterministic repro của stale-manager payload, concurrent append, pending reset, late matching, final-write failure, UTC và conflicting payload.
- Trước sửa, ghi rõ tests nào fail đúng lỗi và tests positive nào pass. Không bắt test lỗi phải xanh để qua baseline gate; expected red baseline có evidence là điều kiện hợp lệ của phase này.
- Viết protocol commit duy nhất: base token, generation, mutation retry, finalization context, accepted semantics, duplicate retention, reset failure và error codes. Kiểm tra compatibility của snapshot cũ trong phạm vi hiện có; không âm thầm xóa state người dùng để vượt schema lỗi.

**Exit gate 0:** có failing reproducer cho lỗi còn tồn tại (hoặc bằng chứng đã sửa ở HEAD mới), positive baseline và plan/task cụ thể. Không chỉ thêm tên hàm hoặc README.

### PHASE 1 — Protocol manager/handler/repository và reset

- Sửa FIX-01/FIX-02. Giữ primitive CAS đúng, nối nó vào actual ingestion/finalization path. Retry phải tính lại operation, không payload cũ.
- Regression đơn giản không timing: A giữ O1, B commit O2, A cố save stale state; O2 không được mất.
- Regression barrier: hai writer cùng base state; accepted IDs đầy đủ. Test conflict/retry/cap, late matching, reset pending và reset write failure.
- Dọn/khóa đường unchecked save hoặc helper không dùng trong write path cần bảo đảm để tránh bypass protocol; không refactor unrelated modules.

**Exit gate 1:** các interleavings trong matrix đạt và không mất accepted event/ghi lùi generation. Tên CAS hoặc test primitive PASS không đủ.

### PHASE 2 — Final state/error, UTC và dedup

- Sửa FIX-03/FIX-04/FIX-05; tích hợp vào protocol phase 1, không vá độc lập rồi phá concurrency.
- Fault-inject sau raw acceptance, sau matching nhưng trước final commit, trong reset, và initial read/write. Bao phủ các final-state branches theo khả năng chuyển trạng thái thực tế.
- Kiểm tra full duplicate lifecycle, gồm retry sau lỗi finalize; UTC before validation; retention boundary với dữ liệu nhỏ có kiểm soát.
- Giữ positive regressions đã đạt. Không gọi diagnostic retention là lỗi production đã đo.

**Exit gate 2:** success/error/read-back đúng contract; UTC và dedup hợp lệ; không còn success giả hoặc reset fallback phá fence.

### PHASE 3 — Tests thật, hai API process và Redis thật

- Hoàn thiện local runner dùng tooling sẵn có. Tạo/tái sử dụng hai OS process riêng, cùng Redis test instance/database/namespace và cùng source fingerprint. Docker+local Python hoặc hai container đều được.
- Chỉ tái sử dụng process nếu xác minh được owner/config/source. Build/recreate đúng API khi cần; không mặc định `up -d` hoặc `--remove-orphans` chứng minh build mới. Healthchecks có timeout và actual error logs, không sửa `/ready` thành luôn xanh.
- Một runner quản lý startup, readiness phù hợp test dependencies, logs, test execution, timeout và cleanup các tài nguyên do nó tạo. Không phát background commands rồi kết thúc trước khi thu kết quả. Nếu daemon không sẵn có hoặc permission bị chặn, ghi blocker thực tế và thao tác tối thiểu cần người dùng; không vượt quyền.
- Dùng synchronization trong test-only harness để giữ/release requests và đo overlap; timeout giúp test không treo. Không thêm production debug bypass. Matching fixture được phép để tạo race, nhưng HTTP handler, manager, repository/Lua và Redis phải thật.
- Ghi `REDIS_REAL_HTTP_INTEGRATION_WITH_MATCHING_FIXTURE`; tách GraphHopper thật nếu chạy được. Một-process ASGI/fakeredis không thay gate này. Không bắt dựng lại toàn bộ production stack chỉ để chạy matching-controlled test.
- Chạy CASE-01…15 trong matrix ở đúng lớp tương ứng. Với fault injection, chỉ dùng test resources được quản lý. Baseline labels cần nói rõ test nào real Redis, test nào controlled matching.
- Nếu fixture skip dependency trong suite development, lệnh acceptance phải phát hiện mandatory skip/zero collection và kết luận gate chưa đạt. Không coi exit code 0 với test chưa chạy là PASS.

**Exit gate 3:** two-process Redis evidence gồm command, PID/container IDs, source hashes, request outcomes, stored IDs, version/generation timeline; yêu cầu bắt buộc không skip.

### PHASE 4 — Regression trên source cuối và final audit

- Chạy backend suite, tests mới, frontend unit và browser regression Round 01 theo cấu hình thực tế. Không ép số test về 385/12/50; báo counts đúng, không cộng trùng các suite lồng nhau.
- Sau bất kỳ thay đổi source nào, rerun affected tests và gates tương ứng trên source cuối. Phân biệt lỗi baseline, environment và regression mới; không bỏ failing tests, sửa reference hoặc giảm assertions để đạt count.
- Review toàn diff, protocol call sites, error catches, production mocks/bypasses, secrets và frozen-data hashes. Không đổi scope hoặc tự tuyên bố production-ready.
- Lưu raw stdout/stderr + JUnit/JSON ở `runtime/remediation/round-02/<run-id>/`. Bảo toàn exit code thực khi redirect logs. Ghi HEAD + dirty-file/source manifest vì HEAD một mình chưa mô tả working tree chưa commit.
- Cập nhật một báo cáo canonical `docs/remediation/round-02.md`, ghi phần cũ là historical/superseded khi cần; không tạo nhiều báo cáo “final” mâu thuẫn. Không chỉnh evidence lịch sử của gói.

**Exit gate 4:** requirement → production path → concrete test/assertion → executed evidence đầy đủ, regression không bị phá, source/hashes xác minh được.

## 6. Final report bắt buộc và điều kiện kết luận

Báo cáo bằng dữ liệu mới, không chỉ “all gates verified”:

1. HEAD/branch/working-tree fingerprint, môi trường và source thực sự được chạy ở hai API.
2. FIX-01…05/TEST-01: root cause hiện tại, file sửa, test và exit gate.
3. Accepted observation IDs so với final stored IDs; outcomes của request bị từ chối nếu có.
4. Duplicate: count trước, sau lần đầu, sau retry; conflicting payload response và state không đổi.
5. Final write fault: POST outcome và GET từ instance khác; không chỉ case initial write fault.
6. Reset: generation trước, sau reset, sau khi pending request đã settle; late-match timeline.
7. UTC: input timestamps tương đương/cũ/mới và kết quả.
8. Commands/exit codes/actual counts, skip reasons, raw evidence paths; phân biệt unit/fixture/Redis thật/live GraphHopper.
9. Giới hạn còn lại, integrity hashes và source diff đã review.

`ROUND_02_PASS`: tất cả gate bắt buộc được thực thi và đạt.

`ROUND_02_NOT_COMPLETE`: còn lỗi, thiếu requirement hoặc chưa có bằng chứng cần thiết.

`ROUND_02_BLOCKED_ENV`: có command/log chứng minh môi trường thực sự chặn gate bắt buộc; không dùng “cần hai API” làm nguyên nhân chung chung.

Không tự bắt đầu ROUND 03. Không tuyên bố PASS khi integration skip, request chưa settle, matching chưa từng thành công hoặc chỉ các helper được test. Giữ các phần đã làm đúng và hoàn thiện luồng hiện có.
