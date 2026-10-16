# Sửa cảnh báo năng lượng và rà soát project — 2026-10-12

Đã sửa lỗi trong ảnh: `VALID_REQUEST` biểu thị yêu cầu tìm trạm hợp lệ, không biểu thị pin yếu. Backend giờ trả đánh giá năng lượng riêng; frontend hiển thị kết quả đó. Với SOC 84%, tầm xa đầu vào 150 km và chuyến 34,6 km, cả hai API local trả `VALID_REQUEST` cho yêu cầu và `SAFE` cho pin.

Rà soát dựa trên source và các tình huống kiểm chứng, không lấy báo cáo cũ làm bằng chứng. Giả định vận hành: demo local, hai API cùng PostgreSQL/Redis/GraphHopper. Không chứng nhận toàn bộ project hết lỗi.

## Đã sửa trong lượt này

| Nhóm | Thay đổi | Kiểm chứng |
|---|---|---|
| Cảnh báo nhầm yêu cầu tìm trạm thành thiếu pin | Thêm `energy_assessment.warning_level` vào hợp đồng; giữ nguyên `need_service`, `request_valid`, `VALID_REQUEST` của yêu cầu chủ động. Phân biệt pin thấp, thiếu dự phòng, không tới được đích và chưa đủ dữ liệu. | SOC cao, pin thấp, thiếu dự phòng, thiếu SOC, legacy response; API live cả hai replica |
| Cảnh báo cũ ghi đè trạng thái mới | Cập nhật đánh giá pin trong lúc giữ trạm đã chọn, không gọi lại ranking. Chặn phản hồi cũ sau đổi SOC/model, power-step và các drawer refresh chồng nhau; lỗi từ request cũ cũng bị bỏ qua. | Deferred-request regressions; browser thấp/cao, giữ trạm, lỗi kết nối và khôi phục |
| Mất tầm xa trước Candidate Search | Truyền tầm xa được detector tính từ SOC/catalog vào hợp đồng. Giữ dữ liệu tầm xa/trip/reserve đã cung cấp cho yêu cầu chủ động thiếu SOC; cảnh báo vẫn `UNAVAILABLE`. | SOC-only và range-only regressions |
| Số liệu pin không hợp lệ | Demand context và ba API nhận telemetry từ chối số không hữu hạn (`NaN`, `Infinity`). | Sáu kiểm thử HTTP 422 |

Không thay chính sách ngưỡng pin, tiêu chí eligibility/ranking, mô hình vật lý hoặc Dataset V1. `energy_assessment` là trường cộng thêm, optional để đọc được evidence cũ; không cần migration database. Khi dữ liệu chưa có hoặc truy vấn đánh giá thất bại, UI không khẳng định pin an toàn.

## Kết quả kiểm chứng

- Backend: **574 PASS / 12 skipped**; frontend: **215 PASS**; Ruff PASS; `git diff --check` PASS.
- Canonical validator: **152 PASS / 0 FAIL**, **22/22 scenario assertions**. Hash của **63 file canonical** khớp manifest trước migration; không có file thay đổi.
- Đã rebuild hai API local; cả hai healthy và trả đúng hợp đồng mới. Frontend hiện dùng static bind mount.
- Browser Chromium/Playwright trên stack thật: **18/18 PASS**, desktop 1440×900 và mobile 390×844. Không có page errors. Kiểm tra request chủ động pin cao, chọn trạm, hạ/nâng SOC, giữ lựa chọn, không rerank khi đang dẫn đường, lỗi đánh giá và khôi phục. Lỗi mạng chỉ được giả lập trong trang kiểm thử, không dừng dịch vụ.
- Review độc lập tìm hai regression trong bản sửa (range-only và phản hồi cũ sau power-step); đã tái hiện, sửa và thêm regression tests. Review cuối không còn blocker trong bản sửa cảnh báo.

Evidence local: `runtime/energy-warning-audit-20261012/`: `backend-tests.txt`, `frontend-tests.txt`, `ruff.txt`, `validator.txt`, `dataset-integrity.json`, `live-api.json`, `browser-results.json`, ảnh desktop/mobile và script tái chạy.

## Tám lỗi còn mở sau rà soát

Các lỗi dưới đây **chưa sửa trong bản vá cảnh báo**. P1 cần ưu tiên vì có thể sai trạng thái hoặc dẫn tới phương án không phục vụ được xe. P2 làm sai kết quả trong các tình huống dữ liệu cụ thể. Đây là danh sách lỗi đã có căn cứ, không phải dự đoán chung chung.

### 1. P1 — GPS mới bị ghi đè, reset có thể bị phục hồi bởi request cũ

Source: `backend/app/api/v1/realtime.py:205`, `backend/app/services/realtime/driver_state_manager.py:304` và Redis CAS trong repository.

Request A đọc trace, request B cập nhật trace, rồi A đọc lại phiên bản mới nhưng vẫn ghi payload cũ. Khóa phiên bản (CAS: chỉ ghi khi phiên bản chưa đổi) mất tác dụng vì phiên bản không đi cùng dữ liệu đã đọc. Probe tái hiện B ghi version 2 chứa `initial,B`, A ghi version 3 chứa `initial,A`: mất điểm B. Cùng kiểu ghi stale payload có thể phục hồi generation cũ sau reset.

Cần đọc payload/version cùng một lần, áp lại mutation khi xung đột và kiểm tra generation trước khi ghép kết quả matching. Nếu bỏ qua, concurrent ingest/matching/reset có thể mất GPS hoặc lùi trạng thái xe.

### 2. P1 — Hai API không dùng cùng nguồn vị trí khi request thiếu tọa độ

Source: `backend/app/api/v1/ranking.py:135`; tương tự trong candidate evaluation và driver demand. Cấu hình `frontend/nginx.conf` cân bằng tới hai API.

Location fallback đọc `app.state.driver_state_store` trong bộ nhớ từng API, thay vì trạng thái chia sẻ qua manager/Redis. GPS vào API 1 không tự xuất hiện trong API 2; reset cũng không xóa bản sao cũ này. Một client đã gửi GPS rồi chỉ gửi driver ID có thể nhận `LOCATION_UNAVAILABLE` hoặc dùng vị trí trước reset. Luồng UI luôn gửi tọa độ explicit tránh được phần lớn tình huống này, nhưng API contract vẫn bị lỗi.

Cần tải shared state qua manager rồi dùng common location resolver; giữ ưu tiên tọa độ explicit. Finding được xác nhận qua source/config, chưa thử lỗi này trên hai replica live.

### 3. P1 — Drawer cho phép dẫn đường tới trạm bị backend đánh dấu không hợp lệ

Source: `backend/app/static/demo/js/ui/drawer_renderer.js:211`, `backend/app/static/demo/js/ui/driver_controller.js:1060`.

Điều kiện nút dùng `ranked?.eligible !== false`; ranked candidate không có field eligibility, còn một station không được rank sẽ có `ranked` undefined. Vì vậy card `cand.eligible=false`, kể cả `INCOMPATIBLE`, vẫn có nút dẫn đường. Handler chỉ kiểm tra tồn tại trạm và tính route; không xác nhận khả năng phục vụ. Probe tái hiện nút xuất hiện và navigation được commit cho trạm không hợp lệ.

Cần giữ identity station/service, dùng eligibility từ backend cho nút và xác nhận lại evidence trước khi chọn. Không xem một route tính được là bằng chứng trạm sạc/đổi pin phù hợp. Nếu bỏ qua, xe có thể tới một trạm không phục vụ được mình.

### 4. P1 — Kế hoạch “đến B rồi sạc” tạo pin dương dù xe không tới được B

Source: `backend/app/static/demo/js/ui/driver_controller.js:1262`.

Dự báo SOC sau chuyến và range bị ép tối thiểu 1. Với SOC 1%, VF3 và chuyến 34,6 km, năng lượng dự báo không đủ tới B nhưng payload gửi backend vẫn có SOC 1% và range dương tại B. Probe xác nhận trường hợp này. Backend vì vậy đang đánh giá một trạng thái tương lai không thể đạt được.

Cần xác nhận khả năng tới B trước khi đánh giá trạm sau B; không ép giá trị âm/không đủ năng lượng thành nguồn pin khả dụng. Nếu bỏ qua, lựa chọn sạc sau chuyến có thể không thực hiện được.

### 5. P2 — Tránh ùn tắc lấy cả dữ liệu cũ hoặc dữ liệu tương lai

Source: `backend/app/services/snapshots/repository.py:117`, caller `backend/app/api/v1/ranking.py:163`.

SQL lọc `delay_factor >= threshold` trước khi chọn snapshot mới nhất. Đường từng tắc tại t1 nhưng thông tại t2 vẫn có thể bị coi là tắc vì hàng t2 đã bị loại. Query cũng thiếu giới hạn thời gian của request, nên đánh giá lịch sử có thể dùng dữ liệu tương lai.

Cần chọn snapshot mới nhất của mỗi segment **tại hoặc trước thời điểm request**, rồi mới lọc mức tắc đường. Finding được xác nhận từ cấu trúc SQL/caller, chưa làm thử nghiệm thay đổi snapshot trong database live.

### 6. P2 — Ràng buộc tuyến không được truyền đồng bộ

Source: `backend/app/services/candidate/service.py:163`; frontend `navigateViaStationId` và `backend/app/static/demo/js/api.js:142`.

Tuyến trực tiếp dùng làm baseline detour không nhận `request.constraints`, trong khi tuyến qua trạm có nhận. Probe ghi 61 lời gọi: direct không constraint, 60 station legs có constraint. Phép so sánh detour đang so hai chính sách khác nhau. Khi chọn trạm, frontend còn tính lại route chỉ với vehicle category, không truyền ràng buộc tránh tắc của recommendation; geometry hiển thị có thể khác tuyến đã được chấm điểm.

Cần dùng cùng constraints cho direct/via và giữ đúng route policy khi hiển thị/dẫn đường. Không sửa bằng cách phụ thuộc trực tiếp GraphHopper trong business layer. Nếu bỏ qua, detour và đường người dùng thấy có thể không tương ứng với kết quả ranking.

### 7. P2 — Map matching đảo thứ tự GPS khi timezone khác nhau

Source: `backend/app/services/map_matching/service.py:18`, timestamp contract trong `models.py`.

Timestamp được sort như chuỗi. `2026-10-12T07:00:00+07:00` thực tế sớm hơn `2026-10-12T00:01:00Z`, nhưng sort hiện tại gửi điểm sau trước. Probe xác nhận thứ tự engine nhận và output bị đảo.

Cần validate/normalize timestamp thành thời điểm có timezone rồi sort theo thời điểm, giữ representation trả về nếu contract yêu cầu. Nếu bỏ qua, trace có thể đi ngược thứ tự và matching sai khi nhận nguồn GPS khác timezone.

### 8. P2 — Không biết thời gian chờ nhưng UI hiển thị 0 phút

Source: `backend/app/static/demo/js/ui/drawer_renderer.js:85`.

`observed_queue_wait_s=null` vẫn thỏa điều kiện khác undefined; `Math.round(null / 60)` thành 0. Backend có thể đang dùng `effective_queue_wait_s=5400` với giả định 90 phút cho queue thiếu dữ liệu, nhưng card nói “0p chờ”. Probe tái hiện đúng tổ hợp đó.

Cần hiển thị effective wait và provenance/nhãn ước tính; giữ null là không biết, không biến thành queue trống. Nếu bỏ qua, người dùng thấy thời gian chờ dễ gây quyết định sai dù final cost backend vẫn đúng.

## Căn cứ và thứ tự sửa tiếp

`backend_runtime_probes.py/json` tái hiện mất GPS, constraints mismatch và timestamp ordering bằng dependency mocks; `frontend_runtime_probes.mjs/json` tái hiện queue null, lựa chọn trạm không hợp lệ và forecast pin dương. Các probe chỉ đọc catalog canonical, không ghi live state hoặc Dataset. Source/config được đọc trực tiếp để xác nhận các findings còn lại.

Ưu tiên nhóm shared GPS/location và eligibility/arrival feasibility trước; sau đó sửa causal congestion/constraint handoff; cuối cùng timezone và queue display. Các sửa này cần regression cho chính tình huống đã nêu, không chỉ chạy lại suite đang PASS.

## Phạm vi và giới hạn

Đã đọc các luồng chính: app/lifespan/config, demand/energy, routing/matching, candidate eligibility, snapshot ingestion/resolution, ranking/orchestration, shared driver persistence, familiarity privacy/history boundaries, replay/controller/bindings/renderers và tests liên quan. Không đọc mọi dòng của toàn repository. Chưa audit đầy đủ segment-resolver/similarity internals, mọi script đánh giá hoặc mô phỏng tải lớn/concurrency bằng dịch vụ thật.

Các giới hạn đã ghi nhận trước đây (single-host data plane, motorcycle dùng car_access, không có end-user auth trên recommend khi familiarity tắt, fanout latency, physics chưa hiệu chuẩn) không được đếm thành lỗi mới. Không kích hoạt familiarity, không mở Week 6 và không thêm dependency/hạ tầng. Bản vá cảnh báo đã được kiểm chứng; tám lỗi còn mở không được che bằng kết quả unit tests PASS.
