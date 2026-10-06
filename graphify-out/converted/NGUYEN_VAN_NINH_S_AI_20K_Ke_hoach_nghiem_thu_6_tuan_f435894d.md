<!-- converted from NGUYEN_VAN_NINH_S_AI_20K_Ke_hoach_nghiem_thu_6_tuan.xlsx -->

## Sheet: Bang tong hop
| KẾ HOẠCH THỰC HIỆN VÀ NGHIỆM THU DỰ ÁN |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Người thực hiện: NGUYEN VAN NINH (S.AI.20K) |  |  |  |  |  |  |  |  |
| Bài toán: Tự động tìm trạm sạc/tủ đổi pin phù hợp nhất cho Driver |  |  |  |  |  |  |  |  |
| PHẠM VI, SẢN PHẨM VÀ TIÊU CHÍ |  |  | LỘ TRÌNH NGHIỆM THU 6 TUẦN |  |  |  |  |  |
| Bài toán/Dự án | Sản phẩm bàn giao | Tiêu chí hoàn thành | Nghiệm thu Tuần 1 | Nghiệm thu Tuần 2 | Nghiệm thu Tuần 3 | Nghiệm thu Tuần 4 | Nghiệm thu Tuần 5 | Nghiệm thu Tuần 6 |
| Bài toán: Tự động tìm trạm sạc/tủ đổi pin phù hợp nhất cho Driver

Nội dung Project
• Map Matching vị trí realtime của driver.

• Xác định nhu cầu Charging/Battery Swap.

• Tìm các trạm/tủ phù hợp.

• Routing từ driver → station → destination.

• Tính ETA, distance, detour, traffic và queue.

• Ranking và lựa chọn trạm/tủ phù hợp nhất.

• Cung cấp realtime recommendation API. | • Map Matching Service: Xác định driver đang ở road segment nào.

• Charging/Swap Demand Detection: Xác định driver cần sạc hay đổi pin.

• Candidate Search Service: Tìm các trạm/tủ có khả năng phục vụ driver.

• Routing Service: Tính route, ETA, distance và detour.

• Station Ranking Model: Xếp hạng trạm dựa trên ETA, detour, queue, traffic và capacity.

• Recommendation API: Trả về trạm/tủ tốt nhất và các lựa chọn thay thế.

• Monitoring & Evaluation: Theo dõi latency, recommendation quality, acceptance, detour và waiting time. | • Map-match được vị trí driver realtime.

• Xác định được nhu cầu Charging/Battery Swap.

• Tìm được các candidate station/cabinet phù hợp.

• Tính được route, ETA và detour bằng road network.

• Trả về Best Station + Top-N alternatives.

• Recommendation có xét traffic, queue và capacity, không chỉ dựa trên khoảng cách.

• Đáp ứng yêu cầu realtime. | Map Matching

Xây dựng pipeline GPS realtime → road segment, xác định vị trí và hướng di chuyển của driver. | Demand Detection

Xác định driver có nhu cầu sạc/đổi pin dựa trên battery/SOC, trip, destination và lịch sử sử dụng. | Candidate + Routing

Tìm candidate station/cabinet và tính route, ETA, distance, detour từ driver tới từng điểm. | Recommendation Model

Xây dựng ranking dựa trên ETA, detour, traffic, queue, capacity và lựa chọn Best Station. | Realtime API + Evaluation

Xây dựng API recommendation, test performance và đánh giá recommendation trên dữ liệu lịch sử/replay. | Productionization

Tối ưu latency, caching, monitoring, logging, deployment và hoàn thiện tài liệu vận hành. |
| Nội dung được tách và ghép lại từ bảng đã cung cấp; xem sheet “Nghiem thu 6 tuan” để đọc riêng từng mốc nghiệm thu. |  |  |  |  |  |  |  |  |
## Sheet: Nghiem thu 6 tuan
| NGHIỆM THU THEO TUẦN |  |  |  |
| --- | --- | --- | --- |
| Người thực hiện: NGUYEN VAN NINH (S.AI.20K) |  |  |  |
| Bài toán: Tự động tìm trạm sạc/tủ đổi pin phù hợp nhất cho Driver |  |  |  |
| LỘ TRÌNH: MAP MATCHING → DEMAND → ROUTING → RANKING → API → VẬN HÀNH |  |  |  |
| Tuần | Hạng mục nghiệm thu | Nội dung nghiệm thu |  |
| Tuần 1 | Map Matching | Xây dựng pipeline GPS realtime → road segment, xác định vị trí và hướng di chuyển của driver. |  |
| Tuần 2 | Demand Detection | Xác định driver có nhu cầu sạc/đổi pin dựa trên battery/SOC, trip, destination và lịch sử sử dụng. |  |
| Tuần 3 | Candidate + Routing | Tìm candidate station/cabinet và tính route, ETA, distance, detour từ driver tới từng điểm. |  |
| Tuần 4 | Recommendation Model | Xây dựng ranking dựa trên ETA, detour, traffic, queue, capacity và lựa chọn Best Station. |  |
| Tuần 5 | Realtime API + Evaluation | Xây dựng API recommendation, test performance và đánh giá recommendation trên dữ liệu lịch sử/replay. |  |
| Tuần 6 | Productionization | Tối ưu latency, caching, monitoring, logging, deployment và hoàn thiện tài liệu vận hành. |  |
| Giữ nguyên nội dung, thứ tự tuần và tiêu chí trong thông tin được cung cấp; không bổ sung ngưỡng KPI hoặc cam kết nghiệm thu mới. |  |  |  |