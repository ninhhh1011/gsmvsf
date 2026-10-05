"""
Generate GSMVSF Ultra-Minimal Technical Architecture Presentation (.pptx).
STRICT RULES:
- Maximum 3 to 6 words per box/card!
- Absolutely NO long sentences or paragraphs!
- Large fonts (18pt - 36pt), massive whitespace, clean visual diagrams.
- 5 slides total.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN

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

    def add_header(slide, title_text, category_text="KIẾN TRÚC HỆ THỐNG"):
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.3))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        tf_cat.margin_left = tf_cat.margin_top = tf_cat.margin_right = tf_cat.margin_bottom = 0
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = C_EMERALD

        t_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.6))
        tf_t = t_box.text_frame
        tf_t.word_wrap = True
        tf_t.margin_left = tf_t.margin_top = tf_t.margin_right = tf_t.margin_bottom = 0
        p_t = tf_t.paragraphs[0]
        p_t.text = title_text
        p_t.font.size = Pt(26)
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

    def add_banner(slide, y, text, bg_color, border_color, text_color):
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
        p.text = text
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = text_color
        return banner

    # ==========================================================
    # SLIDE 1: COVER
    # ==========================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1, C_NAVY)

    # Pill
    add_card(s1, Inches(0.8), Inches(1.5), Inches(3.2), Inches(0.45),
             bg_color=RGBColor(30, 41, 59), border_color=C_EMERALD)
    tb_pill = s1.shapes.add_textbox(Inches(0.9), Inches(1.55), Inches(3.0), Inches(0.35))
    tf_pill = tb_pill.text_frame
    tf_pill.margin_left = tf_pill.margin_top = tf_pill.margin_right = tf_pill.margin_bottom = 0
    p = tf_pill.paragraphs[0]
    p.text = "GSMVSF ARCHITECTURE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    # Title
    t_box1 = s1.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(1.8))
    tf1 = t_box1.text_frame
    tf1.word_wrap = True
    tf1.margin_left = tf1.margin_top = tf1.margin_right = tf1.margin_bottom = 0
    p1 = tf1.paragraphs[0]
    p1.text = "Realtime EV Recommendation\n& Dynamic Routing Engine"
    p1.font.size = Pt(40)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(255, 255, 255)

    desc_box1 = s1.shapes.add_textbox(Inches(0.8), Inches(4.3), Inches(11.0), Inches(0.5))
    tf_desc1 = desc_box1.text_frame
    tf_desc1.word_wrap = True
    tf_desc1.margin_left = tf_desc1.margin_top = tf_desc1.margin_right = tf_desc1.margin_bottom = 0
    p_desc1 = tf_desc1.paragraphs[0]
    p_desc1.text = "Kiến trúc kỹ thuật & Luồng xử lý dữ liệu thời gian thực"
    p_desc1.font.size = Pt(18)
    p_desc1.font.color.rgb = RGBColor(203, 213, 225)

    # 4 Quick Badges
    badges = [
        ("Nginx", "Port 3000 • Failover 0s", C_BLUE),
        ("FastAPI Dual", "Ports 8000 & 8002", C_EMERALD),
        ("GraphHopper 11", "Port 8989 • Routing 8x", C_AMBER),
        ("PostGIS & Redis", "Ports 5432 & 6379", C_RED),
    ]
    for i, (b_title, b_sub, b_color) in enumerate(badges):
        bx = Inches(0.8 + i * 2.95)
        by = Inches(5.4)
        add_card(s1, bx, by, Inches(2.8), Inches(1.2), bg_color=RGBColor(30, 41, 59), border_color=RGBColor(51, 65, 85))
        tb = s1.shapes.add_textbox(bx + Inches(0.2), by + Inches(0.25), Inches(2.4), Inches(0.7))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p_bt = tf.paragraphs[0]
        p_bt.text = b_title
        p_bt.font.size = Pt(16)
        p_bt.font.bold = True
        p_bt.font.color.rgb = b_color

        p_bs = tf.add_paragraph()
        p_bs.text = b_sub
        p_bs.font.size = Pt(11)
        p_bs.font.color.rgb = RGBColor(148, 163, 184)

    s1.notes_slide.notes_text_frame.text = "Slide 1: Tổng quan Tech Stack hệ thống GSMVSF."

    # ==========================================================
    # SLIDE 2: 3-TIER ARCHITECTURE
    # ==========================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s2, C_BG_LIGHT)
    add_header(s2, "Kiến trúc Hệ thống 3 Tầng & Giao thức", "HẠ TẦNG KỸ THUẬT")

    # Tier 1
    add_card(s2, Inches(4.3), Inches(1.4), Inches(4.733), Inches(0.85), border_color=C_BLUE, line_width=2)
    tb = s2.shapes.add_textbox(Inches(4.5), Inches(1.5), Inches(4.333), Inches(0.65))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = "TIER 1: NGINX PROXY (:3000)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_BLUE
    p_sub = tf.add_paragraph()
    p_sub.text = "Cân bằng tải least_conn • Failover tức thì"
    p_sub.font.size = Pt(11)
    p_sub.font.color.rgb = C_DARK

    # Arrow Down
    arr_t1 = s2.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(6.5), Inches(2.32), Inches(0.35), Inches(0.3))
    arr_t1.fill.solid()
    arr_t1.fill.fore_color.rgb = C_BLUE
    arr_t1.line.fill.background()

    # Tier 2 Cluster
    add_card(s2, Inches(0.8), Inches(2.7), Inches(11.733), Inches(1.55),
             bg_color=RGBColor(241, 245, 249), border_color=C_EMERALD, line_width=1.5)
    
    tb_t2_lbl = s2.shapes.add_textbox(Inches(1.0), Inches(2.8), Inches(6.0), Inches(0.25))
    tf_t2_lbl = tb_t2_lbl.text_frame
    tf_t2_lbl.margin_left = tf_t2_lbl.margin_top = tf_t2_lbl.margin_right = tf_t2_lbl.margin_bottom = 0
    p = tf_t2_lbl.paragraphs[0]
    p.text = "TIER 2: CỤM FASTAPI STATELESS (DUAL REPLICAS)"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    # Instance 1
    add_card(s2, Inches(1.0), Inches(3.1), Inches(5.5), Inches(0.95), border_color=C_EMERALD, line_width=2)
    tb = s2.shapes.add_textbox(Inches(1.2), Inches(3.2), Inches(5.1), Inches(0.75))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = "ev_api_1 (:8000)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_NAVY
    p_sub = tf.add_paragraph()
    p_sub.text = "In-Process Engine • Simulator giao thông (30s)"
    p_sub.font.size = Pt(11)
    p_sub.font.color.rgb = C_DARK

    # Instance 2
    add_card(s2, Inches(6.8), Inches(3.1), Inches(5.5), Inches(0.95), border_color=C_EMERALD, line_width=2)
    tb = s2.shapes.add_textbox(Inches(7.0), Inches(3.2), Inches(5.1), Inches(0.75))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = "ev_api_2 (:8002)"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_NAVY
    p_sub = tf.add_paragraph()
    p_sub.text = "In-Process Engine • Standby Failover 0s"
    p_sub.font.size = Pt(11)
    p_sub.font.color.rgb = C_DARK

    # Tier 3 (3 Boxes)
    t3 = [
        ("POSTGRESQL 16", "Port 5432 • asyncpg", "Schema public & realtime", C_SLATE, Inches(0.8)),
        ("REDIS 7.4", "Port 6379 • RESP", "L1 Cache & Khóa CAS", C_RED, Inches(4.8)),
        ("GRAPHHOPPER 11", "Port 8989 • HTTP REST", "Routing 8x & Custom Model", C_AMBER, Inches(8.8)),
    ]
    for title, port, role, color, x_pos in t3:
        add_card(s2, x_pos, Inches(4.5), Inches(3.733), Inches(1.5), border_color=color, line_width=2)
        tb = s2.shapes.add_textbox(x_pos + Inches(0.2), Inches(4.7), Inches(3.333), Inches(1.1))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = color
        p_p = tf.add_paragraph()
        p_p.text = port
        p_p.font.size = Pt(10)
        p_p.font.color.rgb = C_MUTED
        p_r = tf.add_paragraph()
        p_r.text = role
        p_r.font.size = Pt(11.5)
        p_r.font.bold = True
        p_r.font.color.rgb = C_DARK

    add_banner(s2, Inches(6.35),
               "⚡ Chịu lỗi HA: api_1 sập -> Nginx tự chuyển sang api_2 tức thì (0s Downtime).",
               RGBColor(238, 242, 255), C_BLUE, C_BLUE)

    s2.notes_slide.notes_text_frame.text = "Slide 2: Kiến trúc 3 tầng, phân tách Nginx, cụm FastAPI kép và storage PostGIS/Redis/GraphHopper."

    # ==========================================================
    # SLIDE 3: REALTIME PIPELINE
    # ==========================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s3, C_BG_LIGHT)
    add_header(s3, "Luồng Xử lý Dữ liệu Realtime (5 Bước)", "LUỒNG THỰC THI")

    steps = [
        ("1. MAP MATCH", "GPS -> Tim đường", "PostGIS (10s / 50m)", C_BLUE, Inches(0.8)),
        ("2. DEMAND", "19 Dòng xe VF", "Pin tới đích >= 15%", C_EMERALD, Inches(3.2)),
        ("3. LỌC TRẠM", "Quét 30 Trạm", "Chuẩn cổng & pin đổi", C_AMBER, Inches(5.6)),
        ("4. ROUTING 8X", "GraphHopper 11", "Xe -> Trạm -> Đích", C_SLATE, Inches(8.0)),
        ("5. RANKING", "Tối ưu Thời gian", "Top-1 Khuyến nghị", C_RED, Inches(10.4)),
    ]

    for title, role, sub, color, x_pos in steps:
        add_card(s3, x_pos, Inches(1.6), Inches(2.133), Inches(4.3), border_color=color, line_width=2)
        tb = s3.shapes.add_textbox(x_pos + Inches(0.15), Inches(1.9), Inches(1.833), Inches(3.8))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = color

        tf.add_paragraph() # spacer

        p_r = tf.add_paragraph()
        p_r.text = role
        p_r.font.size = Pt(13.5)
        p_r.font.bold = True
        p_r.font.color.rgb = C_NAVY

        p_s = tf.add_paragraph()
        p_s.text = sub
        p_s.font.size = Pt(11)
        p_s.font.color.rgb = C_MUTED

    for i in range(4):
        arr_x = Inches(2.933 + i * 2.4)
        arr = s3.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arr_x, Inches(3.6), Inches(0.26), Inches(0.3))
        arr.fill.solid()
        arr.fill.fore_color.rgb = C_NAVY
        arr.line.fill.background()

    add_banner(s3, Inches(6.35),
               "⏱️ Tổng độ trễ pipeline: 186.4ms (P50) cho toàn bộ 5 bước.",
               RGBColor(236, 253, 245), C_EMERALD, C_EMERALD)

    s3.notes_slide.notes_text_frame.text = "Slide 3: Pipeline 5 bước từ lúc nhận GPS đến khi trả về Top-1 station."

    # ==========================================================
    # SLIDE 4: DYNAMIC CONGESTION AVOIDANCE
    # ==========================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s4, C_BG_LIGHT)
    add_header(s4, "Né Đường Tắc (GraphHopper Custom Model)", "ĐỊNH TUYẾN THÔNG MINH")

    # Left: Tuyến Thẳng
    add_card(s4, Inches(0.8), Inches(1.5), Inches(5.7), Inches(4.5), border_color=C_RED, line_width=2)
    tb = s4.shapes.add_textbox(Inches(1.2), Inches(1.9), Inches(4.9), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = "TUYẾN TRỰC TIẾP"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = C_RED

    tf.add_paragraph()
    p1 = tf.add_paragraph()
    p1.text = "• Quãng đường: 3.6 km"
    p1.font.size = Pt(14)
    p1.font.bold = True
    p1.font.color.rgb = C_NAVY

    p2 = tf.add_paragraph()
    p2.text = "• Trạng thái: Dính tắc đường Đê La Thành"
    p2.font.size = Pt(13)
    p2.font.color.rgb = C_DARK

    p3 = tf.add_paragraph()
    p3.text = "• Thời gian: 32 phút"
    p3.font.size = Pt(15)
    p3.font.bold = True
    p3.font.color.rgb = C_RED

    # Right: Tuyến Vòng
    add_card(s4, Inches(6.833), Inches(1.5), Inches(5.7), Inches(4.5), border_color=C_EMERALD, line_width=2)
    tb = s4.shapes.add_textbox(Inches(7.233), Inches(1.9), Inches(4.9), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = "TUYẾN VÒNG TRÁNH (CUSTOM MODEL)"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = C_EMERALD

    tf.add_paragraph()
    p1 = tf.add_paragraph()
    p1.text = "• Quãng đường: 4.4 km (+800m)"
    p1.font.size = Pt(14)
    p1.font.bold = True
    p1.font.color.rgb = C_NAVY

    p2 = tf.add_paragraph()
    p2.text = "• Trạng thái: Tự bẻ lái sang đường thoáng"
    p2.font.size = Pt(13)
    p2.font.color.rgb = C_DARK

    p3 = tf.add_paragraph()
    p3.text = "• Thời gian: 20 phút (Nhanh hơn 12 phút!)"
    p3.font.size = Pt(15)
    p3.font.bold = True
    p3.font.color.rgb = C_EMERALD

    add_banner(s4, Inches(6.35),
               "🚦 Cơ chế: GraphHopper phạt trọng số đường đỏ tại runtime -> Tự bẻ lái né tắc.",
               RGBColor(255, 251, 235), C_AMBER, C_AMBER)

    s4.notes_slide.notes_text_frame.text = "Slide 4: GraphHopper Custom Model né kẹt xe, đi xa hơn 800m nhưng nhanh hơn 12 phút."

    # ==========================================================
    # SLIDE 5: DISTRIBUTED STATE & HA FAILOVER
    # ==========================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s5, C_BG_LIGHT)
    add_header(s5, "Quản lý Trạng thái & Chịu Lỗi HA", "ĐỘ TIN CẬY HỆ THỐNG")

    t_box5 = [
        ("NGINX FAILOVER (0s)", "api_1 sập -> Chuyển sang api_2 tức thì", "proxy_next_upstream error timeout", C_BLUE, Inches(0.8)),
        ("REDIS KHÓA CAS", "Chống xung đột đa replica", "expected_version & generation_id", C_RED, Inches(4.8)),
        ("POSTGRES SCHEMAS", "Tách dữ liệu tĩnh và biến động", "public (OSM) vs realtime (Snapshots)", C_SLATE, Inches(8.8)),
    ]

    for title, main_t, sub_t, color, x_pos in t_box5:
        add_card(s5, x_pos, Inches(1.6), Inches(3.733), Inches(4.3), border_color=color, line_width=2)
        tb = s5.shapes.add_textbox(x_pos + Inches(0.25), Inches(2.0), Inches(3.233), Inches(3.6))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(15)
        p.font.bold = True
        p.font.color.rgb = color

        tf.add_paragraph()
        p_m = tf.add_paragraph()
        p_m.text = main_t
        p_m.font.size = Pt(14)
        p_m.font.bold = True
        p_m.font.color.rgb = C_NAVY

        p_s = tf.add_paragraph()
        p_s.text = sub_t
        p_s.font.size = Pt(11)
        p_s.font.color.rgb = C_MUTED

    add_banner(s5, Inches(6.35),
               "🛡️ Zero Single Point of Failure: Hệ thống không có điểm chết đơn lẻ.",
               RGBColor(238, 242, 255), C_BLUE, C_BLUE)

    s5.notes_slide.notes_text_frame.text = "Slide 5: Cơ chế chịu lỗi HA, khóa CAS trên Redis và phân vùng Schema Postgres."

    # Save
    out1 = "docs/GSMVSF_Tech_Architecture.pptx"
    out2 = "docs/GSMVSF_Presentation_Final.pptx"
    prs.save(out1)
    print(f"Saved: {out1}")
    try:
        prs.save(out2)
        print(f"Saved: {out2}")
    except Exception as e:
        print(f"Could not overwrite {out2}: {e}")

if __name__ == "__main__":
    create_presentation()
