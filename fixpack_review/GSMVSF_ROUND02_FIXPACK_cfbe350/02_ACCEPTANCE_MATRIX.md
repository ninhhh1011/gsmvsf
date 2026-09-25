# ROUND 02 — Ma trận nghiệm thu sau audit cfbe350

Đây là đặc tả kiểm thử, **không phải kết quả đã chạy trên source sau sửa**. Tất cả trạng thái mới phải được Claude điền từ lần thực thi thực tế.

Evidence lịch sử nằm dưới `round02_review_cfbe350/results/`. Dùng đúng timeline và assertions, không bắt chước giới hạn môi trường/shims của harness. Nếu HEAD mới đã sửa một lỗi, giữ code và chứng minh bằng tests.

| Case | Tình huống bắt buộc | Assertion tối thiểu | Evidence lịch sử / ranh giới |
|---|---|---|---|
| CASE-01 | CAS primitive: ghi hợp lệ rồi thử base version cũ | Stale expected bị từ chối; payload hiện tại không đổi; version đúng contract | `positive_cas_primitive.json`; positive cần giữ; chạy thêm Redis thật |
| CASE-02 | A giữ O1, B commit O2, A save stale payload | O2 không mất; stale write conflict hoặc mutation được tính lại; không gắn version mới cho payload cũ | `manager_fresh_version_stale_payload.json`; deterministic không cần timing |
| CASE-03 | Hai writer thực sự đọc cùng base state, rồi cùng cập nhật | Có overlap/barrier evidence; accepted IDs/payload đầy đủ; outcome/retry đúng; không chỉ count >=2 | `concurrent_lost_update.json`; two-process/Redis thật, không gửi tuần tự |
| CASE-04 | O3 matching pending, O4 hoàn tất, sau đó O3 trả về | State không lùi/xóa O4; final matching phù hợp context đã commit | `late_match_overwrite.json`; controlled matching qua production flow |
| CASE-05 | Request pending → reset B → release/await request cũ → read-back | Generation không lùi; state cũ không sống lại; observation mới bắt đầu đúng session/generation | `reset_resurrection.json`; assert sau pending request settle |
| CASE-06 | Reset generation write lỗi trong khi GET/DELETE vẫn khả dụng | Không fallback DELETE phá fence; response lỗi rõ; không fake reset success | `reset_unchecked_delete_fallback.json`; fault injection test resources |
| CASE-07 | Raw observation đã lưu; matching xong; final write lỗi | Không ACK MATCHED/final status chưa commit; lỗi đúng contract; GET phản ánh state thực; retry không double-count | `final_matched_write_failure.json`, `final_no_trigger_write_failure.json` |
| CASE-08 | Đồng hồ cố định; equivalent Z/+07; stale/newer ở offset khác | Equivalent instant cùng quyết định; event cũ không làm lùi state; event mới không bị từ chối do wall clock | `timezone_equivalence.json`, `timezone_stale_regression.json`, `timezone_newer_rejected.json` |
| CASE-09 | Cùng ID/cùng payload gửi lần đầu, retry, và đồng thời qua hai API | Count N→N+1→N+1; ID duy nhất; state không lùi; retry/finalization đúng | `duplicate.json`, `positive_duplicate_concurrent_observed.json`; các positive cần giữ/mở rộng |
| CASE-10 | Cùng ID nhưng payload khác; cùng instant viết bằng offset khác | Payload mâu thuẫn bị báo lỗi rõ và không mutation; dữ liệu tương đương đã normalize không tạo conflict giả | `duplicate_payload_conflict.json`; test semantics, không chỉ so ID |
| CASE-11 | Dedup retention boundary, long-active session với mẫu nhỏ | Retention được công bố và có giới hạn/cleanup; retry trong window giữ đúng; không quên ID trái contract | `dedup_retention_diagnostic.json` là diagnostic, không phải benchmark production |
| CASE-12 | MATCHED/NO_MATCH/ENGINE_UNAVAILABLE/no-trigger/gap/stationary khi write thành công | MATCHED case bắt buộc MATCHED và non-null match; POST/GET khác instance khớp contract, không update xen giữa | `positive_match.json`, `positive_no_match.json`, `positive_engine_unavailable.json`, `no_trigger_persistence.json`, `gap_status.json`, `positive_stationary_persistence.json` |
| CASE-13 | Read, initial write, EVAL, delete/list failure; bounded conflict retry | Không local/unchecked SET fallback; unavailable khác conflict; không success giả; retry kết thúc có outcome rõ | `positive_read_unavailable.json`, `write_outage.json`, `lua_fallback.json`; không suy initial write thành final-write proof |
| CASE-14 | Regression về assertion cũ và version | Test MATCHED không được pass khi chỉ ENGINE_UNAVAILABLE; concurrent/pending/duplicate đúng timeline; quan sát version transition thực | `original_6_bodies_fixture.txt`, `diff_test_0.patch`; negative-control hỗ trợ test quality, không thay live gate |
| CASE-15 | Hai API process thật cùng Redis, restart một API | Source mới/hash xác minh được; GET qua instance còn lại giữ state theo contract; test owner cleanup đúng | Chưa có raw live evidence trong input cũ; phải tạo evidence mới |

## Điều kiện áp dụng chung

- Dữ liệu expected và baseline phải được ghi rõ; IDs riêng, chưa vượt window retention/TTL. Không tính một stale/conflict rejection minh bạch như accepted event bị mất.
- So sánh counters nghiệp vụ với expected, không yêu cầu request/engine attempt counter giống accepted counter. Không cộng trùng counts của các test suites.
- Một primitive unit test không thay kiểm thử luồng HTTP. Barrier và matching fixture chỉ điều khiển lịch ở test harness, không thay production state manager/repository/Lua bằng fake implementation.
- Integration dùng hai OS process và Redis thật. Matching fixture phải ghi nhãn riêng; engine thật nếu có là nhóm khác.
- Với race/reset, chờ mọi request liên quan settle rồi mới assertion cuối. Không biến timeout/hanging task thành success.
- Mandatory skip/zero collection/thiếu startup làm gate chưa đạt. Raw logs/source fingerprint phải gắn với source cuối, không chỉ copy Markdown từ run trước.
- Mỗi case phải có test node ID + assertion + observed data + command/exit code + evidence path, không chỉ một ô PASS.
