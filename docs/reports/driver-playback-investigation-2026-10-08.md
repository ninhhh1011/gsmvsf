# Điều tra xe dừng và trạm cũ — 2026-10-08

## Kết luận và phạm vi

Nguyên nhân trực tiếp của hiện tượng dừng gần 30 giây là replay gửi request quá nhanh, chạm rate limit; middleware **trong container đang chạy** biến lỗi 429 thành HTTP 500. Frontend chuyển sang ERROR rồi thoát vòng playback. Không tìm thấy bằng chứng reset dữ liệu mỗi 30 giây gây ra lần dừng này.

Đây là báo cáo điều tra và phương án sửa, chưa thay đổi code ứng dụng, cấu hình hay restart/rebuild container. Dataset V1 không được sửa. Không triển khai Week 6. Checkout: `b0484ed`; có sẵn thay đổi chưa commit ở `domain/vehicle-catalog.js`, được giữ nguyên. Tracker hiện nằm ở `docs/PHASE_TRACKER.md`; đường dẫn tracker tại root và các tài liệu tuần cũ trong AGENTS.md không còn tồn tại.

## Bằng chứng trực tiếp trên runtime

- Log phiên trong ảnh: `POST /api/v1/drivers/driver_muz6blg6/location` trả **500** trên api_2; traceback kết thúc tại middleware với `fastapi.exceptions.HTTPException: 429: Rate limit exceeded. Try again later.`
- Gọi GraphHopper qua `http://127.0.0.1:3000/api/v1/route` với A=(20.9849,105.7935), B=(21.0285,105.8542), profile EV_CAR. Route dài **9438.434 m**, replay sinh đúng **648 điểm**, khớp tổng số điểm trong ảnh.
- Chạy chính `ApiClient` và `TrajectoryReplayController` hiện tại với driver diagnostic riêng, tốc độ mặc định 5x, map stub không có DOM. Gửi GPS tới backend/Redis/PostGIS/GraphHopper thật; không mock API, không chạy recommendation trong probe này.
- Kết quả: **199** điểm thành công; request tiếp theo lỗi **HTTP 500** ở **27.488 giây**; kết thúc đo **27.701 giây**, `currentIndex=199`, `state=ERROR`, vẫn còn 449 điểm.
- Log runtime của driver diagnostic xác nhận cùng exception rate limit. Đây là tái hiện cơ chế lỗi, không khẳng định cùng thời gian hoặc chỉ số 159 của phiên gốc; phiên gốc còn gửi recommendation và có thể có request khác dùng chung quota.
- `docker compose exec -T api_2 python -c "import inspect; from backend.app.api.v1.middleware import RateLimitMiddleware; print(inspect.getsource(RateLimitMiddleware))"` cho thấy container vẫn **raise HTTPException**. Source hiện tại đã **return JSONResponse(429)** kèm `Retry-After`. Các API dùng COPY source trong Dockerfile, không bind mount backend: sửa file trên host không cập nhật container.

## Các lỗi xác nhận bằng probe hành vi

| Lỗi | Nguồn | Kết quả đo / cơ chế |
|---|---|---|
| Request quá nhanh | `js/replay.js:430`, `core/constants.py:58` | Delay mặc định 500/5=100 ms sau mỗi bước; giới hạn 100 request/phút trên mỗi API theo client IP. Request từ Nginx dùng chung IP proxy; quota không theo driver. Recommendation/route cũng dùng quota này. |
| Nhánh retry không thể cứu lỗi HTTP | `js/replay.js:379`, `js/replay.js:412` | `step()` đặt ERROR; vòng loop kiểm tra khác PLAYING và break **trước** nhánh retry. Probe trả 429: chỉ **1 lần gọi**, index 0, ERROR. Chỉ đổi auto-resume khi load không sửa được lỗi này. |
| Có hai loop sau Pause → Play | `js/replay.js:389`, `js/replay.js:440` | Giữ request đầu chưa trả, gọi Play → Pause → Play: có **2 invocation playback còn hoạt động**, dù guard tạm thời vẫn giữ 1 ingestion. Pause không thay loop token; clearTimeout không resolve Promise đang ngủ. Đây là nguy cơ sở hữu timer/loop sai, không phải bằng chứng 2 GPS đồng thời trong probe này. |
| Tuyến mới làm thời gian đi lùi | `js/replay.js:204–211` | `baseTime` được tính lại theo độ dài mỗi tuyến. Probe tuyến ngắn rồi dài: điểm cuối tuyến cũ `06:49:41.967Z`, điểm đầu tuyến mới `06:31:26.970Z`, lùi khoảng **18 phút 15 giây**. Backend trả STALE_OBSERVATION nếu timestamp nhỏ hơn điểm đã nhận. |
| HTTP 200 stale vẫn được tính là tiến độ | `api/v1/realtime.py:293`, `js/replay.js:320–367` | Probe response `status=STALE_OBSERVATION`: replay vẫn trả true, gọi downstream và tăng index lên 1. HTTP thành công chưa có nghĩa GPS được chấp nhận. Điều này có thể khiến map/SOC đi theo dữ liệu frontend mà backend từ chối. |
| Phản hồi trạm cũ ghi đè lựa chọn mới | `ui/driver_controller.js:748–786`, `:972–1029` | Giữ leg 2 của evaluation OLD, chọn NEW thành công, rồi trả leg 2 OLD: `_selectedStationId=NEW`, `_navigationLocked=true`, nhưng `lastRecommendedStationId` đổi **NEW → OLD**. Generation chỉ bảo vệ vòng đời driver, không thay đổi khi chọn trạm. Probe dùng API deferred, không phải chứng cứ backend ranking chọn sai. |
| Điểm cuối không hoàn tất Driver | `js/replay.js:348–370`, `ui/driver_controller.js:594` | Callback chạy trước increment index. Probe 1 điểm đã nhận: replay **COMPLETE**, driver vẫn **TRIP_ACTIVE**. Kiểm tra isReplayComplete bên trong callback luôn nhìn index cũ ở bước cuối. |

## Đường luồng còn thiếu đồng bộ, xác nhận bằng đọc code

- `_updateCustomRoute()` đổi điểm B và geometry hiển thị khi đang chạy, nhưng không thay observations replay hoặc reset segment progress. Xe vẫn có thể chạy theo tuyến cũ dù map đã vẽ tuyến mới.
- `_triggerReroute()` luôn route tới B, kể cả đang khóa ghé trạm; nó cũng chỉ đổi geometry theo dõi, không đổi nguồn mô phỏng. Sau khi await reroute, `_onReplayStep()` còn dùng projection tính từ tuyến trước để slice tuyến mới. Cần kiểm thử riêng trước khi sửa, không coi đây là nguyên nhân trực tiếp đã đo của lần dừng trong ảnh.
- Khi navigation bị khóa, `_evaluateAtCurrentPosition()` bỏ qua refresh; recommendation trước đó có thể cũ. Không tự động đổi trạm là chủ đích đang có trong code; không nên giải quyết freshness bằng cách tự unlock hoặc tự chọn top 1 mỗi lần refresh.
- Các đường thực sự gọi `loadFromPolyline()` là startTrip và lựa chọn trạm chủ động. Periodic recommendation hiện tại vẽ tuyến đề xuất nhưng không tự gọi navigateViaStationId. Vì vậy không có bằng chứng một vòng tự chọn trạm mỗi 30 giây trong phiên pin 83%; đã xác nhận race phản hồi cũ riêng ở trên.

## Vì sao mốc 30 giây dễ gây hiểu nhầm

`RealtimeSimulator` chạy mỗi 30 giây, ghi snapshot trạm/queue/traffic qua ingestion; không reset GPS hoặc replay. Context matching 30 giây là cửa sổ quan sát, không phải TTL. Gap reset xảy ra khi **khoảng cách event-time giữa hai GPS >60 giây**; TTL driver là **3600 giây**. Không nên tắt simulator hoặc kéo dài TTL để chữa lỗi rate limit.

## Phương án sửa triệt để, theo thứ tự

1. **Đồng bộ runtime với source đã được kiểm tra.** Rebuild/recreate hai API, kiểm tra cả hai trả 429 JSON + Retry-After; reload Nginx nếu container IP thay đổi. Chỉ cập nhật ứng dụng, giữ DB/Redis/GraphHopper và Dataset. Rebuild riêng vẫn chưa đủ: quota còn đó và frontend chưa xử lý đúng.
2. **Một loop và một request GPS đang xử lý.** Tách token sở hữu playback khỏi generation dữ liệu. Pause/load/reset phải kết thúc wait có thể cancel và loại bỏ loop cũ; resume không tạo loop thứ hai. Không mở khóa in-flight bằng reset boolean trước khi request cũ đã kết thúc. Giữ hành vi pause thường cho phép bước được nhận đang xử lý hoàn tất.
3. **Giới hạn tốc độ request và retry hữu hạn.** API client giữ status và Retry-After. Replay chỉ retry lỗi tạm thời với cùng observation/payload, chờ theo Retry-After/backoff, tối đa 3 lần thử cho mỗi bước; không skip index, không reset session để né quota. Hết budget thì dừng với lỗi rõ ràng và quyền tiếp tục của người dùng. Áp dụng thời gian chờ quota cho recommendation/route để không tiếp tục bắn request trong cooldown.
4. **Đặt ngân sách request có thể đo.** Điểm xuất phát để thử: GPS cách nhau ít nhất 1.5 giây wall time (~40/phút), recommendation cách nhau ít nhất 5 giây (12/phút), hai leg preview tối đa 24/phút; có dư địa so với 100/phút trên một API. Điều kiện 50m không được bypass khoảng cách tối thiểu. Đây là đề xuất demo, chưa phải SLA; nhiều tab vẫn có thể chạm quota và phải được xử lý. Không bỏ rate limit hoặc thêm Redis limiter/streaming ngoài phạm vi.
5. **Tuyến và event-time nhất quán.** Giữ clock tăng liên tục trong cùng phiên mô phỏng; điểm đầu tuyến mới phải sau GPS đã chấp nhận. Timestamp Dataset lịch sử vẫn giữ nguyên. Không tính STALE_OBSERVATION là bước đã nhận; dừng lỗi dữ liệu thay vì retry mãi timestamp stale. Chỉ đổi route/replay/progress cùng nhau khi người dùng đổi đích hoặc chọn tuyến; update recommendation chỉ là preview. Reroute tôn trọng trạm đã chọn, rồi tính projection trên tuyến mới.
6. **Chặn phản hồi cũ ở mọi commit async.** Dùng revision lựa chọn/tuyến, kiểm tra lại sau mỗi await; chỉ response của revision hiện hành được cập nhật trạm/geometry. Giữ riêng trạm người dùng chọn và top 1 đang đề xuất. Refresh không tự route về trạm cũ, không tự unlock và không tự gọi refresh đệ quy. Chỉ combined backend workflow retry 409 candidate-state một lần như contract hiện có.
7. **Hoàn tất từ bước đã được xác nhận.** Truyền tiến độ/completion của bước được nhận cho Driver hoặc xử lý replay COMPLETE đúng một lần; không kiểm tra index cũ và không tự wrap về điểm A khi đã tới B.

## Kiểm tra bắt buộc trước khi gọi là đã sửa

- Tái hiện tuyến 648 điểm trên stack thật đến B, có recommendation và snapshot tick; chạy đủ vượt nhiều cửa sổ rate limit, không chỉ 30 giây đầu. Mọi điểm được nhận có timestamp tăng, index không reset và Driver chuyển COMPLETE đúng một lần.
- Inject 429, 503/network timeout, lỗi dữ liệu 4xx và STALE_OBSERVATION: kiểm tra cooldown, giới hạn lần thử, không skip GPS và không retry vô hạn.
- Pause/Play nhanh lúc ingest và lúc timer đang chờ; reset/load/switch mode lúc request đang chờ: tối đa 1 loop có quyền chạy và 1 GPS in-flight, response cũ không publish.
- Chọn NEW trong lúc evaluation OLD chưa trả; thay B trong lúc route đang tính: response cũ không đổi lựa chọn hoặc geometry, replay đi tới đúng đích hiện hành.
- Thử pin đủ, pin thấp, khóa ghé trạm và trạm đổi trạng thái: refresh không điều khiển tuyến ngoài ý muốn; lỗi dependency và conflict hiện rõ.
- Không thêm công nghệ mới và không thay snapshot/label contracts. Khi triển khai thay đổi ownership/approach, ghi ADR phù hợp; báo cáo này chưa thay đổi kiến trúc.

## Kết quả kiểm tra hiện tại

- `node --test tests/frontend/test_replay_state_machine.mjs tests/frontend/test_mode_isolation.mjs`: **37 PASS**. Những test có sẵn chưa bao phủ các probe lỗi ở trên.
- `DEBUG=false`, `PYTHONDONTWRITEBYTECODE=1`, `python -B -m pytest backend/tests/test_security.py -q --basetemp=runtime/migration/pytest-driver-investigation`: **7 PASS, 1 SKIP**; test local xác nhận middleware trong source đã đúng, không chứng minh container đã cập nhật.
- `npm test`: **122 PASS, 4 FAIL / 126**. Ba test catalog lỗi `window is not defined`; một test ranh giới controller/domain cũng phát hiện `window`. Cả bốn liên quan thay đổi có sẵn chưa commit ở `vehicle-catalog.js`, không được sửa trong điều tra này. Output lưu `runtime/driver-playback-frontend-tests.txt`.
- Không claim toàn bộ hệ thống xanh hoặc bug đã sửa. Không chạy lại validator Dataset vì không thay Dataset hay backend business logic.
# Điều tra xe dừng và trạm cũ — 2026-10-08

## Kết luận và phạm vi

Nguyên nhân trực tiếp của hiện tượng dừng gần 30 giây là replay gửi request quá nhanh, chạm rate limit; middleware **trong container đang chạy** biến lỗi 429 thành HTTP 500. Frontend chuyển sang ERROR rồi thoát vòng playback. Không tìm thấy bằng chứng reset dữ liệu mỗi 30 giây gây ra lần dừng này.

Đây là báo cáo điều tra và phương án sửa, chưa thay đổi code ứng dụng, cấu hình hay restart/rebuild container. Dataset V1 không được sửa. Không triển khai Week 6. Checkout: `b0484ed`; có sẵn thay đổi chưa commit ở `domain/vehicle-catalog.js`, được giữ nguyên. Tracker hiện nằm ở `docs/PHASE_TRACKER.md`; đường dẫn tracker tại root và các tài liệu tuần cũ trong AGENTS.md không còn tồn tại.

## Bằng chứng trực tiếp trên runtime

- Log phiên trong ảnh: `POST /api/v1/drivers/driver_muz6blg6/location` trả **500** trên api_2; traceback kết thúc tại middleware với `fastapi.exceptions.HTTPException: 429: Rate limit exceeded. Try again later.`
- Gọi GraphHopper qua `http://127.0.0.1:3000/api/v1/route` với A=(20.9849,105.7935), B=(21.0285,105.8542), profile EV_CAR. Route dài **9438.434 m**, replay sinh đúng **648 điểm**, khớp tổng số điểm trong ảnh.
- Chạy chính `ApiClient` và `TrajectoryReplayController` hiện tại với driver diagnostic riêng, tốc độ mặc định 5x, map stub không có DOM. Gửi GPS tới backend/Redis/PostGIS/GraphHopper thật; không mock API, không chạy recommendation trong probe này.
- Kết quả: **199** điểm thành công; request tiếp theo lỗi **HTTP 500** ở **27.488 giây**; kết thúc đo **27.701 giây**, `currentIndex=199`, `state=ERROR`, vẫn còn 449 điểm.
- Log runtime của driver diagnostic xác nhận cùng exception rate limit. Đây là tái hiện cơ chế lỗi, không khẳng định cùng thời gian hoặc chỉ số 159 của phiên gốc; phiên gốc còn gửi recommendation và có thể có request khác dùng chung quota.
- `docker compose exec -T api_2 python -c "import inspect; from backend.app.api.v1.middleware import RateLimitMiddleware; print(inspect.getsource(RateLimitMiddleware))"` cho thấy container vẫn **raise HTTPException**. Source hiện tại đã **return JSONResponse(429)** kèm `Retry-After`. Các API dùng COPY source trong Dockerfile, không bind mount backend: sửa file trên host không cập nhật container.

## Các lỗi xác nhận bằng probe hành vi

| Lỗi | Nguồn | Kết quả đo / cơ chế |
|---|---|---|
| Request quá nhanh | `js/replay.js:430`, `core/constants.py:58` | Delay mặc định 500/5=100 ms sau mỗi bước; giới hạn 100 request/phút trên mỗi API theo client IP. Request từ Nginx dùng chung IP proxy; quota không theo driver. Recommendation/route cũng dùng quota này. |
| Nhánh retry không thể cứu lỗi HTTP | `js/replay.js:379`, `js/replay.js:412` | `step()` đặt ERROR; vòng loop kiểm tra khác PLAYING và break **trước** nhánh retry. Probe trả 429: chỉ **1 lần gọi**, index 0, ERROR. Chỉ đổi auto-resume khi load không sửa được lỗi này. |
| Có hai loop sau Pause → Play | `js/replay.js:389`, `js/replay.js:440` | Giữ request đầu chưa trả, gọi Play → Pause → Play: có **2 invocation playback còn hoạt động**, dù guard tạm thời vẫn giữ 1 ingestion. Pause không thay loop token; clearTimeout không resolve Promise đang ngủ. Đây là nguy cơ sở hữu timer/loop sai, không phải bằng chứng 2 GPS đồng thời trong probe này. |
| Tuyến mới làm thời gian đi lùi | `js/replay.js:204–211` | `baseTime` được tính lại theo độ dài mỗi tuyến. Probe tuyến ngắn rồi dài: điểm cuối tuyến cũ `06:49:41.967Z`, điểm đầu tuyến mới `06:31:26.970Z`, lùi khoảng **18 phút 15 giây**. Backend trả STALE_OBSERVATION nếu timestamp nhỏ hơn điểm đã nhận. |
| HTTP 200 stale vẫn được tính là tiến độ | `api/v1/realtime.py:293`, `js/replay.js:320–367` | Probe response `status=STALE_OBSERVATION`: replay vẫn trả true, gọi downstream và tăng index lên 1. HTTP thành công chưa có nghĩa GPS được chấp nhận. Điều này có thể khiến map/SOC đi theo dữ liệu frontend mà backend từ chối. |
| Phản hồi trạm cũ ghi đè lựa chọn mới | `ui/driver_controller.js:748–786`, `:972–1029` | Giữ leg 2 của evaluation OLD, chọn NEW thành công, rồi trả leg 2 OLD: `_selectedStationId=NEW`, `_navigationLocked=true`, nhưng `lastRecommendedStationId` đổi **NEW → OLD**. Generation chỉ bảo vệ vòng đời driver, không thay đổi khi chọn trạm. Probe dùng API deferred, không phải chứng cứ backend ranking chọn sai. |
| Điểm cuối không hoàn tất Driver | `js/replay.js:348–370`, `ui/driver_controller.js:594` | Callback chạy trước increment index. Probe 1 điểm đã nhận: replay **COMPLETE**, driver vẫn **TRIP_ACTIVE**. Kiểm tra isReplayComplete bên trong callback luôn nhìn index cũ ở bước cuối. |

## Đường luồng còn thiếu đồng bộ, xác nhận bằng đọc code

- `_updateCustomRoute()` đổi điểm B và geometry hiển thị khi đang chạy, nhưng không thay observations replay hoặc reset segment progress. Xe vẫn có thể chạy theo tuyến cũ dù map đã vẽ tuyến mới.
- `_triggerReroute()` luôn route tới B, kể cả đang khóa ghé trạm; nó cũng chỉ đổi geometry theo dõi, không đổi nguồn mô phỏng. Sau khi await reroute, `_onReplayStep()` còn dùng projection tính từ tuyến trước để slice tuyến mới. Cần kiểm thử riêng trước khi sửa, không coi đây là nguyên nhân trực tiếp đã đo của lần dừng trong ảnh.
- Khi navigation bị khóa, `_evaluateAtCurrentPosition()` bỏ qua refresh; recommendation trước đó có thể cũ. Không tự động đổi trạm là chủ đích đang có trong code; không nên giải quyết freshness bằng cách tự unlock hoặc tự chọn top 1 mỗi lần refresh.
- Các đường thực sự gọi `loadFromPolyline()` là startTrip và lựa chọn trạm chủ động. Periodic recommendation hiện tại vẽ tuyến đề xuất nhưng không tự gọi navigateViaStationId. Vì vậy không có bằng chứng một vòng tự chọn trạm mỗi 30 giây trong phiên pin 83%; đã xác nhận race phản hồi cũ riêng ở trên.

## Vì sao mốc 30 giây dễ gây hiểu nhầm

`RealtimeSimulator` chạy mỗi 30 giây, ghi snapshot trạm/queue/traffic qua ingestion; không reset GPS hoặc replay. Context matching 30 giây là cửa sổ quan sát, không phải TTL. Gap reset xảy ra khi **khoảng cách event-time giữa hai GPS >60 giây**; TTL driver là **3600 giây**. Không nên tắt simulator hoặc kéo dài TTL để chữa lỗi rate limit.

## Phương án sửa triệt để, theo thứ tự

1. **Đồng bộ runtime với source đã được kiểm tra.** Rebuild/recreate hai API, kiểm tra cả hai trả 429 JSON + Retry-After; reload Nginx nếu container IP thay đổi. Chỉ cập nhật ứng dụng, giữ DB/Redis/GraphHopper và Dataset. Rebuild riêng vẫn chưa đủ: quota còn đó và frontend chưa xử lý đúng.
2. **Một loop và một request GPS đang xử lý.** Tách token sở hữu playback khỏi generation dữ liệu. Pause/load/reset phải kết thúc wait có thể cancel và loại bỏ loop cũ; resume không tạo loop thứ hai. Không mở khóa in-flight bằng reset boolean trước khi request cũ đã kết thúc. Giữ hành vi pause thường cho phép bước được nhận đang xử lý hoàn tất.
3. **Giới hạn tốc độ request và retry hữu hạn.** API client giữ status và Retry-After. Replay chỉ retry lỗi tạm thời với cùng observation/payload, chờ theo Retry-After/backoff, tối đa 3 lần thử cho mỗi bước; không skip index, không reset session để né quota. Hết budget thì dừng với lỗi rõ ràng và quyền tiếp tục của người dùng. Áp dụng thời gian chờ quota cho recommendation/route để không tiếp tục bắn request trong cooldown.
4. **Đặt ngân sách request có thể đo.** Điểm xuất phát để thử: GPS cách nhau ít nhất 1.5 giây wall time (~40/phút), recommendation cách nhau ít nhất 5 giây (12/phút), hai leg preview tối đa 24/phút; có dư địa so với 100/phút trên một API. Điều kiện 50m không được bypass khoảng cách tối thiểu. Đây là đề xuất demo, chưa phải SLA; nhiều tab vẫn có thể chạm quota và phải được xử lý. Không bỏ rate limit hoặc thêm Redis limiter/streaming ngoài phạm vi.
5. **Tuyến và event-time nhất quán.** Giữ clock tăng liên tục trong cùng phiên mô phỏng; điểm đầu tuyến mới phải sau GPS đã chấp nhận. Timestamp Dataset lịch sử vẫn giữ nguyên. Không tính STALE_OBSERVATION là bước đã nhận; dừng lỗi dữ liệu thay vì retry mãi timestamp stale. Chỉ đổi route/replay/progress cùng nhau khi người dùng đổi đích hoặc chọn tuyến; update recommendation chỉ là preview. Reroute tôn trọng trạm đã chọn, rồi tính projection trên tuyến mới.
6. **Chặn phản hồi cũ ở mọi commit async.** Dùng revision lựa chọn/tuyến, kiểm tra lại sau mỗi await; chỉ response của revision hiện hành được cập nhật trạm/geometry. Giữ riêng trạm người dùng chọn và top 1 đang đề xuất. Refresh không tự route về trạm cũ, không tự unlock và không tự gọi refresh đệ quy. Chỉ combined backend workflow retry 409 candidate-state một lần như contract hiện có.
7. **Hoàn tất từ bước đã được xác nhận.** Truyền tiến độ/completion của bước được nhận cho Driver hoặc xử lý replay COMPLETE đúng một lần; không kiểm tra index cũ và không tự wrap về điểm A khi đã tới B.

## Kiểm tra bắt buộc trước khi gọi là đã sửa

- Tái hiện tuyến 648 điểm trên stack thật đến B, có recommendation và snapshot tick; chạy đủ vượt nhiều cửa sổ rate limit, không chỉ 30 giây đầu. Mọi điểm được nhận có timestamp tăng, index không reset và Driver chuyển COMPLETE đúng một lần.
- Inject 429, 503/network timeout, lỗi dữ liệu 4xx và STALE_OBSERVATION: kiểm tra cooldown, giới hạn lần thử, không skip GPS và không retry vô hạn.
- Pause/Play nhanh lúc ingest và lúc timer đang chờ; reset/load/switch mode lúc request đang chờ: tối đa 1 loop có quyền chạy và 1 GPS in-flight, response cũ không publish.
- Chọn NEW trong lúc evaluation OLD chưa trả; thay B trong lúc route đang tính: response cũ không đổi lựa chọn hoặc geometry, replay đi tới đúng đích hiện hành.
- Thử pin đủ, pin thấp, khóa ghé trạm và trạm đổi trạng thái: refresh không điều khiển tuyến ngoài ý muốn; lỗi dependency và conflict hiện rõ.
- Không thêm công nghệ mới và không thay snapshot/label contracts. Khi triển khai thay đổi ownership/approach, ghi ADR phù hợp; báo cáo này chưa thay đổi kiến trúc.

## Kết quả kiểm tra hiện tại

- `node --test tests/frontend/test_replay_state_machine.mjs tests/frontend/test_mode_isolation.mjs`: **37 PASS**. Những test có sẵn chưa bao phủ các probe lỗi ở trên.
- `DEBUG=false`, `PYTHONDONTWRITEBYTECODE=1`, `python -B -m pytest backend/tests/test_security.py -q --basetemp=runtime/migration/pytest-driver-investigation`: **7 PASS, 1 SKIP**; test local xác nhận middleware trong source đã đúng, không chứng minh container đã cập nhật.
- `npm test`: **122 PASS, 4 FAIL / 126**. Ba test catalog lỗi `window is not defined`; một test ranh giới controller/domain cũng phát hiện `window`. Cả bốn liên quan thay đổi có sẵn chưa commit ở `vehicle-catalog.js`, không được sửa trong điều tra này. Output lưu `runtime/driver-playback-frontend-tests.txt`.
- Không claim toàn bộ hệ thống xanh hoặc bug đã sửa. Không chạy lại validator Dataset vì không thay Dataset hay backend business logic.
