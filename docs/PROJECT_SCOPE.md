# PROJECT_SCOPE

## Problem Statement
**Bài toán:** Tự động tìm trạm sạc/tủ đổi pin phù hợp nhất cho Driver

## Project Contents

- Map Matching vị trí realtime của driver (GPS → road segment)
- Xác định nhu cầu Charging/Battery Swap
- Tìm các trạm/tủ phù hợp (Candidate Search)
- Routing từ driver → station → destination
- Tính ETA, distance, detour, traffic và queue
- Ranking và lựa chọn trạm/tủ phù hợp nhất
- Cung cấp realtime recommendation API

## Deliverables

1. **Map Matching Service** - Xác định driver đang ở road segment nào
2. **Charging/Swap Demand Detection** - Xác định driver cần sạc hay đổi pin
3. **Candidate Search Service** - Tìm các trạm/tủ có khả năng phục vụ driver
4. **Routing Service** - Tính route, ETA, distance và detour
5. **Station Ranking Model** - Xếp hạng trạm dựa trên ETA, detour, queue, traffic và capacity
6. **Recommendation API** - Trả về trạm/tủ tốt nhất và các lựa chọn thay thế
7. **Monitoring & Evaluation** - Theo dõi latency, recommendation quality, acceptance, detour và waiting time

## Six-Week Progression

| Week | Milestone | Content |
|------|-----------|---------|
| Week 1 | Map Matching | GPS realtime → road segment, determine position and direction |
| Week 2 | Demand Detection | Battery/SOC based need determination |
| Week 3 | Candidate + Routing | Find candidates, compute routes, ETA, detour |
| Week 4 | Recommendation Model | Ranking based on ETA, detour, traffic, queue, capacity |
| Week 5 | Realtime API + Evaluation | Build API, test performance, evaluate recommendations |
| Week 6 | Productionization | Optimize latency, caching, monitoring, deployment |

## Completion Criteria

- Map-match được vị trí driver realtime
- Xác định được nhu cầu Charging/Battery Swap
- Tìm được các candidate station/cabinet phù hợp
- Tính được route, ETA và detour bằng road network
- Trả về Best Station + Top-N alternatives
- Recommendation có xét traffic, queue và capacity, không chỉ dựa trên khoảng cách
- Đáp ứng yêu cầu realtime

## Dataset

See: [DATA_CONTRACT.md](./DATA_CONTRACT.md)
