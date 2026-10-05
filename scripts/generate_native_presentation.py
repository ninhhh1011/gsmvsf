"""
Generate GSMVSF 100% Native Vector PowerPoint Presentation.
ULTRA CLEAN EDITION:
- Extremely minimal text: short punchy bullet points (3-6 words each).
- No long paragraphs or wordy sentences.
- High visual whitespace and breathing room.
- Native PowerPoint shapes and text frames (Zero text overlaps).
- Absolutely NO test suites or test metrics.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

# Color Palette
C_NAVY = RGBColor(15, 23, 42)        # #0F172A
C_BLUE = RGBColor(37, 99, 235)       # #2563EB
C_EMERALD = RGBColor(5, 150, 105)    # #059669
C_AMBER = RGBColor(217, 119, 6)      # #D97706
C_RED = RGBColor(220, 38, 38)        # #DC2626
C_SLATE = RGBColor(51, 65, 85)       # #334155
C_BG_LIGHT = RGBColor(248, 250, 252) # #F8FAFC
C_BORDER = RGBColor(226, 232, 240)   # #E2E8F0
C_MUTED = RGBColor(100, 116, 139)    # #64748B
C_DARK = RGBColor(30, 41, 59)        # #1E293B

def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def set_slide_bg(slide, color):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = color
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category_text="KIẾN TRÚC & HỆ THỐNG"):
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.3))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        tf_cat.margin_left = tf_cat.margin_top = tf_cat.margin_right = tf_cat.margin_bottom = 0
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = C_EMERALD

        t_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.55))
        tf_t = t_box.text_frame
        tf_t.word_wrap = True
        tf_t.margin_left = tf_t.margin_top = tf_t.margin_right = tf_t.margin_bottom = 0
        p_t = tf_t.paragraphs[0]
        p_t.text = title_text
        p_t.font.size = Pt(22)
        p_t.font.bold = True
        p_t.font.color.rgb = C_NAVY

    def add_card(slide, x, y, w, h, bg_color=RGBColor(255, 255, 255), border_color=C_BORDER, line_width=1.5):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        if border_color:
            card.line.color.rgb = border_color
            card.line.width = Pt(line_width)
        else:
            card.line.fill.background()
        return card

    def add_banner(slide, y, text, bg_color, border_color, text_color, icon_text=""):
        banner = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y, Inches(11.733), Inches(0.65))
        banner.fill.solid()
        banner.fill.fore_color.rgb = bg_color
        banner.line.color.rgb = border_color
        banner.line.width = Pt(1.5)

        tb = slide.shapes.add_textbox(Inches(1.0), y + Inches(0.12), Inches(11.333), Inches(0.45))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        full_text = f"{icon_text}  {text}" if icon_text else text
        p.text = full_text
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = text_color
        return banner

    # ==========================================================
    # SLIDE 1: COVER
    # ==========================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1, C_NAVY)

    # Subtitle Pill
    add_card(s1, Inches(0.8), Inches(1.5), Inches(4.5), Inches(0.45),
             bg_color=RGBColor(30, 41, 59), border_color=C_EMERALD)
    tb_pill = s1.shapes.add_textbox(Inches(0.9), Inches(1.53), Inches(4.3), Inches(0.4))
    tf_pill = tb_pill.text_frame
    tf_pill.margin_left = tf_pill.margin_top = tf_pill.margin_right = tf_pill.margin_bottom = 0
    p_pill = tf_pill.paragraphs[0]
    p_pill.text = "HỆ THỐNG ĐIỀU PHỐI ĐỘI XE ĐIỆN GSM / VINFAST"
    p_pill.font.size = Pt(10)
    p_pill.font.bold = True
    p_pill.font.color.rgb = C_EMERALD

    # Main Title
    t_box1 = s1.shapes.add_textbox(Inches(0.8), Inches(2.3), Inches(11.7), Inches(1.8))
    tf1 = t_box1.text_frame
    tf1.word_wrap = True
    tf1.margin_left = tf1.margin_top = tf1.margin_right = tf1.margin_bottom = 0
    p1 = tf1.paragraphs[0]
    p1.text = "GSMVSF: EV Dynamic Charging\nRecommendation & Routing Engine"
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(255, 255, 255)

    desc_box1 = s1.shapes.add_textbox(Inches(0.8), Inches(4.3), Inches(11.0), Inches(0.6))
    tf_desc1 = desc_box1.text_frame
    tf_desc1.word_wrap = True
    tf_desc1.margin_left = tf_desc1.margin_top = tf_desc1.margin_right = tf_desc1.margin_bottom = 0
    p_desc1 = tf_desc1.paragraphs[0]
    p_desc1.text = "Điều phối trạm sạc & tủ đổi pin thông minh thời gian thực cho tài xế xe điện VinFast."
    p_desc1.font.size = Pt(16)
    p_desc1.font.color.rgb = RGBColor(203, 213, 225)

    badges = [
        ("High Availability", "Dual API Replicas • Failover 0s"),
        ("Độ trễ P50 < 190ms", "Concurrent Routing 8x"),
        ("19 Dòng xe VinFast", "Vật lý pin & an toàn SOC"),
        ("Né Kẹt Xe Realtime", "GraphHopper Custom Model"),
    ]
    for i, (b_title, b_sub) in enumerate(badges):
        bx = Inches(0.8 + i * 2.95)
        by = Inches(5.5)
        add_card(s1, bx, by, Inches(2.8), Inches(1.2), bg_color=RGBColor(30, 41, 59), border_color=RGBColor(51, 65, 85))
        tb = s1.shapes.add_textbox(bx + Inches(0.15), by + Inches(0.2), Inches(2.5), Inches(0.8))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p_bt = tf.paragraphs[0]
        p_bt.text = b_title
        p_bt.font.size = Pt(13)
        p_bt.font.bold = True
        p_bt.font.color.rgb = C_EMERALD

        p_bs = tf.add_paragraph()
        p_bs.text = b_sub
        p_bs.font.size = Pt(10)
        p_bs.font.color.rgb = RGBColor(148, 163, 184)

    s1.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 1 (30s):\n"
        "- Xin chào mọi người, đây là hệ thống GSMVSF — Điều phối và đề xuất trạm sạc xe điện thông minh theo thời gian thực cho đội xe GSM VinFast.\n"
        "- Hệ thống tối ưu đa biến: vừa an toàn pin, vừa né kẹt xe, vừa tránh quá tải trạm với độ trễ phản hồi dưới 200 mili-giây."
    )

    # ==========================================================
    # SLIDE 2: 3-TIER ARCHITECTURE (ULTRA CLEAN)
    # ==========================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s2, C_BG_LIGHT)
    add_header(s2, "Kiến trúc Hệ thống 3 Tầng & Giao tiếp Liên Dịch vụ", "KIẾN TRÚC & GIAO TIẾP")

    # Tier 1: Nginx (Top Center)
    add_card(s2, Inches(4.3), Inches(1.4), Inches(4.733), Inches(0.9), border_color=C_BLUE, line_width=2)
    tb_t1 = s2.shapes.add_textbox(Inches(4.5), Inches(1.5), Inches(4.333), Inches(0.7))
    tf_t1 = tb_t1.text_frame
    tf_t1.word_wrap = True
    tf_t1.margin_left = tf_t1.margin_top = tf_t1.margin_right = tf_t1.margin_bottom = 0
    p = tf_t1.paragraphs[0]
    p.text = "TIER 1: NGINX REVERSE PROXY"
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = C_BLUE
    p2 = tf_t1.add_paragraph()
    p2.text = "Port 3000 • Cân bằng tải least_conn • Tiếp nhận request Web & Mobile"
    p2.font.size = Pt(10)
    p2.font.color.rgb = C_DARK

    # Arrow Down
    arr_t1 = s2.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(6.5), Inches(2.35), Inches(0.35), Inches(0.3))
    arr_t1.fill.solid()
    arr_t1.fill.fore_color.rgb = C_BLUE
    arr_t1.line.fill.background()

    # Tier 2 Cluster Boundary Box
    add_card(s2, Inches(0.8), Inches(2.7), Inches(11.733), Inches(1.75),
             bg_color=RGBColor(241, 245, 249), border_color=C_EMERALD, line_width=1.5)
    
    tb_t2_lbl = s2.shapes.add_textbox(Inches(1.0), Inches(2.78), Inches(6.0), Inches(0.25))
    tf_t2_lbl = tb_t2_lbl.text_frame
    tf_t2_lbl.margin_left = tf_t2_lbl.margin_top = tf_t2_lbl.margin_right = tf_t2_lbl.margin_bottom = 0
    p = tf_t2_lbl.paragraphs[0]
    p.text = "TIER 2: CỤM BACKEND STATELESS (DUAL REPLICAS)"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    # Instance 1
    add_card(s2, Inches(1.0), Inches(3.08), Inches(5.5), Inches(1.2), border_color=C_EMERALD, line_width=2)
    tb_i1 = s2.shapes.add_textbox(Inches(1.2), Inches(3.18), Inches(5.1), Inches(1.0))
    tf_i1 = tb_i1.text_frame
    tf_i1.word_wrap = True
    tf_i1.margin_left = tf_i1.margin_top = tf_i1.margin_right = tf_i1.margin_bottom = 0
    p = tf_i1.paragraphs[0]
    p.text = "FastAPI Instance 1 (:8000)"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = C_NAVY
    p_i1_sub = tf_i1.add_paragraph()
    p_i1_sub.text = "• Xử lý thuật toán điều phối & gợi ý trạm sạc\n• Chạy mô phỏng giao thông thời gian thực"
    p_i1_sub.font.size = Pt(10.5)
    p_i1_sub.font.color.rgb = C_DARK

    # Instance 2
    add_card(s2, Inches(6.8), Inches(3.08), Inches(5.5), Inches(1.2), border_color=C_EMERALD, line_width=2)
    tb_i2 = s2.shapes.add_textbox(Inches(7.0), Inches(3.18), Inches(5.1), Inches(1.0))
    tf_i2 = tb_i2.text_frame
    tf_i2.word_wrap = True
    tf_i2.margin_left = tf_i2.margin_top = tf_i2.margin_right = tf_i2.margin_bottom = 0
    p = tf_i2.paragraphs[0]
    p.text = "FastAPI Instance 2 (:8002)"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = C_NAVY
    p_i2_sub = tf_i2.add_paragraph()
    p_i2_sub.text = "• Dự phòng nóng: Nginx failover 0 giây khi api_1 sập\n• Đồng bộ trạng thái tài xế qua Redis CAS"
    p_i2_sub.font.size = Pt(10.5)
    p_i2_sub.font.color.rgb = C_DARK

    # Tier 3: 3 Storage Boxes
    t3_items = [
        ("POSTGRESQL 16 + POSTGIS", "Port 5432 • Giao thức asyncpg",
         "Mạng đường bộ & Lịch sử Snapshot giao thông. Lưu trữ bền vững qua Docker Volume.", C_SLATE, Inches(0.8)),
        ("REDIS 7.4 IN-MEMORY", "Port 6379 • Giao thức RESP",
         "Bộ nhớ đệm L1 Cache & Trạng thái xe. Khóa lạc quan CAS đồng bộ tức thì.", C_RED, Inches(4.8)),
        ("GRAPHHOPPER 11.0", "Port 8989 • Giao thức HTTP REST",
         "Định tuyến đa chặng (Xe -> Trạm -> Đích) & Custom Model né kẹt xe.", C_AMBER, Inches(8.8)),
    ]

    for title, sub, desc, color, x_pos in t3_items:
        add_card(s2, x_pos, Inches(4.65), Inches(3.733), Inches(1.5), border_color=color, line_width=2)
        tb_box = s2.shapes.add_textbox(x_pos + Inches(0.2), Inches(4.78), Inches(3.333), Inches(1.25))
        tf_box = tb_box.text_frame
        tf_box.word_wrap = True
        tf_box.margin_left = tf_box.margin_top = tf_box.margin_right = tf_box.margin_bottom = 0
        
        p = tf_box.paragraphs[0]
        p.text = title
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = color
        
        p_sub = tf_box.add_paragraph()
        p_sub.text = sub
        p_sub.font.size = Pt(9)
        p_sub.font.bold = True
        p_sub.font.color.rgb = C_MUTED

        p_desc = tf_box.add_paragraph()
        p_desc.text = desc
        p_desc.font.size = Pt(10)
        p_desc.font.color.rgb = C_DARK

    # Bottom Banner (Punchy & Short)
    add_banner(s2, Inches(6.4),
               "ĐẶC TÍNH CHỊU LỖI: api_1 sập -> Nginx tự động chuyển 100% sang api_2 tức thì trong 0 giây (Zero Downtime).",
               RGBColor(238, 242, 255), C_BLUE, C_BLUE, icon_text="🛡️")

    s2.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 2 (45s):\n"
        "- Đây là kiến trúc 3 tầng với 6 container độc lập.\n"
        "- Tầng 1: Nginx Load Balancer tiếp nhận request qua cổng 3000.\n"
        "- Tầng 2: Cụm kép FastAPI không trạng thái. Nếu api_1 gặp sự cố, Nginx tự chuyển sang api_2 ngay lập tức trong 0 giây, không có điểm nghẽn đơn lẻ SPOF.\n"
        "- Tầng 3: PostGIS lưu mạng đường bộ, Redis làm cache L1, GraphHopper 11 định tuyến song song."
    )

    # ==========================================================
    # SLIDE 3: DATA FLOW SEQUENCE (ULTRA CLEAN)
    # ==========================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s3, C_BG_LIGHT)
    add_header(s3, "Sơ đồ Luồng Dữ liệu Thời gian thực (Realtime Pipeline)", "QUY TRÌNH XỬ LÝ")

    p_steps = [
        ("BƯỚC 1", "Map Matching", "PostGIS + GH 11",
         "Khớp GPS vào tim đường Hà Nội theo chu kỳ 10s hoặc di chuyển 50m.", C_BLUE, Inches(0.8)),
        ("BƯỚC 2", "Demand Physics", "19 Dòng xe VF",
         "Tính tiêu hao kWh/km thực tế. Đảm bảo pin dự phòng tới đích >= 15%.", C_EMERALD, Inches(3.2)),
        ("BƯỚC 3", "Candidate Filter", "Quét 30 Trạm",
         "Loại trạm hỏng & sai cổng sạc. Ô tô -> sạc nhanh, Xe máy -> đổi pin.", C_AMBER, Inches(5.6)),
        ("BƯỚC 4", "Multi-Leg Routing", "GraphHopper 8x",
         "Tính đồng thời 8 route (Xe -> Trạm -> Đích) & tự bẻ lái né đường kẹt.", C_NAVY, Inches(8.0)),
        ("BƯỚC 5", "Cost Ranking", "Tối ưu Chi phí",
         "Cộng dồn thời gian: Đi đường + Sạc + Xếp hàng + Kẹt xe -> Top 1.", C_RED, Inches(10.4)),
    ]

    for step_num, step_name, tech_tag, desc, color, x_pos in p_steps:
        add_card(s3, x_pos, Inches(1.45), Inches(2.133), Inches(4.6), border_color=color, line_width=2)
        tb = s3.shapes.add_textbox(x_pos + Inches(0.14), Inches(1.65), Inches(1.85), Inches(4.2))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p = tf.paragraphs[0]
        p.text = step_num
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = color

        p_name = tf.add_paragraph()
        p_name.text = step_name
        p_name.font.size = Pt(14)
        p_name.font.bold = True
        p_name.font.color.rgb = C_NAVY

        p_tech = tf.add_paragraph()
        p_tech.text = tech_tag
        p_tech.font.size = Pt(9.5)
        p_tech.font.bold = True
        p_tech.font.color.rgb = color

        tf.add_paragraph() # spacer

        p_desc = tf.add_paragraph()
        p_desc.text = desc
        p_desc.font.size = Pt(11)
        p_desc.font.color.rgb = C_DARK

    # Horizontal Connecting Arrows
    for i in range(4):
        arr_x = Inches(2.933 + i * 2.4)
        arr = s3.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arr_x, Inches(3.6), Inches(0.26), Inches(0.3))
        arr.fill.solid()
        arr.fill.fore_color.rgb = C_NAVY
        arr.line.fill.background()

    # Bottom Banner (Punchy & Short)
    add_banner(s3, Inches(6.35),
               "TỔNG THỜI GIAN XỬ LÝ: Toàn bộ 5 bước hoàn tất trong 186.4ms (P50), phản hồi tức thì cho tài xế khi đang lái xe.",
               RGBColor(236, 253, 245), C_EMERALD, C_EMERALD, icon_text="⏱️")

    s3.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 3 (40s):\n"
        "- Mỗi khi xe di chuyển, hệ thống chạy qua 5 bước tuần tự:\n"
        "- 1. Khớp tọa độ GPS vào tim đường.\n"
        "- 2. Kiểm tra năng lượng pin còn lại.\n"
        "- 3. Lọc nhanh các trạm không phù hợp.\n"
        "- 4. GraphHopper tính 8 tuyến đường song song ghé trạm.\n"
        "- 5. Xếp hạng chi phí để chọn ra trạm tốt nhất.\n"
        "- Toàn bộ quy trình chỉ mất 186 mili-giây."
    )

    # ==========================================================
    # SLIDE 4: CORE ALGORITHMS (ULTRA CLEAN)
    # ==========================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s4, C_BG_LIGHT)
    add_header(s4, "Mô hình Năng lượng Vật lý & Hàm Chi phí Toàn diện", "THUẬT TOÁN CỐT LÕI")

    # Left: Energy Physics
    add_card(s4, Inches(0.8), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_EMERALD, line_width=2)
    tb_l4 = s4.shapes.add_textbox(Inches(1.1), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_l4 = tb_l4.text_frame
    tf_l4.word_wrap = True
    tf_l4.margin_left = tf_l4.margin_top = tf_l4.margin_right = tf_l4.margin_bottom = 0

    p = tf_l4.paragraphs[0]
    p.text = "1. MÔ HÌNH VẬT LÝ PIN (19 DÒNG XE VF)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    items_l4 = [
        "Ô tô điện (VF e34, VF 8, VF 9): Điều hướng đến trạm sạc nhanh (18 - 30 phút).",
        "Xe máy điện (Klara, Feliz, Evo 200): Điều hướng đến tủ đổi pin siêu tốc (~6 phút).",
        "Công thức tiêu hao động: Tính mức kWh/km theo tải trọng và cấu hình từng dòng xe.",
        "Ngưỡng an toàn: Mức pin khi đến đích bắt buộc >= 15% để chống cạn pin dọc đường."
    ]
    for it in items_l4:
        p_it = tf_l4.add_paragraph()
        p_it.text = f"✔  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Right: Cost Formula
    add_card(s4, Inches(6.833), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_BLUE, line_width=2)
    tb_r4 = s4.shapes.add_textbox(Inches(7.133), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_r4 = tb_r4.text_frame
    tf_r4.word_wrap = True
    tf_r4.margin_left = tf_r4.margin_top = tf_r4.margin_right = tf_r4.margin_bottom = 0

    p = tf_r4.paragraphs[0]
    p.text = "2. HÀM CHI PHÍ TỐI ƯU (COST FUNCTION)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_BLUE

    # Formula Pill
    p_f = tf_r4.add_paragraph()
    p_f.text = "Cost = T_detour + T_service + T_queue + T_traffic"
    p_f.font.size = Pt(12)
    p_f.font.bold = True
    p_f.font.color.rgb = C_RED

    items_r4 = [
        "T_detour (Đi đường): Thời gian lái xe đi vòng ghé trạm rồi mới về điểm đến.",
        "T_service (Sạc/Đổi): Thời gian sạc pin (ô tô) hoặc đổi pin (xe máy).",
        "T_queue (Chờ đợi): Thời gian xếp hàng theo số lượng xe thực tế tại trạm.",
        "T_traffic (Kẹt xe): Độ trễ phát sinh do ùn tắc trên các tuyến đường dẫn vào trạm.",
    ]
    for it in items_r4:
        p_it = tf_r4.add_paragraph()
        p_it.text = f"★  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Bottom Banner (Punchy & Short)
    add_banner(s4, Inches(6.35),
               "NGUYÊN TẮC VÀNG: Trạm gần nhưng kẹt xe và chờ 45p sẽ bị LOẠI để chọn trạm thoáng hơn chỉ mất 15p!",
               RGBColor(254, 242, 242), C_RED, C_RED, icon_text="⚡")

    s4.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 4 (40s):\n"
        "- Trụ cột 1: Mô hình vật lý năng lượng 19 dòng xe VinFast, tự động phân định sạc ô tô hay đổi pin xe máy, và giữ ngưỡng an toàn pin trên 15%.\n"
        "- Trụ cột 2: Hàm Chi Phí = TỔNG THỜI GIAN (Đi đường + Sạc + Xếp hàng + Kẹt xe). Không chọn trạm gần nếu bị tắc đường hoặc chờ đợi quá lâu."
    )

    # ==========================================================
    # SLIDE 5: DYNAMIC AVOIDANCE (ULTRA CLEAN)
    # ==========================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s5, C_BG_LIGHT)
    add_header(s5, "Cơ chế Né Đường Tắc & Cân bằng Tải Trạm Realtime", "VẬN HÀNH THÔNG MINH")

    # Left: Traffic Detour
    add_card(s5, Inches(0.8), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_RED, line_width=2)
    tb_l5 = s5.shapes.add_textbox(Inches(1.1), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_l5 = tb_l5.text_frame
    tf_l5.word_wrap = True
    tf_l5.margin_left = tf_l5.margin_top = tf_l5.margin_right = tf_l5.margin_bottom = 0

    p = tf_l5.paragraphs[0]
    p.text = "1. TỰ ĐỘNG NÉ ĐƯỜNG TẮC (DETOUR)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_RED

    detour_items = [
        "Tuyến trực tiếp (3.6 km): Dính đường đỏ tắc nặng -> Thời gian thực tế: 32 phút.",
        "Tuyến vòng tránh (4.4 km): GraphHopper tự bẻ lái đi vòng -> Thời gian chỉ 20 phút!",
        "Nhanh hơn 12 phút nhờ Custom Model phạt tốc độ các đoạn đường tắc.",
        "Cập nhật liên tục: Tự động làm mới dữ liệu giao thông mỗi 30 giây."
    ]
    for it in detour_items:
        p_it = tf_l5.add_paragraph()
        p_it.text = f"•  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Right: Herd Avoidance
    add_card(s5, Inches(6.833), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_AMBER, line_width=2)
    tb_r5 = s5.shapes.add_textbox(Inches(7.133), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_r5 = tb_r5.text_frame
    tf_r5.word_wrap = True
    tf_r5.margin_left = tf_r5.margin_top = tf_r5.margin_right = tf_r5.margin_bottom = 0

    p = tf_r5.paragraphs[0]
    p.text = "2. CÂN BẰNG TẢI TRẠM SẠC"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_AMBER

    herd_items = [
        "Trạm A (Cách 1 km, đang kẹt): 3 xe đợi -> Hàng đợi +45 phút (Tổng: 60 phút).",
        "Trạm B (Cách 3 km, còn chỗ): Sạc được ngay -> Tổng thời gian chỉ 22 phút!",
        "Tự động tụt hạng: Chi phí hàng đợi tăng vọt làm trạm A bị hạ điểm.",
        "Triệt tiêu dồn toa: Tự động phân bổ đều xe sang các trạm lân cận còn trống."
    ]
    for it in herd_items:
        p_it = tf_r5.add_paragraph()
        p_it.text = f"•  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Bottom Banner (Punchy & Short)
    add_banner(s5, Inches(6.35),
               "HIỆU QUẢ VẬN HÀNH: Giảm 28% thời gian chờ đợi và khai thác đồng đều công suất 30 trạm sạc toàn Hà Nội.",
               RGBColor(255, 251, 235), C_AMBER, C_AMBER, icon_text="📊")

    s5.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 5 (40s):\n"
        "- Về kẹt xe: GraphHopper dùng Custom Model phạt đường đỏ, xe tự bẻ lái đi vòng để đến nơi nhanh hơn 12 phút.\n"
        "- Về trạm sạc: Khi 1 trạm đông xe, hàng đợi tăng làm trạm tụt hạng, các xe sau tự động được chia đều sang các trạm lân cận còn chỗ."
    )

    # ==========================================================
    # SLIDE 6: DRIVER COCKPIT & OPERATIONS (ULTRA CLEAN)
    # ==========================================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s6, C_BG_LIGHT)
    add_header(s6, "Buồng lái Tài xế & Giám sát Toàn Mạng lưới Realtime", "TRẢI NGHIỆM THỰC TẾ")

    # Left: Driver Cockpit
    add_card(s6, Inches(0.8), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_EMERALD, line_width=2)
    tb_l6 = s6.shapes.add_textbox(Inches(1.1), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_l6 = tb_l6.text_frame
    tf_l6.word_wrap = True
    tf_l6.margin_left = tf_l6.margin_top = tf_l6.margin_right = tf_l6.margin_bottom = 0

    p = tf_l6.paragraphs[0]
    p.text = "1. CHẾ ĐỘ BUỒNG LÁI TÀI XẾ"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    cockpit_items = [
        "Giao diện tối giản: Tập trung tuyệt đối cho người lái, không gây xao nhãng.",
        "Cảnh báo pin 3 cấp độ: 🟢 SAFE • 🟡 ADVISORY • 🔴 CRITICAL.",
        "Thanh trượt Pin tương tác: Kéo % pin -> Hệ thống đổi trạm sạc tức thì.",
        "Chỉ số rõ ràng: Quãng đường vòng (Detour km), Thời gian sạc, Tổng chi phí."
    ]
    for it in cockpit_items:
        p_it = tf_l6.add_paragraph()
        p_it.text = f"•  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Right: Operations Simulation
    add_card(s6, Inches(6.833), Inches(1.45), Inches(5.7), Inches(4.6), border_color=C_BLUE, line_width=2)
    tb_r6 = s6.shapes.add_textbox(Inches(7.133), Inches(1.7), Inches(5.1), Inches(4.1))
    tf_r6 = tb_r6.text_frame
    tf_r6.word_wrap = True
    tf_r6.margin_left = tf_r6.margin_top = tf_r6.margin_right = tf_r6.margin_bottom = 0

    p = tf_r6.paragraphs[0]
    p.text = "2. CHẾ ĐỘ GIÁM SÁT TOÀN MẠNG LƯỚI"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_BLUE

    sim_items = [
        "Bản đồ nhiệt: Trực tiếp theo dõi trạng thái 30 trạm sạc toàn Hà Nội.",
        "Mô phỏng GPS thực tế: Phát lại hành trình xe di chuyển trên tim đường.",
        "Minh bạch Cost Function: Xem chi tiết thời gian đi đường, sạc, chờ đợi.",
        "Đa nền tảng: Chạy mượt mà trên Web Desktop và điện thoại tài xế."
    ]
    for it in sim_items:
        p_it = tf_r6.add_paragraph()
        p_it.text = f"•  {it}"
        p_it.font.size = Pt(11.5)
        p_it.font.color.rgb = C_DARK

    # Bottom Banner (Punchy & Short)
    add_banner(s6, Inches(6.35),
               "KẾT LUẬN: GSMVSF là giải pháp điều phối sạc thông minh hoàn chỉnh, sẵn sàng phục vụ thực tế cho đội xe VinFast/GSM.",
               C_NAVY, C_EMERALD, RGBColor(255, 255, 255), icon_text="🏁")

    s6.notes_slide.notes_text_frame.text = (
        "LỜI THOẠI SLIDE 6 (30s):\n"
        "- Buồng lái tài xế hiển thị 3 mức cảnh báo Pin trực quan, cùng bản đồ giám sát toàn diện 30 trạm sạc.\n"
        "- Hệ thống đã sẵn sàng đưa vào vận hành thực tế cho quy mô hàng ngàn xe điện GSM VinFast. Xin cảm ơn quý vị!"
    )

    output_path = "docs/GSMVSF_Presentation_Final.pptx"
    prs.save(output_path)
    print(f"Clean presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_presentation()
