# Khảo sát H3 resolution và yêu cầu so sánh hai route

Ngày: 2026-10-10. Phạm vi: đọc code hiện tại, đối chiếu workbook nghiệm thu, chạy thử nghiệm độ nhạy bằng hàm production. Đây là kết quả khảo sát và đề xuất, không phải ADR đã duyệt hay thay đổi runtime.

## Kết luận

Resolution 11 + exact cell identity có độ nhạy quá cao với lệch ngang nếu mục tiêu là so sánh hành lang giao thông. Tuy nhiên, đổi 11 thành 9 không giải quyết đầy đủ yêu cầu: có thể gộp nhầm đường song song, không bảo đảm cùng hướng, và hiện tại API đang trả mức giống tốt nhất trong lịch sử thay vì một cặp route xác định. Khuyến nghị thử nghiệm Resolution 9 làm chỉ mục hành lang, kiểm chứng đoạn tương ứng bằng geometry và hướng trước khi tính khoảng cách chung. Resolution 10 là phương án đối chứng cần đo, không bỏ qua vì thiếu một chuẩn công nghiệp bắt buộc.

Không chọn Resolution 8 làm metric chính cho tuyến đô thị. Không gọi một resolution là tối ưu trước khi đánh giá cặp tuyến Hà Nội có ground truth và cả false positive lẫn false negative.

## Đối chiếu yêu cầu

Workbook nguồn: `C:\Users\nguye\Downloads\NGUYEN_VAN_NINH_S_AI_20K_Ke_hoach_nghiem_thu_6_tuan.xlsx`, đọc bằng openpyxl ở chế độ read-only/data-only.

- `Bang tong hop!A7:I7`: nội dung, sản phẩm, tiêu chí hoàn thành và sáu tuần.
- `Nghiem thu 6 tuan!A7:C12`: map matching, demand, candidate/routing, ranking, realtime API/evaluation, productionization.
- `Nghiem thu 6 tuan!A14`: không bổ sung ngưỡng KPI hoặc cam kết nghiệm thu mới.

Workbook không ấn định H3 resolution, công thức overlap, tiêu chí chọn tuyến hay quy tắc suy luận động cơ người lái. Yêu cầu scale-up do người dùng cung cấp bổ sung ba câu hỏi: hai tuyến giống nhau bao nhiêu phần trăm; bao nhiêu người dùng hành lang đó; vì sao họ chọn đường đó. Ba câu hỏi cần phân biệt vì route/GPS chỉ đủ chứng minh hành vi sử dụng đường, không đủ chứng minh động cơ.

Đã đọc PROJECT_SCOPE, ACCEPTANCE_CRITERIA, DATA_CONTRACT, ARCHITECTURE, DECISIONS và tracker. `PHASE_TRACKER.md` ở root không tồn tại; tracker hiện có là `docs/PHASE_TRACKER.md`, mô tả Phase 0–3. `docs/PHASE4_ROUTE_FAMILIARITY.md` ghi nhận Phase 4. ADR-021 hiện quy định Resolution 11. Không tự thay ADR hay bắt đầu Week 6.

## Luồng code thực tế

1. `api/v1/route_familiarity.py` nhận completed-route polyline từ trusted producer. `route_familiarity/ingestion.py` tạo signature và gọi repository. Đường ingestion này không tự map-match lại polyline; độ đúng của tuyến thực đi phụ thuộc producer.
2. `route_familiarity/signature.py` giải mã polyline, nội suy trên từng đoạn, lấy midpoint với bước tối đa bằng nửa cạnh H3 trung bình, tạo cell ở Resolution 11. Chỉ gộp cell liên tiếp; giữ revisits và khoảng cách mỗi lượt đi qua cell.
3. `candidate/service.py` tạo recommended signature cho candidate eligible từ hai leg GraphHopper: current location → station → destination. Không có destination hay thiếu geometry thì familiarity unavailable. Đây là tuyến còn lại tại thời điểm request, không nhất thiết cùng phạm vi với một chuyến lịch sử hoàn chỉnh.
4. `ranking/orchestration.py` chuyển signatures sang ranking. `route_familiarity/repository.py` lấy personal history theo driver/time, không lọc cặp origin/destination. Community history dùng PostgreSQL GIN `cells && query_cells`, rồi giới hạn drivers/trips. Cả hai chỉ lấy completed routes đã có tại request time.
5. `route_familiarity/service.py` còn kiểm tra exact cell intersection trước similarity. Personal score là MAX adherence trong tối đa 50 chuyến, không phải trung bình hay tuyến phổ biến nhất. Số chuyến hỗ trợ dùng ngưỡng mặc định 0.10. Confidence dựa vào số chuyến, không phải độ chính xác GPS hay xác suất đúng tuyến.
6. `route_familiarity/similarity.py` dùng weighted ordered LCS, triển khai sparse bằng Fenwick tree. Cặp cell chỉ được nối nếu ID bằng nhau. Mỗi cặp đóng góp `min(recommended_cell_distance, historical_cell_distance)`. Khoảng cách chung chia độ dài recommended route; không phải Jaccard, không đối xứng, không phải đếm cell giao nhau.
7. Community score lấy best score mỗi driver đủ mức hỗ trợ, cộng prior và làm trơn; chỉ hiển thị khi đủ distinct drivers. Đây không phải tỷ lệ phần trăm toàn bộ tài xế chọn route. Community không đổi ranking. Personal penalty có thể thêm tối đa 30 giây vào final cost, không đổi ETA vật lý, eligibility hay 409 retry.
8. `ranking/models.py` khai báo resolution trong response mặc định từ constant. `ranking/service.py` trả recommended cells, chưa trả các lượt cell/đoạn thực sự được alignment match để vẽ overlap.
9. Working tree hiện tại: `ui/driver_controller.js:onToggleH3()` tự lấy `directRouteGeometry` để tạo H3 ở frontend. `ui/route_familiarity_overlay.js` lấy mẫu khoảng 35 m, dùng Set loại lặp, giới hạn 500 cell và tô màu theo khoảng cách tới station. Nó không dùng cùng signature hay cùng trọng số của backend, chưa phải màn so sánh hai tuyến. Comment khẳng định continuous coverage không phải bảo đảm hình học khi tuyến lướt gần đỉnh/biên cell.

Feature backend mặc định tắt. Tìm kiếm source frontend không thấy caller gửi completed routes tới endpoint internal. Không kết luận hệ thống đã thu thập được tuyến thực đi từ việc nhìn thấy lớp H3 trên bản đồ. Không đưa trusted producer token vào browser để giải quyết khoảng trống này.

## Kiểm chứng kích thước H3

H3 Python đang cài: 4.5.0. [Bảng H3 4.x chính thức](https://h3geo.org/docs/core-library/restable/) và API đang cài cho cạnh trung bình:

| Resolution | Cạnh trung bình (m) | Diện tích trung bình (m²) |
|---|---:|---:|
| 8 | 531.414 | 737327.598 |
| 9 | 200.786 | 105332.513 |
| 10 | 75.864 | 15047.502 |
| 11 | 28.664 | 2149.643 |

Đây là thống kê trung bình, không bảo đảm mọi cell có cùng kích thước. Các số 174/461/24.9 m trong phản biện không khớp bảng 4.x và thư viện hiện tại. Không dùng đường kính suy từ cạnh như ngưỡng khoảng cách tuyến. [Bài Uber giới thiệu H3](https://www.uber.com/us/en/blog/h3/) giải thích spatial indexing và ứng dụng; nguồn đã kiểm tra không chứng minh Resolution 9 là chuẩn bắt buộc/tối ưu cho route similarity của Uber hoặc Grab.

## Thử nghiệm bằng hàm production

Script: `runtime/h3-resolution-review/sensitivity.py`. Kết quả: `runtime/h3-resolution-review/sensitivity.json`.

Trong process thử nghiệm riêng, thay resolution và bước sampling tương ứng của module signature. Source production, schema, DB và Dataset không được thay đổi. Sử dụng chính `create_route_signature` và `weighted_ordered_overlap`, encoder từ test hiện có. 10 vị trí quanh Hà Nội × 3 hướng = 30 cặp mỗi mức lệch/mỗi resolution. Tuyến thẳng dài khoảng 2 km, dịch ngang có kiểm soát; đây là dữ liệu tổng hợp, không phải xác nhận chất lượng GPS hay các đại lộ thực tế.

| Resolution | Lệch 10 m | Lệch 25 m | Lệch 40 m | Cách 100 m | Cách 200 m | Đảo hướng tuyến 2 km |
|---|---:|---:|---:|---:|---:|---:|
| 8 | 100.00% | 100.00% | 100.00% | 100.00% | 81.25% | 50.00% |
| 9 | 95.00% | 90.00% | 85.00% | 67.50% | 35.00% | 20.00% |
| 10 | 90.57% | 79.25% | 66.97% | 20.75% | 0.00% | 7.55% |
| 11 | 75.69% | 44.64% | 16.07% | 0.00% | 0.00% | 2.86% |

Giá trị là trung vị, không phải tỷ lệ đúng/sai trên đường thật. Định nghĩa product quyết định đường song song được coi là cùng corridor hay khác route; bảng cho thấy trade-off, không tự xác lập ground truth đó.

Các phát hiện bổ sung:

- Cùng geometry nhưng đổi từ hai vertices thành 68 vertices: median khoảng 92.53–94.31%, thay vì 100%. Nguyên nhân là sampling restart trên từng đoạn và xấp xỉ trọng số giao biên. Thay resolution không tự loại bias này.
- Tuyến khoảng 10 m ở tâm một cell và tuyến đảo ngược đạt 100% ở cả bốn resolution. Thứ tự cell không thể bảo đảm hướng khi cả tuyến chỉ có một cell.
- Resolution 9 vẫn có trường hợp lệch 25 m chỉ đạt 80%; ô lớn không xóa hoàn toàn hiệu ứng ranh giới.
- 12 domain/similarity tests hiện tại PASS. Các test này xác nhận implementation weighted LCS, nhưng chưa là bằng chứng đã chịu GPS drift, phân biệt đường song song, hay metric đúng yêu cầu scale-up.

## Hướng xử lý đề xuất

### Phương án A: chỉ đổi 11 → 9

Diff nhỏ nhưng đầy đủ vẫn cần DB migration, lịch sử, frontend, test, tài liệu. Cải thiện độ nhạy lệch ngang nhưng giữ lỗi hướng, gộp đường song song, sampling bias, sai phạm vi cặp tuyến và thiếu bằng chứng giải thích. Không khuyến nghị dùng làm bản sửa hoàn tất.

### Phương án B: H3 tìm hành lang, geometry/hướng xác nhận đoạn chung

Khuyến nghị cho yêu cầu scale-up. Bắt đầu đánh giá với Resolution 9 và dùng Resolution 10 làm đối chứng. Tái sử dụng GraphHopper, PostGIS và H3 đang có, không thêm engine hay vector DB.

- Chốt metric chính: `recommended_coverage = verified_shared_m / recommended_route_m`. Nếu cần trả lời phần đường thực đi giống đề xuất, trả thêm `actual_coverage = verified_shared_m / actual_route_m`. Hiển thị rõ mẫu số, không dùng một % mơ hồ. Chỉ số đối xứng là tùy chọn khi thật sự cần.
- Định danh rõ recommended route revision/time và actual trip/comparison extent. Hai tuyến phải cùng phạm vi A→B hoặc cùng phần còn lại; không so tùy tiện full historical trip với current→station→destination rồi gọi là mức tuân thủ chuyến hiện tại.
- H3 ở Resolution 9 dùng để thu hẹp tìm kiếm đoạn tương ứng. Xét cell cùng ô và ô lân cận ở bước tìm ứng viên để không mất đoạn ngay biên. Không tự coi mọi ô lân cận là match.
- Đoạn được tính chung cần gần nhau theo geometry/corridor policy và cùng hướng, giữ thứ tự di chuyển và không double-count revisits. Không dùng tâm cell như vị trí xe. Ngưỡng khoảng cách/hướng là tham số cần hiệu chỉnh bằng dữ liệu, chưa có số đã được duyệt. Directed road identity là bằng chứng hỗ trợ khi resolve rõ; ID null/AMBIGUOUS không được biến thành match chắc chắn.
- Route history hiện chỉ lưu cell/weights, không giữ subcell geometry hoặc heading; xác nhận geometry/hướng đòi hỏi bổ sung bằng chứng có giới hạn từ trusted producer và cập nhật privacy/retention contract. Không giả định có thể lấy lại thông tin đã mất từ cell ID. Cần quyết định này trước implementation.
- Giữ bounded workload và explicit unavailable. Kế thừa thuật toán alignment hiện có khi phù hợp nhưng cập nhật điều kiện match và cả prefilter SQL/service. Cách tính verified shared distance phải được định nghĩa, không tự coi trọng số của hai lượt đi qua ô là độ dài giao hình học chính xác.
- Personal familiarity và actual adherence là hai kết quả khác nhau. Với familiarity, best-ever không chứng minh tuyến thường đi. Có thể báo supporting trips/eligible comparable trips trong cửa sổ thời gian trước; định nghĩa comparable trip và ngưỡng support phải được thống nhất trước thay đổi.
- Community báo distinct supporting drivers/trips và phạm vi mẫu/cửa sổ/truncation. Không đổi score làm trơn hiện tại thành tỷ lệ phổ biến mà không có mẫu số thích hợp. Giữ privacy suppression và event-time semantics.
- UI dùng kết quả backend: tuyến đề xuất, tuyến thực, phần chung, phần khác, resolution và provenance. Frontend chỉ render. Lớp station coverage hiện tại nếu giữ phải có tên riêng, không đại diện overlap.

### Phương án C: Resolution 10, giữ exact ordered overlap

Phương án tạm ít thay đổi hơn B, cân bằng hơn giữa drift và hai đường song song trong thí nghiệm này. Vẫn không giải quyết hướng trong một ô hoặc tất cả boundary/sampling bias. Không chọn làm giải pháp cuối chỉ vì diff ngắn.

## Câu hỏi “nhiều người đi đường đó vì sao”

GPS/history chứng minh có người đi qua, không chứng minh họ tránh tắc hay thích đường đó. Có thể giải thích các bằng chứng đo được: mức hỗ trợ cộng đồng, thời gian di chuyển quan sát, detour, traffic tại thời điểm chuyến. Muốn nói tài xế chọn vì traffic/queue/ETA phải có snapshot hoặc feedback tương ứng ở thời điểm lựa chọn. Thiếu bằng chứng thì ghi rõ chưa xác định lý do; không suy luận nhân quả từ độ phổ biến. Queue/capacity chủ yếu giải thích station choice, không tự giải thích lựa chọn mọi road corridor.

## Các nơi phải thay khi triển khai

- constants, signature/models, similarity và work budget/indexing.
- trusted ingestion contract, repository/schema, additive migration/backfill, event-time/privacy safeguards.
- cả SQL community prefilter và service early intersection; không để chúng loại mất matches mà thuật toán mới cho phép.
- candidate signature creation, recommendation workflow, ranking explanation model/default resolution và penalty regressions.
- Driver UI/controller/renderers, overlay validation/labels/sampling; API cung cấp bằng chứng đủ render mà không lộ lịch sử riêng tư.
- domain/similarity/repository/API/workflow/ranking/privacy/frontend tests, benchmark fixtures, OPERATIONS/ARCHITECTURE và ADR-021 supersession.

Schema hiện dùng `CREATE TABLE IF NOT EXISTS` với `CHECK (resolution = 11)`; chỉnh schema file không alter table đã tồn tại. Personal history không filter resolution; comparator từ chối mixed resolutions, còn service có thể bypass comparator khi cell không giao. Do đó migration thiếu đồng bộ có thể trả score 0 hoặc familiarity UNAVAILABLE, không chỉ SQL insert error.

Lịch sử 11 có thể chuyển parent H3 và gộp **chỉ cell liên tiếp**, cộng trọng số, nhưng đó là xấp xỉ dựa trên logical hierarchy; không tương đương tạo lại signature 9 trực tiếp từ geometry. Không relabel resolution mà giữ nguyên IDs. Backfill cần version/provenance, idempotency và rollback giữ lịch sử; không dùng script `--rollback` hiện tại vì nó DROP table.

## Kiểm chứng cần trước nghiệm thu bản sửa

Không tự đặt ngưỡng KPI. Bộ đánh giá phải gồm: cùng geometry khác mật độ sample; lệch ngang/GPS noise qua biên; hai đường song song; cùng corridor ngược hướng; đoạn ngắn cùng cell; crossings/loops/revisits; detour một phần và khác chiều dài; thiếu matching evidence; history migration/mixed versions; prefilter recall; bounded workload; không đổi eligibility/ETA/409 semantics và privacy/event-time. So sánh 9/10/11 trên cùng tập cặp tuyến có xác nhận ground truth, báo false positives, false negatives, sai số khoảng cách chung và latency riêng.

Dataset V1 vẫn read-only; labels chỉ dùng offline đánh giá. Chưa chạy đánh giá chất lượng tuyến thật hoặc live GraphHopper/PostgreSQL trong khảo sát này. Không chạy full suite/validator vì không sửa runtime hay Dataset. Working tree có frontend edits từ trước, đã giữ nguyên.
