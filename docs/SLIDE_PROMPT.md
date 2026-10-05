# Prompt cho AI tạo Slide - EV Charging Architecture Review

## 1. Thông tin dự án

**Tên:** EV Charging Recommendation System
**Mục đích:** Tự động gợi ý trạm sạc/đổi pin tốt nhất cho tài xế xe điện VinFast
**Đối tượng:** Mentor (kỹ thuật, hiểu architecture)

## 2. Kiến trúc hệ thống

### Layers (từ trên xuống)
- **Client Application** → Giao diện người dùng
- **FastAPI Gateway** → Điều phối request
- **Core Services:**
  - Map Matching: Snap GPS vào road segment (GraphHopper)
  - Demand Detection: Kiểm tra SOC, xác định có cần dịch vụ không
  - Candidate Search: Tìm các trạm phù hợp, filter eligible stations
  - Ranking: Xếp hạng theo TOTAL_SERVICE_COMPLETION_V1 (cost = travel + queue + service + detour)
- **Data Layer:**
  - GraphHopper: Routing engine
  - PostgreSQL: Lưu snapshots (station, queue, traffic) - immutable authority
  - Redis: 2 mục đích (1) GPS state với CAS, (2) Snapshot cache với TTL

### Request Flow (5 bước)
1. GPS Input → Raw coordinates từ driver
2. Map Matching → Snap to road segment
3. Demand Detection → Check if service needed (SOC analysis)
4. Candidate Search → Find eligible stations + route
5. Ranking → Score và return best + top-N alternatives

### Component Communication
- FastAPI Gateway là center
- GraphHopper: Route calculation
- PostgreSQL: Snapshot authority (immutable)
- Redis: GPS state (CAS-based) + Snapshot cache (TTL-based)

### Workflow Orchestration
- RecommendationWorkflow điều phối:
  1. CandidateSearchService.search() → resolve snapshots, route, filter
  2. RankingService.recommend() → TOTAL_SERVICE_COMPLETION_V1
- Conflict Handling: CandidateStateChanged → retry once → HTTP 409

### Snapshot Architecture
- 3 loại snapshot: Station, Queue, Traffic
- SnapshotResolver: Redis cache → PostgreSQL → return
- Ingestion: Simulator → IngestionService → PostgreSQL (internal)

### Application Lifecycle (3-Tier)
- **Startup:** httpx client, asyncpg pool, Redis, SnapshotResolver, Workflow, Simulator
- **Runtime:** Request processing, snapshot caching, GPS state updates, background simulation
- **Shutdown:** Simulator.stop(), clear state, close connections

## 3. Key Design Rules

1. **No Business Logic in Frontend** - UI chỉ call API, logic ở backend
2. **PostgreSQL = Snapshot Authority** - Redis là cache optional, PG là truth
3. **Conflict = 409 + Retry** - Queue surge → retry once
4. **GPS State with CAS** - Per-driver updates với version-based conflict detection
5. **Shared Routing Adapter** - Single httpx client cho tất cả routing calls

## 4. Yêu cầu Slide

### Phong cách
- Professional, clean, minimalist
- Màu sắc: Navy/Blue/Teal (không quá nhiều màu)
- Font: Sans-serif, rõ ràng
- Ít text, nhiều diagram/flow chart
- 16:9 aspect ratio

### Cấu trúc (8-9 slides)

1. **Title Slide** - Tên dự án, "Architecture Review"
2. **System Overview** - 4 layers visualization (Client → Gateway → Services → Data)
3. **Request Flow** - 5 bước flow chart
4. **Component Communication** - Diagrammatic view của các components và cách chúng giao tiếp
5. **Recommendation Workflow** - Orchestration flow + conflict handling
6. **Snapshot Architecture** - 3 loại snapshot + resolver flow
7. **Key Design Rules** - 5 nguyên tắc architecture (ngắn gọn)
8. **Application Lifecycle** - Startup/Runtime/Shutdown
9. **Questions?** - Slide kết thúc

### KHÔNG BAO GỒM
- API endpoints/paths (POST /drivers/{id}/location, etc.)
- Code snippets
- Week labels (W1, W2, W3, W4)
- Technical jargon không cần thiết
- Quá nhiều màu sắc
- Animated transitions phức tạp

### Format output
- PowerPoint (.pptx)
- Hoặc HTML presentation
- Mỗi slide rõ ràng, đủ info để explain nhưng không overload

## 5. Prompt template cho AI

```
Tạo presentation về System Architecture cho EV Charging Recommendation System.

**Đối tượng:** Mentor (technical)
**Style:** Professional, clean, minimalist, 16:9
**Màu:** Navy/Blue/Teal palette

**Nội dung cần có:**
1. System Overview - 4 layers: Client → Gateway → Services (Map Matching, Demand Detection, Candidate Search, Ranking) → Data (GraphHopper, PostgreSQL, Redis)
2. Request Flow - 5 steps: GPS → Map Match → Demand → Search → Rank
3. Component Communication - FastAPI center, GraphHopper/PostgreSQL/Redis around
4. Recommendation Workflow - CandidateSearch + Ranking + Conflict retry
5. Snapshot Architecture - Station/Queue/Traffic snapshots, Redis cache → PostgreSQL
6. Key Design Rules - 5 rules: no biz logic frontend, PG authority, conflict retry, GPS CAS, shared routing adapter
7. Lifecycle - Startup/Runtime/Shutdown
8. Questions slide

**KHÔNG gồm:** API paths, W1/W2 labels, code snippets
```
