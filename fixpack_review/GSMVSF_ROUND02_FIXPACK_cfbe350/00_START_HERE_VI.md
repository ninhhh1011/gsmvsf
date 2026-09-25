# GSMVSF — Gói sửa tiếp ROUND 02 sau audit cfbe350

## Dùng gói này

Đưa toàn bộ ZIP cho Claude đang làm ROUND 02. Giải nén vào thư mục audit ngoài `E:\build6week`, ví dụ `E:\gsmvsf_audit_exports\`.

Đọc **01_PROMPT_CLAUDE_ROUND02.md** để triển khai. **02_ACCEPTANCE_MATRIX.md** chỉ rõ timeline/assertion cần chứng minh và evidence lịch sử liên quan.

**Repository để sửa:** working tree hiện tại tại `E:\build6week`.

**Thư mục tuyệt đối không sửa để “fix”:** `round02_review_cfbe350/input/snapshot/`. Đó là source lịch sử dùng trong audit. Không copy đè snapshot lên repository.

## Nội dung

- `01_PROMPT_CLAUDE_ROUND02.md`: prompt đầy đủ, Phase → Task → exit gates.
- `02_ACCEPTANCE_MATRIX.md`: bộ điều kiện nghiệm thu cho những lỗi còn lại và các positive regressions cần giữ.
- `round02_review_cfbe350/`: toàn bộ 105 file của bộ audit được gửi trước, giữ nguyên nội dung từng file: báo cáo, source có số dòng, harness, kết quả JSON/JUnit/logs, source snapshot và metadata.
- `MANIFEST_SHA256.json`: inventory/hash của gói này; không bao gồm hash của chính manifest.

Không cần ZIP 8640ff2 hoặc lịch sử chat cũ để đọc các finding chính của gói này. Đây không phải bản clone đầy đủ của repository; implementation và acceptance tests phải thực hiện ở local workspace thật.

## Phạm vi bằng chứng

Audit được đóng gói là audit lịch sử của snapshot `cfbe350eea862cca734fc28b334b3da63ec732bc`, không phải audit mới của working tree local hiện tại.

Theo audit kèm theo: 28 independent checks gồm 17 PASS / 11 FAIL; 26 exported unit tests PASS; 6 thân hàm integration vẫn PASS với matching cố ý lỗi. Những nhóm này có phạm vi khác nhau, không phải rerun toàn bộ 385 tests.

Harness dùng một Python process, ASGI/Lua/Redis-command/matching fixtures; chưa nghiệm thu hai API process + Redis/GraphHopper thật. Đọc báo cáo/README gốc để biết thiếu dependency, import shims và các giới hạn TTL/cjson/network. Không đưa shims/fake implementation vào production hoặc dùng chúng thay gate Redis thật.

Bước tạo gói này chỉ đọc/kiểm tra archive và viết prompt/manifest; không chạy lại backend, sửa sản phẩm hoặc tạo thêm kết quả test. Trạng thái PASS/FAIL trong `round02_review_cfbe350/results/` được giữ nguyên từ audit trước.

## Kết quả cần nhận từ Claude

Sửa source local → regression cho counterexamples → hai API process + Redis thật → raw evidence gắn source cuối → kết luận gate đúng phạm vi. Không nhận thêm bảng “test name → PASS” thiếu request/state/timeline.

Không chuyển ROUND 03 khi các gate bắt buộc của ROUND 02 chưa đạt.
