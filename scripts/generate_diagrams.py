"""
Generate High-Resolution Architecture & Communication Diagrams for Presentation.
Focus: Visual components, communication protocols, data flows, dynamic routing.
Zero test metrics, minimal text, maximum clarity.
"""
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

os.makedirs("docs/diagrams", exist_ok=True)

# Color Palette
C_NAVY = "#0F172A"
C_BLUE = "#2563EB"
C_EMERALD = "#059669"
C_AMBER = "#D97706"
C_RED = "#DC2626"
C_CARD_BG = "#FFFFFF"
C_BORDER = "#CBD5E1"
C_BG = "#F8FAFC"
C_DARK_TEXT = "#0F172A"
C_MUTED = "#64748B"

def draw_box(ax, x, y, w, h, title, sub="", color="#2563EB", bg="#FFFFFF", text_color="#0F172A", badge="", title_size=11):
    # Rounded box
    box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.03",
                                 facecolor=bg, edgecolor=color, linewidth=2, zorder=2)
    ax.add_patch(box)
    
    # Title & Subtext
    cx = x + w / 2.0
    if sub:
        cy_title = y + h * 0.62
        cy_sub = y + h * 0.28
        ax.text(cx, cy_title, title, ha='center', va='center', fontsize=title_size, fontweight='bold', color=text_color, zorder=3)
        ax.text(cx, cy_sub, sub, ha='center', va='center', fontsize=8.5, color=C_MUTED, zorder=3)
    else:
        ax.text(cx, y + h / 2.0, title, ha='center', va='center', fontsize=title_size, fontweight='bold', color=text_color, zorder=3)

    if badge:
        # Badge on top-right or top-left
        bx = x + 0.02
        by = y + h - 0.03
        ax.text(bx, by, badge, ha='left', va='top', fontsize=7.5, fontweight='bold', color=color, zorder=4)

def draw_arrow(ax, x1, y1, x2, y2, label="", color="#334155", lw=2, label_color="#1E293B", offset_y=0.02):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6", color=color, lw=lw),
                zorder=5)
    if label:
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0 + offset_y
        ax.text(mx, my, label, ha='center', va='center', fontsize=8.5, fontweight='bold',
                color=label_color, backgroundcolor='#FFFFFF', zorder=6,
                bbox=dict(boxstyle='square,pad=0.2', facecolor='#FFFFFF', edgecolor='none', alpha=0.9))

# ==============================================================================
# DIAGRAM 1: 3-TIER ARCHITECTURE & SERVICE COMMUNICATION
# ==============================================================================
def generate_architecture_diagram():
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=200)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.axis('off')

    # Header
    ax.text(0.5, 0.95, "KIẾN TRÚC HỆ THỐNG 3 TẦNG & GIAO TIẾP LIÊN DỊCH VỤ", ha='center', va='center',
            fontsize=18, fontweight='bold', color=C_NAVY)
    ax.text(0.5, 0.91, "Cơ chế chịu lỗi High Availability (Dual API Replicas) & Các giao thức truyền thông",
            ha='center', va='center', fontsize=11, color=C_MUTED)

    # --- CLIENT TIER (Top) ---
    draw_box(ax, 0.35, 0.77, 0.3, 0.08, "Client / Tài xế GSM", "Web Browser • Mobile Driver Cockpit",
             color=C_NAVY, bg="#FFFFFF", badge="CLIENT TIER")

    # --- TIER 1: PRESENTATION (Middle-Top) ---
    draw_box(ax, 0.30, 0.58, 0.4, 0.10, "Tier 1: Nginx Reverse Proxy & Load Balancer",
             "Container: ev_frontend • Port 3000 • Thuật toán least_conn", color=C_BLUE, bg="#FFFFFF", badge="TIER 1: REVERSE PROXY")

    # Arrow: Client -> Nginx
    draw_arrow(ax, 0.5, 0.77, 0.5, 0.68, "HTTP / JSON (Port 3000)", color=C_BLUE)

    # --- TIER 2: APPLICATION CLUSTER (Middle) ---
    # Container boundary for Tier 2
    t2_bg = patches.FancyBboxPatch((0.08, 0.33), 0.84, 0.17, boxstyle="round,pad=0.02,rounding_size=0.02",
                                  facecolor="#F1F5F9", edgecolor=C_EMERALD, linestyle="--", linewidth=1.5, zorder=1)
    ax.add_patch(t2_bg)
    ax.text(0.10, 0.48, "TIER 2: APPLICATION CLUSTER (STATELESS DUAL REPLICAS)", fontsize=9, fontweight='bold', color=C_EMERALD)

    draw_box(ax, 0.12, 0.36, 0.36, 0.10, "FastAPI Instance 1 (ev_api_1)",
             "Port 8000 • In-Process Engine • Simulator", color=C_EMERALD, bg="#FFFFFF")
    draw_box(ax, 0.52, 0.36, 0.36, 0.10, "FastAPI Instance 2 (ev_api_2)",
             "Port 8002 • In-Process Engine • Failover", color=C_EMERALD, bg="#FFFFFF")

    # Arrows: Nginx -> api_1 and api_2
    draw_arrow(ax, 0.42, 0.58, 0.30, 0.46, "HTTP proxy", color=C_EMERALD)
    draw_arrow(ax, 0.58, 0.58, 0.70, 0.46, "Failover (0s)", color=C_EMERALD)

    # --- TIER 3: PERSISTENCE & COMPUTING (Bottom) ---
    draw_box(ax, 0.05, 0.08, 0.28, 0.14, "PostgreSQL 16 + PostGIS",
             "Container: ev_db (Port 5432)\nMạng đường bộ HN & Snapshot DB", color="#334155", bg="#FFFFFF", badge="PERSISTENCE")
    
    draw_box(ax, 0.36, 0.08, 0.28, 0.14, "Redis 7.4 In-Memory",
             "Container: ev_redis (Port 6379)\nL1 Snapshot Cache & Driver State", color=C_RED, bg="#FFFFFF", badge="CACHE & STATE")

    draw_box(ax, 0.67, 0.08, 0.28, 0.14, "GraphHopper 11.0 Engine",
             "Container: ev_graphhopper (Port 8989)\nRouting đa chặng & Map Matching", color=C_AMBER, bg="#FFFFFF", badge="ROUTING CORE")

    # Arrows: Tier 2 -> Tier 3
    draw_arrow(ax, 0.22, 0.36, 0.19, 0.22, "asyncpg (TCP:5432)", color="#334155")
    draw_arrow(ax, 0.40, 0.36, 0.48, 0.22, "Redis Protocol (TCP:6379)", color=C_RED)
    draw_arrow(ax, 0.78, 0.36, 0.81, 0.22, "HTTP REST (/route)", color=C_AMBER)

    plt.tight_layout()
    fig.savefig("docs/diagrams/arch_communication.png", bbox_inches='tight', dpi=200)
    plt.close(fig)
    print("Saved docs/diagrams/arch_communication.png")

# ==============================================================================
# DIAGRAM 2: DATA FLOW & COMPONENT INTERACTION
# ==============================================================================
def generate_data_flow_diagram():
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=200)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.axis('off')

    # Header
    ax.text(0.5, 0.95, "SƠ ĐỒ LUỒNG DỮ LIỆU THỜI GIAN THỰC (REALTIME PIPELINE)", ha='center', va='center',
            fontsize=18, fontweight='bold', color=C_NAVY)
    ax.text(0.5, 0.91, "Chuỗi 5 bước xử lý từ lúc nhận tọa độ GPS đến khi trả kết quả tối ưu (< 190ms)",
            ha='center', va='center', fontsize=11, color=C_MUTED)

    # 5 Horizontal Steps
    steps = [
        ("1. GPS Telemetry", "Tài xế gửi GPS & % Pin\nHybridTrigger (10s/50m)", C_BLUE, 0.05),
        ("2. Demand Physics", "Kiểm tra pin 19 dòng xe VF\nĐảm bảo pin tới đích >=15%", C_EMERALD, 0.24),
        ("3. Spatial Filter", "Lọc nhanh 30 trạm sạc\nLoại trạm hỏng & sai cổng", C_AMBER, 0.43),
        ("4. Routing Core", "GraphHopper tính đồng thời\n8 route (Xe->Trạm->Đích)", "#334155", 0.62),
        ("5. Cost Ranking", "Tối ưu Tổng chi phí\nĐi đường + Sạc + Hàng đợi", C_RED, 0.81)
    ]

    for title, desc, color, x in steps:
        draw_box(ax, x, 0.48, 0.15, 0.24, title, desc, color=color, bg="#FFFFFF", title_size=10.5)

    # Arrows connecting steps
    for i in range(4):
        x1 = steps[i][3] + 0.15
        x2 = steps[i+1][3]
        draw_arrow(ax, x1, 0.60, x2, 0.60, "", color=C_NAVY, lw=2.5)

    # Bottom Interaction with Backend Engines
    draw_box(ax, 0.08, 0.12, 0.24, 0.18, "PostgreSQL / PostGIS", "Khớp GPS vào tim đường\n& Truy vấn snapshot giao thông", color="#334155")
    draw_box(ax, 0.38, 0.12, 0.24, 0.18, "Redis L1 Cache", "Đọc trạng thái xe & hàng đợi trạm\nvới tốc độ sub-millisecond", color=C_RED)
    draw_box(ax, 0.68, 0.12, 0.24, 0.18, "GraphHopper 11.0", "Tính toán đa luồng 8 routes song song\n& phạt trọng số né đường kẹt", color=C_AMBER)

    # Connect top pipeline to bottom storage
    draw_arrow(ax, 0.125, 0.48, 0.20, 0.30, "MapMatch", color="#334155")
    draw_arrow(ax, 0.505, 0.48, 0.50, 0.30, "L1 Snapshot", color=C_RED)
    draw_arrow(ax, 0.695, 0.48, 0.80, 0.30, "8x Parallel Routes", color=C_AMBER)

    plt.tight_layout()
    fig.savefig("docs/diagrams/data_flow_sequence.png", bbox_inches='tight', dpi=200)
    plt.close(fig)
    print("Saved docs/diagrams/data_flow_sequence.png")

# ==============================================================================
# DIAGRAM 3: DYNAMIC AVOIDANCE & LOAD BALANCING
# ==============================================================================
def generate_avoidance_diagram():
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=200)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.axis('off')

    # Header
    ax.text(0.5, 0.95, "CƠ CHẾ NÉ ĐƯỜNG TẮC & CÂN BẰNG TẢI TRẠM SẠC REALTIME", ha='center', va='center',
            fontsize=18, fontweight='bold', color=C_NAVY)
    ax.text(0.5, 0.91, "Xử lý 2 bài toán lớn trong vận hành: Tắc nghẽn giao thông và Hiệu ứng dồn toa tại trạm",
            ha='center', va='center', fontsize=11, color=C_MUTED)

    # Left Container: Traffic Detour
    draw_box(ax, 0.06, 0.10, 0.42, 0.74, "1. TỰ ĐỘNG NÉ ĐƯỜNG TẮC (CONGESTION DETOUR)",
             "", color=C_RED, bg="#FFFFFF", badge="GRAPHHOPPER CUSTOM MODEL")
    
    draw_box(ax, 0.09, 0.56, 0.36, 0.14, "Tuyến Trực Tiếp (3.6 km)", "Dính đường đỏ (tắc nặng)\nThời gian thực tế: 32 phút", color=C_RED, bg="#FEF2F2")
    draw_box(ax, 0.09, 0.34, 0.36, 0.14, "Tuyến Vòng Tránh (4.4 km)", "Custom Model phạt đường đỏ -> Đi vòng đường thoáng\nThời gian thực tế: 20 phút (Nhanh hơn 12 phút!)", color=C_EMERALD, bg="#ECFDF5")
    draw_arrow(ax, 0.27, 0.56, 0.27, 0.48, "GraphHopper tự đổi lộ trình", color=C_EMERALD)

    ax.text(0.27, 0.18, "NGUYÊN LÝ: Không chọn đường ngắn nhất theo km,\nmà chọn đường tốn ít thời gian nhất!",
            ha='center', va='center', fontsize=9.5, fontweight='bold', color=C_NAVY)

    # Right Container: Station Herd Avoidance
    draw_box(ax, 0.52, 0.10, 0.42, 0.74, "2. CÂN BẰNG TẢI TRẠM (HERD AVOIDANCE)",
             "", color=C_AMBER, bg="#FFFFFF", badge="DYNAMIC QUEUE COST")

    draw_box(ax, 0.55, 0.56, 0.36, 0.14, "Trạm A: Cách 1 km (Đang kẹt)", "3 xe đang đợi sạc -> Hàng đợi +45 phút\nTổng thời gian: 15p (đi) + 45p (đợi) = 60 phút", color=C_AMBER, bg="#FFFBEB")
    draw_box(ax, 0.55, 0.34, 0.36, 0.14, "Trạm B: Cách 3 km (Còn chỗ)", "Không có hàng đợi -> Sạc được ngay\nTổng thời gian: 22p (đi) + 0p (đợi) = 22 phút!", color=C_BLUE, bg="#EFF6FF")
    draw_arrow(ax, 0.73, 0.56, 0.73, 0.48, "Hệ thống tự động chuyển hướng xe sang Trạm B", color=C_BLUE)

    ax.text(0.73, 0.18, "NGUYÊN LÝ: Phạt nặng thời gian chờ đợi (T_queue),\ntriệt tiêu hiện tượng dồn toa vào 1 trạm duy nhất!",
            ha='center', va='center', fontsize=9.5, fontweight='bold', color=C_NAVY)

    plt.tight_layout()
    fig.savefig("docs/diagrams/dynamic_avoidance.png", bbox_inches='tight', dpi=200)
    plt.close(fig)
    print("Saved docs/diagrams/dynamic_avoidance.png")

# ==============================================================================
# DIAGRAM 4: IN-PROCESS CORE ENGINE
# ==============================================================================
def generate_core_engine_diagram():
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=200)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.axis('off')

    # Header
    ax.text(0.5, 0.95, "THUẬT TOÁN ĐIỀU PHỐI & HÀM CHI PHÍ TỐI ƯU (COST FUNCTION)", ha='center', va='center',
            fontsize=18, fontweight='bold', color=C_NAVY)
    ax.text(0.5, 0.91, "Cơ chế đánh giá đa biến: Pin vật lý + Không gian trạm + Độ trễ kẹt xe + Hàng đợi",
            ha='center', va='center', fontsize=11, color=C_MUTED)

    # Left: Vehicle Physics
    draw_box(ax, 0.06, 0.18, 0.42, 0.65, "Mô hình Năng lượng Vật lý (19 Dòng xe VF)",
             "", color=C_EMERALD, bg="#FFFFFF", badge="VEHICLE ENERGY PHYSICS")
    
    vf_items = [
        ("VF e34 / VF 8 / VF 9", "Ô tô điện -> Định tuyến trạm sạc (18 - 30 phút)"),
        ("Klara / Feliz / Evo 200", "Xe máy điện -> Định tuyến tủ đổi pin (~6 phút)"),
        ("Đặc tính tiêu thụ kWh/km", "Tính toán theo tải trọng và cấu hình từng dòng xe"),
        ("Ngưỡng an toàn dự phòng", "Bắt buộc SOC sau khi đến đích phải >= 15% (min 1.0 km)")
    ]
    for i, (head, sub) in enumerate(vf_items):
        y_pos = 0.64 - i * 0.12
        draw_box(ax, 0.08, y_pos, 0.38, 0.09, head, sub, color=C_BORDER, bg="#F8FAFC", title_size=9.5)

    # Right: Cost Formula & Components
    draw_box(ax, 0.52, 0.18, 0.42, 0.65, "Hàm Chi phí Toàn diện (Cost Optimization)",
             "", color=C_BLUE, bg="#FFFFFF", badge="COST FUNCTION")

    # Big Formula Pill
    pill = patches.FancyBboxPatch((0.54, 0.66), 0.38, 0.10, boxstyle="round,pad=0.02,rounding_size=0.02",
                                 facecolor="#FEF2F2", edgecolor=C_RED, linewidth=1.5, zorder=2)
    ax.add_patch(pill)
    ax.text(0.73, 0.72, "TỔNG THỜI GIAN =", ha='center', va='center', fontsize=10, fontweight='bold', color=C_NAVY, zorder=3)
    ax.text(0.73, 0.68, "T_detour + T_service + T_queue + T_traffic_delay", ha='center', va='center', fontsize=10.5, fontweight='bold', color=C_RED, zorder=3)

    cost_items = [
        ("T_detour (Thời gian đi đường)", "Thời gian lái xe vòng ghé trạm rồi mới về điểm đến"),
        ("T_service (Thời gian sạc/đổi)", "Thời gian nạp năng lượng (Ô tô sạc vs Xe máy đổi pin)"),
        ("T_queue (Thời gian chờ đợi)", "Số lượng xe đang xếp hàng x Thời gian phục vụ mỗi xe"),
        ("T_traffic_delay (Độ trễ kẹt xe)", "Độ trễ phát sinh do ùn tắc trên các cung đường dẫn vào trạm")
    ]
    for i, (head, sub) in enumerate(cost_items):
        y_pos = 0.52 - i * 0.10
        draw_box(ax, 0.54, y_pos, 0.38, 0.08, head, sub, color=C_BORDER, bg="#F8FAFC", title_size=9.5)

    # Bottom Banner
    b_pill = patches.FancyBboxPatch((0.06, 0.04), 0.88, 0.09, boxstyle="round,pad=0.02,rounding_size=0.02",
                                   facecolor="#EFF6FF", edgecolor=C_BLUE, linewidth=1, zorder=2)
    ax.add_patch(b_pill)
    ax.text(0.5, 0.085, "KẾT QUẢ ĐẦU RA: Hệ thống trả về Trạm Sạc Top-1 tối ưu nhất + Các phương án thay thế, kèm minh bạch toàn bộ các chỉ số chi phí.",
            ha='center', va='center', fontsize=10.5, fontweight='bold', color=C_BLUE, zorder=3)

    plt.tight_layout()
    fig.savefig("docs/diagrams/core_engine.png", bbox_inches='tight', dpi=200)
    plt.close(fig)
    print("Saved docs/diagrams/core_engine.png")

if __name__ == "__main__":
    generate_architecture_diagram()
    generate_data_flow_diagram()
    generate_avoidance_diagram()
    generate_core_engine_diagram()
