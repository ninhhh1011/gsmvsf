"""
Generate Realistic Hanoi Route History with H3 Resolution 11
============================================================

This script generates ~720 realistic historical routes across 8 major Hanoi corridors
using the real GraphHopper OSM routing engine (hanoi-patched.osm.pbf).

For each corridor:
- Main route (Recommended - e.g. direct/fastest)
- Habitual / Divergence route (Alternative drivers take to avoid congestion or access charging)
- Origin/Destination jittering (200m - 400m radius)
- H3 Resolution 11 cell sequence with 15m interpolation (continuous hex coverage)
- Realistic timestamps, drivers, trip metadata
- Grouped into 8 Route Families with weighted support and habitual reasons

Usage:
    python scripts/generate_hanoi_corridors_h3.py
"""

import sys
import os
import math
import time
import random
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

import h3
import psycopg2
from psycopg2.extras import execute_batch, execute_values

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Target database connection (IPv4 localhost for Windows Docker)
DB_URL = os.getenv("ROUTE_HISTORY_DATABASE_URL_SYNC", "postgresql://postgres:postgres@127.0.0.1:5432/route_history_db")
GRAPHHOPPER_URL = os.getenv("GRAPHHOPPER_URL", "http://127.0.0.1:8989")
H3_RESOLUTION = 11

# 8 Major Corridors in Hanoi with realistic waypoints and behavioral divergence
CORRIDORS = [
    {
        "family_id": "FAM_0001",
        "name": "Hà Đông – Nguyễn Trãi – Hoàn Kiếm",
        "origin_base": (20.9715, 105.7760),       # Quang Trung, Hà Đông
        "dest_base": (21.0245, 105.8560),         # Nhà Hát Lớn, Hoàn Kiếm
        "variant_prob": 0.40,                     # 40% đi tuyến thói quen
        "alt_waypoints": [(21.0020, 105.7950), (21.0110, 105.8030)], # Vành đai 3 trên cao & Trần Duy Hưng
        "reason_main": "Tuyến ngắn nhất qua trục Nguyễn Trãi - Tây Sơn",
        "reason_alt": "74% tài xế giờ cao điểm chọn Vành đai 3 trên cao để né 6 nút đèn đỏ ngã tư Nguyễn Trãi & Ngã Tư Sở",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0002",
        "name": "Tố Hữu – Lê Văn Lương – Ba Đình",
        "origin_base": (20.9820, 105.7620),       # Tố Hữu / Vạn Phúc, Hà Đông
        "dest_base": (21.0320, 105.8280),         # Kim Mã / Giảng Võ, Ba Đình
        "variant_prob": 0.45,
        "alt_waypoints": [(20.9850, 105.7800), (21.0120, 105.8050)], # Rẽ Mỗ Lao & Đường Láng
        "reason_main": "Tuyến thẳng trục Tố Hữu - Lê Văn Lương - Láng Hạ",
        "reason_alt": "68% tài xế rẽ ven sông Tô Lịch khi nút giao Hoàng Minh Giám ùn ứ xe",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0003",
        "name": "Cầu Giấy / QL32 – Kim Mã – Phố Cổ",
        "origin_base": (21.0420, 105.7650),       # Cầu Diễn / Hồ Tùng Mậu
        "dest_base": (21.0285, 105.8542),         # Bờ Hồ Hoàn Kiếm
        "variant_prob": 0.35,
        "alt_waypoints": [(21.0450, 105.7720), (21.0420, 105.8050)], # Hoàng Quốc Việt & Bưởi
        "reason_main": "Trục Hồ Tùng Mậu - Cầu Giấy - Kim Mã - Nguyễn Thái Học",
        "reason_alt": "71% tài xế chọn trục Hoàng Quốc Việt vì đường rộng thoáng, ít xung đột giao cắt",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0004",
        "name": "Pháp Vân / Linh Đàm – Vành đai 3 – Cầu Giấy / Nhật Tân",
        "origin_base": (20.9720, 105.8350),       # Bến xe Nước Ngầm, Hoàng Mai
        "dest_base": (21.0750, 105.8050),         # Xuân Đỉnh / Ngoại Giao Đoàn
        "variant_prob": 0.40,
        "alt_waypoints": [(21.0150, 105.7780), (21.0350, 105.7720)], # Đường gom Mễ Trì & Lê Đức Thọ
        "reason_main": "Vành đai 3 trên cao thẳng tuyến Pháp Vân - Mai Dịch",
        "reason_alt": "Tài xế rẽ đường gom Mễ Trì khi Vành đai 3 trên cao tê liệt giờ tan tầm",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0005",
        "name": "Times City / Vĩnh Tuy – Vành đai 2 – Cầu Giấy",
        "origin_base": (20.9980, 105.8680),       # Times City / Minh Khai
        "dest_base": (21.0360, 105.7820),         # ĐH Quốc Gia / Cầu Giấy
        "variant_prob": 0.30,
        "alt_waypoints": [(21.0100, 105.8350), (21.0220, 105.8150)], # Xã Đàn & Hào Nam
        "reason_main": "Vành đai 2 trên cao: Minh Khai - Đại La - Trường Chinh - Đường Láng",
        "reason_alt": "Tuyến đường phố thấp qua Ô Chợ Dừa để đón khách nội đô",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0006",
        "name": "Vinhomes Smart City – Đại lộ Thăng Long – Hoàn Kiếm",
        "origin_base": (20.9970, 105.7520),       # Vin Smart City, Tây Mỗ (cổng chính)
        "dest_base": (21.0245, 105.8560),         # Tràng Tiền / Hoàn Kiếm
        "variant_prob": 0.35,
        "alt_waypoints": [(21.0080, 105.7850), (21.0180, 105.8150)], # Lê Văn Lương & Láng Hạ
        "reason_main": "Đại lộ Thăng Long qua hầm chui Trung Hòa -> Trần Duy Hưng -> Tràng Thi",
        "reason_alt": "80% tài xế chuộng hầm chui Trung Hòa vì không có đèn đỏ",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0007",
        "name": "Vinhomes Ocean Park – Cầu Vĩnh Tuy – Trung tâm Hai Bà Trưng",
        "origin_base": (20.9960, 105.9380),       # Vin Ocean Park, Gia Lâm
        "dest_base": (21.0120, 105.8500),         # Vincom Bà Triệu
        "variant_prob": 0.25,
        "alt_waypoints": [(20.9850, 105.8850), (20.9950, 105.8600)], # Cầu Thanh Trì & Lĩnh Nam
        "reason_main": "Cổ Linh qua Cầu Vĩnh Tuy giai đoạn 2 -> Minh Khai -> Bà Triệu",
        "reason_alt": "83% tài xế chọn Cầu Vĩnh Tuy 2 vì 4 làn xe tốc độ cao, né kẹt xe Cầu Chương Dương",
        "trip_count": 90,
    },
    {
        "family_id": "FAM_0008",
        "name": "Lotte Mall Tây Hồ – Đường Láng – Thanh Xuân",
        "origin_base": (21.0720, 105.8150),       # Lotte Mall Tây Hồ, Võ Chí Công
        "dest_base": (21.0025, 105.8160),         # Royal City, Ngã Tư Sở
        "variant_prob": 0.30,
        "alt_waypoints": [(21.0400, 105.8200), (21.0250, 105.8220)], # Liễu Giai & Huỳnh Thúc Kháng
        "reason_main": "Võ Chí Công -> Bưởi -> Đường Láng ven sông Tô Lịch chạy thẳng",
        "reason_alt": "76% tài xế đi đường Láng vì mặt đường một chiều thoáng xe, ít rẽ trái",
        "trip_count": 90,
    },
]


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters between two lat/lng points."""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def interpolate_points(coords: List[Tuple[float, float]], step_m: float = 18.0) -> List[Tuple[float, float]]:
    """
    Interpolate dense points along polyline (~18m step)
    to guarantee continuous H3 Resolution 11 hexagon sequence.
    """
    if len(coords) < 2:
        return coords

    dense = [coords[0]]
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        dist = haversine_distance_m(p1[0], p1[1], p2[0], p2[1])

        if dist > step_m:
            steps = int(math.ceil(dist / step_m))
            for s in range(1, steps):
                frac = s / float(steps)
                lat = p1[0] + (p2[0] - p1[0]) * frac
                lng = p1[1] + (p2[1] - p1[1]) * frac
                dense.append((lat, lng))

        dense.append(p2)
    return dense


def query_graphhopper_route(points: List[Tuple[float, float]]) -> Dict[str, Any]:
    """Query GraphHopper for car route connecting ordered points."""
    query_parts = []
    for lat, lng in points:
        query_parts.append(f"point={lat:.6f},{lng:.6f}")
    query_str = "&".join(query_parts)
    url = f"{GRAPHHOPPER_URL}/route?{query_str}&profile=car&points_encoded=false&instructions=false"

    req = urllib.request.Request(url, headers={"User-Agent": "HanoiCorridorGenerator/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            return json.loads(resp.read().decode())
        raise RuntimeError(f"GraphHopper status: {resp.status}")


def coords_to_h3_res11(coords: List[Tuple[float, float]]) -> List[str]:
    """Convert interpolated coordinates into ordered non-duplicate H3 Res 11 cells."""
    dense = interpolate_points(coords, step_m=18.0)
    cells = []
    last_cell = None
    for lat, lng in dense:
        cell = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
        if cell != last_cell:
            cells.append(cell)
            last_cell = cell
    return cells


def jitter_coord(lat: float, lng: float, max_dist_m: float = 300.0) -> Tuple[float, float]:
    """Add small random jitter within max_dist_m."""
    d_lat = (random.uniform(-max_dist_m, max_dist_m) / 111320.0)
    d_lng = (random.uniform(-max_dist_m, max_dist_m) / (111320.0 * math.cos(math.radians(lat))))
    return (lat + d_lat, lng + d_lng)


def main():
    print("=" * 70)
    print(" HANOI ROUTE HISTORY GENERATOR (H3 RESOLUTION 11)")
    print(f" Target Database: {DB_URL}")
    print(f" GraphHopper URL: {GRAPHHOPPER_URL}")
    print("=" * 70)

    # 1. Connect to PostgreSQL
    print("\n[1/5] Connecting to route_history_db...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # 2. Clear old synthetic data
    print("[2/5] Cleaning existing historical data...")
    cur.execute("DELETE FROM historical_route_h3;")
    cur.execute("DELETE FROM historical_route_segments;")
    cur.execute("DELETE FROM route_family_members;" if table_exists(cur, "route_family_members") else "SELECT 1;")
    cur.execute("DELETE FROM route_families;")
    cur.execute("DELETE FROM historical_routes;")
    conn.commit()
    print("      Existing records cleared successfully.")

    # 3. Generate routes for each corridor
    print(f"\n[3/5] Generating ~{sum(c['trip_count'] for c in CORRIDORS)} historical routes across {len(CORRIDORS)} corridors...")

    all_routes = []
    all_h3_rows = []
    families = []
    now = datetime.now()

    route_counter = 0

    for c_idx, corridor in enumerate(CORRIDORS, 1):
        fam_id = corridor["family_id"]
        c_name = corridor["name"]
        o_base = corridor["origin_base"]
        d_base = corridor["dest_base"]
        trip_count = corridor["trip_count"]
        variant_prob = corridor["variant_prob"]
        alt_waypoints = corridor["alt_waypoints"]

        print(f"\n  --- Corridor {c_idx}/{len(CORRIDORS)}: {c_name} ({fam_id}) ---")
        
        rep_route_id = None
        corridor_routes = []
        unique_drivers = set()
        total_support = 0.0

        for t_idx in range(trip_count):
            route_counter += 1
            route_id = f"HR_{route_counter:05d}"
            trip_id = f"TRIP_{route_counter:05d}"
            driver_num = random.randint(1, 40)
            driver_id = f"DRIVER_{driver_num:02d}"
            unique_drivers.add(driver_id)

            # Random origin/dest with 200m - 350m jitter
            orig = jitter_coord(o_base[0], o_base[1], max_dist_m=random.uniform(150, 350))
            dest = jitter_coord(d_base[0], d_base[1], max_dist_m=random.uniform(150, 350))

            # Decide whether to take alternative/habitual route
            is_alt = (random.random() < variant_prob)
            if is_alt and alt_waypoints:
                # Add jittered waypoint
                wp = random.choice(alt_waypoints)
                wp_jittered = jitter_coord(wp[0], wp[1], max_dist_m=100.0)
                gh_points = [orig, wp_jittered, dest]
            else:
                gh_points = [orig, dest]

            # Query GraphHopper
            try:
                gh_resp = query_graphhopper_route(gh_points)
                path = gh_resp["paths"][0]
                dist_m = float(path["distance"])
                raw_coords = [(pt[1], pt[0]) for pt in path["points"]["coordinates"]] # [lat, lng]
            except Exception as e:
                # Fallback to direct coords on rare GH snap issue
                print(f"      GH routing warning for route {route_id}: {e}")
                raw_coords = [orig, dest]
                dist_m = haversine_distance_m(orig[0], orig[1], dest[0], dest[1])

            # Convert to H3 Resolution 11 sequence
            h3_cells = coords_to_h3_res11(raw_coords)

            # Generate realistic timestamp (distributed over last 14 days, commute peaks)
            days_ago = random.randint(0, 14)
            # Pick hour: 60% in morning/evening commute, 40% elsewhere
            if random.random() < 0.6:
                hour = random.choice([7, 8, 9, 17, 18, 19])
            else:
                hour = random.choice([10, 11, 12, 13, 14, 15, 16, 20, 21])
            minute = random.randint(0, 59)
            started_at = now - timedelta(days=days_ago, hours=(now.hour - hour), minutes=(now.minute - minute))
            duration_s = max(300, int(dist_m / (random.uniform(20.0, 35.0) * 1000 / 3600)))
            ended_at = started_at + timedelta(seconds=duration_s)

            # Weight recency
            recency_weight = max(0.2, 1.0 - (days_ago / 20.0))
            total_support += recency_weight

            all_routes.append((
                route_id,
                trip_id,
                driver_id,
                started_at,
                ended_at,
                orig[0],
                orig[1],
                dest[0],
                dest[1],
                dist_m,
                len(h3_cells)
            ))

            for seq_idx, cell in enumerate(h3_cells):
                all_h3_rows.append((route_id, seq_idx, cell))

            if rep_route_id is None:
                rep_route_id = route_id

            corridor_routes.append(route_id)

        # Compute initial bearing
        d_lat = d_base[0] - o_base[0]
        d_lng = d_base[1] - o_base[1]
        bearing = math.degrees(math.atan2(d_lng, d_lat)) % 360.0

        families.append((
            fam_id,
            rep_route_id,
            o_base[0],
            o_base[1],
            d_base[0],
            d_base[1],
            bearing,
            trip_count,
            len(unique_drivers),
            round(total_support, 2)
        ))

        print(f"      Created {trip_count} routes ({len(unique_drivers)} drivers, support: {total_support:.1f}, rep: {rep_route_id})")

    # 4. Bulk Insert into Database
    print(f"\n[4/5] Inserting into PostgreSQL ({len(all_routes)} routes, {len(all_h3_rows):,} H3 Res-11 cells)...")

    # Insert historical_routes
    route_sql = """
        INSERT INTO historical_routes (
            route_id, trip_id, driver_id, started_at, ended_at,
            origin_lat, origin_lng, dest_lat, dest_lng,
            total_distance_m, segment_count
        ) VALUES %s
    """
    execute_values(cur, route_sql, all_routes, page_size=500)
    conn.commit()
    print("      -> historical_routes inserted.")

    # Insert historical_route_h3 in batches
    h3_sql = """
        INSERT INTO historical_route_h3 (route_id, seq, h3_cell_res11)
        VALUES %s
    """
    execute_values(cur, h3_sql, all_h3_rows, page_size=2000)
    conn.commit()
    print("      -> historical_route_h3 inserted.")

    # Insert route_families
    fam_sql = """
        INSERT INTO route_families (
            family_id, representative_route_id,
            origin_lat, origin_lng, dest_lat, dest_lng,
            direction_bearing, trip_count, unique_driver_count, weighted_support
        ) VALUES %s
    """
    execute_values(cur, fam_sql, families)
    conn.commit()
    print("      -> route_families inserted.")

    # 5. Summary & Verification
    print("\n[5/5] Verification & Statistics:")
    cur.execute("SELECT count(*) FROM historical_routes;")
    r_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM historical_route_h3;")
    h_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM route_families;")
    f_count = cur.fetchone()[0]

    cur.execute("SELECT family_id, trip_count, unique_driver_count, weighted_support FROM route_families ORDER BY family_id;")
    fam_stats = cur.fetchall()

    print(f"      Total Routes: {r_count:,}")
    print(f"      Total H3 Res-11 Cells: {h_count:,}")
    print(f"      Total Families: {f_count}")
    print("\n  Family Breakdown:")
    for f in fam_stats:
        print(f"    - {f[0]}: {f[1]} trips, {f[2]} drivers, support {f[3]:.1f}")

    cur.close()
    conn.close()
    print("\n" + "=" * 70)
    print(" SUCCESS: Realistic Hanoi H3 Res-11 history generated and loaded!")
    print("=" * 70)


def table_exists(cur, table_name: str) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = %s
        );
    """, (table_name,))
    return cur.fetchone()[0]


if __name__ == "__main__":
    main()
