# Driver Mode duy nhất — điều tra, thiết kế đề xuất và bàn giao

Ngày: 2026-10-08. Trạng thái: báo cáo brainstorming cho agent triển khai; **chưa triển khai, chưa chứng nhận hết lỗi**. Người dùng yêu cầu chỉ điều tra và viết hướng xử lý, không sửa ứng dụng. Tài liệu này là đầu ra của yêu cầu đó; các quyết định đề xuất bên dưới không được ghi thành ADR Approved trước khi được chốt.

## 1. Yêu cầu đã xác nhận

1. Chỉ có một giao diện **Driver Mode**, bỏ bộ chuyển Driver / Simulation / Debug.
2. Bỏ danh sách tình huống mẫu và luồng scenario khỏi ứng dụng.
3. Bấm **Tìm đường** phải tìm và hiển thị **tối đa 5 trạm phù hợp, kể cả pin còn đủ**. Không hứa có đủ 5 nếu backend chỉ tìm được ít hơn.
4. Rê chuột vào trạm/hạng trên bản đồ phải thấy thông tin trực quan giống thẻ tham chiếu: xe → trạm, thời gian chờ/dịch vụ, trạm → B, đi vòng và tổng thời gian. Có thể trình bày gọn hơn ảnh.
5. Có nút **H3** riêng, mặc định tắt; bật/tắt chỉ đổi lớp hiển thị, không thay tuyến hay ranking.
6. Agent hiện tại không sửa code, config, container, dữ liệu hay các bản sửa đang dở. Agent tiếp theo phải có bằng chứng kiểm thử cho những lỗi đã biết và các tương tác mới.

### Ranh giới “xóa scenario”

Người dùng muốn bỏ 8 tình huống mẫu khỏi giao diện và chưa hiểu khác biệt với Dataset V1. Đã giải thích: dữ liệu scenario UI là dữ liệu mẫu để điều khiển demo; Dataset V1 là dữ liệu chuẩn và cơ sở kiểm tra đúng/sai. **Không có ủy quyền xóa Dataset V1.**

Phạm vi đề xuất: bỏ UI scenario, request tải `demo/data/scenarios.json`, phụ thuộc vào scenario/trip mẫu khi khởi tạo Driver, và fixture được đóng gói chỉ phục vụ màn hình Debug. Giữ toàn bộ `dataset_v1/`, labels và kiểm thử offline. Việc không còn menu scenario không đồng nghĩa xóa các ca kiểm thử tự động. Không dùng lệnh xóa theo từ khóa `scenario` trên toàn repo.

## 2. Baseline và độ tin cậy của bằng chứng

- HEAD lúc điều tra: `b0484ed`. Workspace có thay đổi chưa commit trong `backend/Dockerfile`, `backend/pyproject.toml`, `api.js`, `replay.js`, `cockpit_bindings.js`, `cockpit_renderer.js`, `driver_controller.js`, và test mới `tests/frontend/test_driver_playback_probe.mjs`. Đây là đầu vào được đọc, không phải thay đổi do lượt brainstorming này tạo ra.
- Báo cáo trước: [driver-playback-investigation-2026-10-08.md](driver-playback-investigation-2026-10-08.md). Bằng chứng live cũ: tuyến 648 điểm, 199 GPS được nhận, HTTP 500 sau 27,7 giây; runtime cũ ném HTTPException 429 ở middleware. **Không áp số liệu/line number cũ thành kết quả của bản sửa đang dở.**
- Kiểm tra đọc-only ở lượt này: `node --test tests/frontend/test_driver_playback_probe.mjs tests/frontend/test_replay_state_machine.mjs tests/frontend/test_route_familiarity_overlay.mjs` → **26 PASS / 0 FAIL**. Không chạy lại toàn bộ hệ thống hay thay runtime ở lượt này.
- Test xanh này chưa đủ: một số test không thực sự tạo race mà tên test mô tả; các vấn đề đọc-code bên dưới cần regression test trước khi sửa.
- Source of truth dự án đã được đọc ở lượt điều tra trước. Tracker thực tế là `docs/PHASE_TRACKER.md`; không có tracker root. Không bắt đầu Week 6, thêm công nghệ, sửa routing engine hoặc thay contract labels/snapshot để hoàn thành giao diện này.

## 3. Chọn cách hợp nhất

| Cách | Tác động | Đánh giá |
|---|---|---|
| **Giữ Driver controller, chuyển các phần hiển thị hữu ích sang Driver, bỏ runtime Debug** | Tái sử dụng map, renderers, API và H3 hiện có; một nơi sở hữu hành trình | **Đề xuất** |
| Chỉ giấu tab Debug, vẫn khởi tạo cả hai controller | Ít thay HTML nhưng hai bộ state/listener/request vẫn tồn tại | Không đáp ứng mục tiêu giảm xung đột |
| Viết lại frontend bằng framework mới | Phạm vi lớn, bỏ nhiều hành vi đã có, tăng rủi ro migration | Không có nhu cầu chứng minh |

Mục tiêu không phải ghép nguyên hai panel vào một màn hình. Chỉ giữ: chọn A/B, xe, SOC; tìm đường; Top 5; xem/chọn trạm; điều khiển chạy; H3. Bảng latency/pipeline, editor snapshot và menu tình huống không phải chức năng bắt buộc của giao diện mới.

## 4. Luồng người dùng đề xuất

```text
[Xe] [SOC] [Chọn A] [Chọn B] [Tìm đường]                  [H3 bật/tắt]

Bản đồ: tuyến A→B + marker trạm #1…#5
Bảng Top 5 gọn: hạng, tên, dịch vụ, đến trạm, chờ, tổng qua trạm

Rê chuột / focus → xem thẻ ngắn
Click / chạm     → ghim thẻ để đọc và thao tác
[Ghé trạm này]  → xác nhận lựa chọn tuyến xe→trạm→B
[Bắt đầu]       → chạy trên tuyến đã chọn; nếu chưa chọn trạm, chạy thẳng B
```

- `Tìm đường` là một hành động người dùng, đồng thời tính tuyến trực tiếp và tìm dịch vụ chủ động. Việc trả Top 5 không tự chọn trạm #1 làm điểm ghé.
- Hover/focus không gọi API, không sửa SOC, không đổi selected station, không kéo bản đồ tự động. Popup click giữ ổn định khi dữ liệu refresh.
- Trên thiết bị cảm ứng dùng chạm; hỗ trợ focus/Enter/Escape trên bàn phím. Nút hành động nằm trong thẻ ghim, không buộc người dùng đuổi theo tooltip biến mất.
- Khi đang chạy, A là vị trí đã được chấp nhận hiện tại. Đổi A được xem là cấu hình chuyến mới: dừng chuyến cũ và cần hành động Bắt đầu mới. Đổi B hoặc chọn trạm khác phải thay geometry/replay/progress cùng một lần commit; trong lúc tính, đánh dấu đang đổi tuyến và không cho request cũ áp kết quả.
- Giữ Play/Pause trong Driver nếu cần mô phỏng chuyển động từ A→B. Bỏ scenario UI không có nghĩa bỏ nguồn GPS mô phỏng. Ghi nhãn “Mô phỏng di chuyển” cho nguồn synthetic; không gọi đó là GPS thiết bị thật.
- Đề xuất giữ chức năng “Đến B rồi sạc” nếu đang có người dùng, trong mục thu gọn. Không dùng kết quả của intent này lấp vào danh sách “Ghé trạm trên đường”; thiếu dữ liệu phải hiện thiếu dữ liệu. Không nhân cơ hội hợp nhất để xóa hành vi này mà chưa chốt phạm vi.

### Thẻ trạm gọn và trung thực

```text
#2  Trạm S003                         Đổi pin · Đang mở
Xe → trạm: 0,6 km · 1 phút           Trống: 10 vị trí
Chờ: 0 phút · Đổi pin: 5 phút
Trạm → B: 0,6 km · 1 phút            Đi vòng: +1,1 km
Tổng qua trạm tới B: 7 phút
[Ghé trạm này]
```

Các số trên chỉ minh họa bố cục theo ảnh, không được chép làm fallback hoặc expected output. “Đổi pin” phải ghi thời gian đổi pin, không luôn dùng chữ “sạc”. Cảnh báo pin SAFE/ADVISORY/CRITICAL độc lập với việc có Top 5: người dùng chủ động tìm trạm không đồng nghĩa pin nguy hiểm.

Trạm offline/không phù hợp không được ở Top 5 hợp lệ. Nếu vẫn hiện các trạm khác trên bản đồ làm tham khảo, thẻ phải ghi rõ trạng thái, nguồn/thời điểm thông tin và vô hiệu hóa nút ghé trạm cho lựa chọn không hợp lệ. Unknown không được giả làm OPEN; thiếu queue không được hiển thị 0 phút.

## 5. Những điểm đã tìm thấy trong code hiện tại

| Vị trí / symbol | Vấn đề | Yêu cầu xử lý |
|---|---|---|
| `app.js:init/loadCatalogs` | Tạo cả Driver và Sim; tải scenarios/trips như dependency bootstrap | Một Driver runtime; bỏ scenario dependency và window.simMode |
| `sim_mode.js:runSimulation` | Song song candidate-search, recommend, route; snapshot/candidate result có thể khác lần tìm trong recommend | Không sao chép orchestration Debug sang Driver |
| `driver_controller.js:refreshDrawerEvaluations` | Tự gọi candidate-search + recommend top_n=30, catch thành null rồi giữ data trước | Top 5/list/map dùng một result đã chấp nhận; hiển thị lỗi/stale thay vì âm thầm trộn |
| `map.js:renderRecommendationRoute` | Marker Top 5 sống cùng layer tuyến preview | Tách vòng đời marker/rank khỏi việc có vẽ được hai leg tuyến hay không |
| `map.js:renderTopCandidatesBadges` | Tooltip chỉ có station_id; click mở popup của marker khác | Cùng renderer dữ liệu cho marker/list/popup, truyền đúng candidate |
| `map.js:renderStations` | Nút dẫn đường luôn hiện kể cả ineligible; callback click marker có thể gọi onSelect ngay | Click để xem; chỉ nút chọn chủ động mới commit navigation; gate eligibility |
| `drawer_renderer.js:renderDrawerStationCard` | Fallback distance đường chim bay, phút suy đoán, 5/20 phút dịch vụ; tìm candidate chỉ theo station_id | Bỏ số giả trong thông tin operational; giữ composite station/service identity |
| `cockpit_renderer.js:renderTripActiveEta` | Khi có recommendation, ETA chính dùng eta_to_station_s | Khi Top 5 luôn hiện, lỗi này sẽ làm ETA tới B biến thành ETA tới trạm chưa chọn; sửa theo active route |
| `route_familiarity_overlay.js` | Overlay tốt về viewport/batch/cap, nhưng được sở hữu bởi Sim và nhận rec.familiarity | Chuyển ownership sang một Driver; chỉ hiển thị đúng geometry/revision |
| `ranking.py:recommend` | `requested_service=None` là AUTO, có thể trả rỗng lúc pin đủ | Hành động Tìm đường cần explicit service request, giữ nguyên backend eligibility |

### Đánh giá bản sửa playback đang dở

Đây là kết luận đọc diff/test, không khẳng định mọi điểm đã tái hiện live:

1. Nhánh `speedMultiplier >= 10` của `replay.js` dùng delay rất ngắn với chú thích dành cho test, nhưng `cockpit_renderer.js` có nút **10x** thật. 10x cho delay 50 ms (~1200 GPS/phút trước latency). Phải bỏ cơ chế production dựa vào “tốc độ test”; test dùng fake clock/injection riêng.
2. 5x có delay 800 ms: riêng GPS đã ~75/phút; cộng tối đa 12 recommend và 24 route leg/phút là ~111 request/phút trước overhead. Chú thích “safely within 100” chưa tính tổng. Không dựa vào may mắn Nginx chia đều hai replica.
3. `routeRevision` tăng cả khi evaluation và khi chọn tuyến. Một evaluation bắt đầu sau click chọn trạm có thể làm pending navigation tự vô hiệu hóa. Cần tách **thay đổi ý định tuyến** khỏi **phiên tìm recommendation**; refresh không được hủy lựa chọn người dùng đang tính.
4. `_updateCustomRoute` chưa có bảo vệ revision như navigation, và chưa thay observations khi đổi B đang chạy. `_triggerReroute` chưa bảo toàn waypoint trạm đã chọn.
5. `reset()` vẫn đặt `isStepInProgress=false` dù request cũ có thể chưa xong; DELETE state chạy fire-and-forget. Đây là cửa sổ request cũ/new/reset chồng nhau cần test có barrier.
6. Timestamp tuyến mới dựa vào lastAccepted giúp tránh lùi, nhưng bước gửi có thể clamp timestamp tương lai về now; callback vẫn truyền observation cũ. Cần một observation chuẩn duy nhất cho ingest, energy và recommend; retry cùng GPS phải giữ nguyên timestamp/payload. Không chỉ test timestamp lúc tạo polyline.
7. Retry hiện là lần đầu + 3 retry = **4 attempts**. Test “exhausted after 3 attempts” chỉ assert >=3 nên không chứng minh giới hạn. Phải chốt tổng attempts và assert bằng chính xác, không dùng >=.
8. Probe 6 gán trực tiếp selected station/revision ngay sau gọi evaluate, không đợi evaluation thực sự tới leg bị giữ và không gọi public navigate. Nó có thể pass bằng cách hủy evaluation ngay sau response recommend; chưa chứng minh race leg-2. Probe 3 đo concurrency GPS, không chứng minh chỉ một loop sở hữu timer; biến activeLoops không được dùng.

Không triển khai UI mới lên những giả định “test xanh nghĩa là race đã hết”. Agent phải bổ sung đúng các kiểm thử còn thiếu ở mục 10.

## 6. Contract dữ liệu Top 5

### Một kết quả dùng chung

- Dùng workflow `/api/v1/recommend` hiện có, `top_n=5`, có explicit `requested_service` khi người dùng Tìm đường. `ANY` hiện có nhánh hỗ trợ những service trong capability; agent phải kiểm tra hành vi thật bằng test, vì docstring trong driver_requester có mô tả cũ không khớp nhánh ANY.
- Có thể gửi CHARGING với xe chỉ sạc, BATTERY_SWAP với xe chỉ đổi, ANY với xe nhiều dịch vụ; backend vẫn là nơi kiểm tra capability. Không giả SOC thấp để ép có trạm, không tự nới eligibility hoặc tự xếp hạng theo đường chim bay.
- Một result gồm `candidate_search_id`, `request_time`, vị trí/SOC/đích của request, ranked candidates và freshness. Map, cards, tooltip cùng đọc result này. Catalog chỉ bổ sung tên/tọa độ, không ghi đè queue/capacity/rank.
- Danh tính candidate là **(station_id, service_type)**. Giữ nguyên backend rank. Nếu một trạm có hai dịch vụ trong 5 candidate, gom hiển thị dưới cùng vị trí/thẻ với hai lựa chọn dịch vụ; không đè bản ghi hoặc tự tạo trạm thứ sáu để “đủ 5”. Số trạm vật lý có thể ít hơn số phương án.
- Lỗi route trực tiếp và lỗi recommendation là hai kết quả riêng: route A→B thành công vẫn có thể dùng khi tìm trạm lỗi, với thông báo rõ. Không hiển thị kết quả trạm cũ như thuộc A/B mới.
- Cần cảnh báo năng lượng AUTO riêng với explicit intent: `energy_context.need_service=true` của DRIVER_REQUEST không được dùng để suy ra CRITICAL. Tái sử dụng API demand hiện có với cùng telemetry nếu cần; chỉ một nơi điều phối, tính request đó vào ngân sách. Không tự phát minh logic cảnh báo frontend.

### Trường cho renderer

| Nội dung | Field authoritative |
|---|---|
| Hạng / dịch vụ | `rank`, `service_type` |
| Xe → trạm | `features.distance_to_station_m`, `eta_to_station_s` |
| Chờ | `features.effective_queue_wait_s`, kèm `queue_assumption` khi có; phân biệt observed null |
| Sạc / đổi | `features.service_duration_s` |
| Trạm → B | `features.distance_station_to_dest_m`, `features.duration_station_to_dest_s` |
| Đi vòng | `features.detour_distance_m`, `features.detour_duration_s` |
| Tổng qua trạm tới B | `eta_to_destination_via_station_s` |
| Vị trí phục vụ còn trống | `features.available_capacity` |
| Freshness | các `station_state`, `queue_state`, `traffic_state`, request_time và degraded reasons |

Null → “Chưa có dữ liệu”; 0 → hiển thị 0. Không lấy `final_cost_s` làm tổng chuyến đi: cost có thể có penalty và mục tiêu ranking là hoàn tất dịch vụ; tổng tới B là trường riêng. Không đổi `score` không tồn tại thành phần trăm “độ phù hợp”. Format đơn vị và số thập phân được làm ở frontend; suy luận nghiệp vụ/ranking thì không.

## 7. Quyền sở hữu trạng thái để tránh vòng lặp lỗi

Tái sử dụng các module có sẵn, không cần store framework hay event bus mới. Những trách nhiệm phải rõ:

| Trạng thái | Chủ sở hữu / quyền thay đổi |
|---|---|
| Session/chuyến, A/B, vehicle | Driver controller, từ hành động người dùng |
| GPS đã nhận, index, clock, loop/cooldown | Replay controller duy nhất |
| Tuyến đã chọn + station/service + route revision | Driver navigation flow; refresh/hover không được đổi |
| Top 5 + request revision + freshness | Một recommendation flow; không sở hữu tuyến chạy |
| Tooltip/popup/H3 | Chỉ trạng thái trình bày, không gọi orchestration |

Các invariant bắt buộc:

- Tối đa một GPS in-flight; một loop có quyền lên lịch bước tiếp theo. Cancel timer phải settle Promise. Không mở khóa request đang chạy bằng gán boolean khi reset.
- Revision tuyến tăng khi ý định A/B/vehicle/station thay đổi; request sequence recommendation chỉ tăng cho recommendation. Mọi async response kiểm tra session + loại revision đúng trước khi commit. Response cũ không được xóa loading/error của request mới trong finally.
- Route geometry, điểm ghé, progress tracker và synthetic trajectory thay cùng nhau sau khi route mới hợp lệ. Trong lúc route mới đang tính, đề xuất pause mô phỏng; thất bại giữ tuyến cũ, báo lỗi, người dùng tiếp tục chủ động.
- GPS đã ACK mới được tính tiến độ/SOC. Không double debit khi retry. `STALE_OBSERVATION` không được tính thành accepted. Cùng observation retry có cùng timestamp/payload.
- Refresh cập nhật Top 5 nhưng không tự chuyển selected station về top 1. Nếu trạm đã chọn bị xác nhận offline, báo rõ cần chọn lại và dừng việc commit tuyến không hợp lệ; không tạo vòng unlock→refresh→auto-select.
- Hết tuyến chuyển COMPLETE đúng một lần; bấm tiếp tục không tự wrap về A. Chuyến mới tạo session mới; cleanup session cũ không xóa state session mới.
- Completion/state callback không tự sinh recommend/startTrip đệ quy. Backend 409 chỉ có đúng retry search một lần trong workflow hiện hữu; frontend không bọc retry 409 vô hạn.

## 8. Nhịp request và thời gian

- Hover, click mở thẻ, bật/tắt H3: **0 request tìm trạm/route/GPS mới**.
- Lần Tìm đường: một route trực tiếp + một recommend; không thêm candidate-search để dựng thẻ từ snapshot khác. Nếu cảnh báo AUTO cần endpoint demand riêng, gọi cùng telemetry và đếm trong ngân sách.
- Preview tuyến ghé chỉ tải theo hành động xem/chọn chủ động; không fanout 10 route calls cho 5 trạm mỗi lần refresh. Metric có sẵn trong ranked candidates đủ dựng thẻ.
- Một refresh controller, tối đa một evaluation đang xử lý; coalesce thay đổi liên tục thành input mới nhất. Không tạo interval riêng cho map, drawer, badge và H3.
- Áp dụng ngân sách tổng trên các API call, không chỉ GPS. Có thể khởi đầu với GPS cách nhau >=1.5 giây, refresh >=5 giây, rồi đo trên cả một replica và hai replica. Speed 1x/5x/10x không được bypass giới hạn network. Tốc độ mô phỏng phải có định nghĩa nhất quán với clock/spacing; không chỉ tăng timestamp mà UI vẫn chạy cùng tốc độ.
- Retry tạm thời tổng **tối đa 3 attempts/observation** là đề xuất chốt cho triển khai: lần đầu + tối đa 2 retry. Tôn trọng Retry-After (seconds và HTTP-date hợp lệ), cooldown cancel được; hết budget → trạng thái lỗi rõ. Không tự restart/reload để làm mới budget.
- Lưu bền payload pending trong vòng bước để retry không đổi thời gian; dùng cùng normalized observation cho downstream. Event-time và wall-time khác nhau: rate limit dùng wall-time, replay/history dùng event-time. Không cho snapshot tương lai chảy vào đánh giá lịch sử.
- Không sửa Dataset, nâng rate limit vô cớ hoặc thêm Redis limiter mới để che request trùng.

## 9. H3 chỉ để hiển thị

H3 hiện thuộc `RouteFamiliarityOverlay` trong Sim, nhận `rec.familiarity.route_cells`. Backend familiarity là tính năng opt-in có yêu cầu gateway ký danh tính. **Không bật familiarity, bỏ authentication hoặc giả chữ ký chỉ để nút H3 hoạt động.**

Đề xuất: nút H3 trong Driver vẽ các ô H3-11 dọc **tuyến đang hiển thị có revision rõ ràng**. Tái sử dụng local pinned H3 bundle và renderer viewport/batch/cap hiện có. Nếu response đã có cells phù hợp đúng tuyến thì dùng; nếu chỉ có geometry A→B, tính lớp ô hình học cục bộ phục vụ trình bày. Không gửi ô đó vào ranking, không gắn nhãn lịch sử/cộng đồng hay độ chính xác.

Nếu tạo cells từ geometry: cần lấy mẫu dọc các segment, không chỉ đổi các đỉnh thưa thành cell; chặn input quá dài và giới hạn công việc. Giữ cap render 500 cells, batch 50 hiện có; hiển thị khi bị giới hạn. Giới hạn xử lý đầu vào phải có test, không chỉ giới hạn polygon đầu ra. Đây là lớp trực quan xấp xỉ, không cam kết mọi cell bị đường cắt qua hoặc tương đương signature familiarity backend.

Toggle không gọi API, thay camera, fitBounds hoặc hủy replay. Route đổi phải hủy batch cũ. Hover trạm không đổi lớp H3; chọn/xem tuyến khác bằng hành động rõ ràng mới đổi nguồn. Tắt H3 xóa overlay nhưng không xóa tuyến, marker hay Top 5. Thiếu dữ liệu/library thì nút vô hiệu hóa có lý do.

## 10. Tiêu chí kiểm thử bàn giao

| Ca bắt buộc | Điều kiện pass |
|---|---|
| Pin đủ, bấm Tìm đường | Explicit search trả tối đa 5 hợp lệ nếu có; cảnh báo pin vẫn đúng; chưa tự ghé top 1 |
| 0/1/5 kết quả; trạm hai dịch vụ | Không tạo số/trạm giả; composite keys không bị ghi đè; danh sách và map đồng nhất |
| Hover/focus/chạm 100 lần | Không tăng network search/route count, không thay session/index/SOC/selected station |
| Trạm offline hoặc chưa biết capacity | Không có nút chọn hợp lệ; null không thành 0; tooltip/list cùng trạng thái |
| Đổi B liên tiếp, response đảo thứ tự | Chỉ revision cuối commit; map, replay và đích khớp nhau |
| Chọn NEW khi evaluation OLD đang chờ leg-2 | Test phải đợi barrier xác nhận đang ở leg-2 và gọi navigate thật; NEW không bị ghi đè |
| Evaluation bắt đầu khi navigation đang chờ | Refresh không hủy navigation mới của người dùng |
| Pause/Play, load/reset lúc ingest và sleep pending | Một loop có quyền schedule, một GPS in-flight; không orphan wait hoặc double SOC |
| 429, timeout, 503, 422, stale | Số attempts chính xác; payload retry bất biến; không skip index; lỗi dữ liệu không retry mãi |
| Synthetic route dài, đổi tuyến nhiều lần | Timestamp gửi và timestamp dùng đánh giá khớp, không lùi/tương lai; backend không reject stale |
| 1x/5x/10x trên runtime thật | Không có nhánh test bypass production rate; đo tổng API request, không chỉ GPS |
| H3 toggle/zoom/đổi tuyến liên tục | 0 orchestration calls; cap/batch hoạt động; không cells của route cũ; ranking bất biến |
| Chạy tới B | COMPLETE đúng một lần, không quay về A, không request nền tiếp sau khi kết thúc |
| Scenario removal | Trang không tải scenarios/trips mẫu, không import/khởi tạo Sim, vẫn bootstrap khi file scenario UI không tồn tại |
| Offline evaluation | Dataset hashes giữ nguyên; test labels vẫn offline; không xóa kiểm thử chỉ vì tên có scenario |

Unit/integration tests dùng deferred barriers và fake clock thay cho sleep 200 ms phụ thuộc máy. Không sửa assertion để khớp bug. Từng test hồi quy phải thất bại trên logic lỗi tương ứng và pass sau sửa. Các kiểm thử thuộc UI Debug cũ được thay bằng invariant Driver mới, không xóa trắng coverage.

E2E thật: dùng A/B tùy chọn trên GraphHopper, chạy đủ tới B và vượt nhiều chu kỳ 60 giây; bật snapshot simulator, thử pin cao/thấp, chọn/đổi trạm, H3 và lỗi dependency có kiểm soát. Không yêu cầu giữ đúng 648 điểm nếu sampling được đổi có chủ đích; phải ghi rõ số điểm mới và chứng minh hết tuyến. Không dùng mock để báo live PASS. Kiểm tra cả hai API container chứa đúng source đã nghiệm thu; health xanh không chứng minh phiên bản đúng.

## 11. Phạm vi file và thứ tự cho agent triển khai

1. **Chụp baseline hiện tại:** git diff, phiên bản source/container, kết quả test; bảo toàn sửa dở của người khác. Đọc báo cáo cũ như lịch sử, không giả định line number hiện tại giống cũ.
2. **Khóa contract và test race còn thiếu:** ownership, attempts, input/output data và cảnh báo AUTO vs explicit. Ghi ADR mới cho thay đổi approach sau khi thiết kế được duyệt; không sửa ADR cũ để tuyên bố đã approved.
3. **Ổn định replay/navigation:** `replay.js`, `api.js`, `ui/driver_controller.js`; xử lý đầy đủ caller, đừng vá chỉ nút gây triệu chứng.
4. **Hợp nhất luồng dữ liệu Driver:** `app.js`, Driver controller; một kết quả recommend phục vụ list/map. Bỏ độc lập drawer orchestration và đăng ký Sim.
5. **Chuyển UI:** `index.html`, `style.css`, `map.js`, `ui/cockpit_bindings.js`, các renderer hiện có và overlay H3. Chọn renderer chung nhỏ nhất cho thẻ; không nhân bản công thức trong ba renderer.
6. **Dọn phần không còn dùng:** `sim_mode.js`, scenario UI JSON, CSS/DOM/listeners và catalog loader liên quan; `trips.json`, tech_view/components chỉ xóa khi kiểm tra không còn consumer runtime. Giữ module dùng chung, dữ liệu chuẩn và offline tools.
7. **Nghiệm thu rồi cập nhật runtime:** chạy test/lint/E2E và live; sau đó rebuild API đã kiểm tra, kiểm tra version trên cả hai replica, browser cache/reload và proxy routing. Không gộp việc thay dependencies/Dockerfile đang dở vào tuyên bố UI đã xong nếu chưa review riêng.

Không bắt buộc tách thành nhiều framework/module mới. Mỗi bước chỉ coi hoàn tất khi điều kiện pass liên quan đã có bằng chứng; lỗi phát hiện phải quay lại nguyên nhân, không bù bằng auto-resume hoặc retry mới. Agent không được claim “không thể có bug”; phải bàn giao danh sách invariant, test output, live evidence và giới hạn còn lại.

## 12. Prompt bàn giao ngắn

> Đọc AGENTS.md, tài liệu dự án, báo cáo điều tra playback và báo cáo Driver-only này. Yêu cầu là một Driver Mode duy nhất, Tìm đường luôn tìm tối đa 5 phương án trạm phù hợp, hover/click thẻ trực quan và H3 chỉ hiển thị. Bỏ scenario khỏi runtime UI, giữ Dataset V1 và offline evaluation. Trước khi triển khai, đối chiếu diff đang dở và xin chốt các quyết định thiết kế còn chưa duyệt; không coi báo cáo là chứng nhận đã sửa. Bổ sung các regression test còn thiếu trước khi sửa logic, đặc biệt race NEW/OLD thật, refresh hủy navigation, reset in-flight, tốc độ 10x, event-time và tổng request. Không ghép hai controller, không copy orchestration Debug, không tự chọn top 1, không tạo số fallback operational. Chỉ nghiệm thu khi unit/integration/browser và hành trình thật tới B qua nhiều cửa sổ rate limit đạt tiêu chí mục 10. Ghi bằng chứng và ADR phù hợp; không sửa Dataset hoặc bắt đầu hạ tầng Week 6.
