import json
import os

presets = {
    # ---------------- TITLE CARDS (10 presets) ----------------
    "黄金强光贴纸 (El Resplandor Dorado)": {
        "mode": "text", "font_family": "Montserrat Black", "weight": 900,
        "color": "#FFFFFF", "hl_color": "#FFC300",
        "stroke": True, "stroke_color": "#0A1428", "stroke_width": 5,
        "shadow": True, "shadow_color": "#0A1428", "shadow_x": 5, "shadow_y": 5, "shadow_blur": 0, "shadow_alpha": 100,
        "bg": False
    },
    "霓虹青空发光体 (Cielo Neón)": {
        "mode": "text", "font_family": "Bebas Neue", "uppercase": True,
        "color": "#F8F9FA", "hl_color": "#00F0FF",
        "stroke": True, "stroke_color": "#2B2D42", "stroke_width": 3,
        "shadow": True, "shadow_color": "#00F0FF", "shadow_x": 0, "shadow_y": 0, "shadow_blur": 15, "shadow_alpha": 80,
        "bg": False
    },
    "街头冲击 (Impacto Urbano)": {
        "mode": "text", "font_family": "Anton",
        "color": "#1A1D20", "hl_color": "#D90429",
        "stroke": True, "stroke_color": "#FFFFFF", "stroke_width": 6,
        "shadow": False,
        "bg": False
    },
    "纯净极简 (Minimalismo Puro)": {
        "mode": "text", "font_family": "Poppins SemiBold",
        "color": "#FFFFFF", "hl_color": "#A3E4D7",
        "stroke": False,
        "shadow": True, "shadow_color": "#111827", "shadow_x": 0, "shadow_y": 4, "shadow_blur": 12, "shadow_alpha": 65,
        "bg": False
    },
    "复古报纸 (Titular de Prensa)": {
        "mode": "text", "font_family": "Lora Bold",
        "color": "#4A2511", "hl_color": "#4A2511",
        "stroke": True, "stroke_color": "#F9F3E3", "stroke_width": 4,
        "shadow": False,
        "bg": False
    },
    "警戒红幕 (Alerta Roja)": {
        "mode": "text", "font_family": "Merriweather Bold",
        "color": "#FFFFFF", "hl_color": "#FFF3B0",
        "stroke": False,
        "shadow": True, "shadow_color": "#590D0D", "shadow_x": 2, "shadow_y": 2, "shadow_blur": 4, "shadow_alpha": 60,
        "bg": True, "bg_shape": "notch", "bg_color": "#E63946", "bg_alpha": 242
    },
    "深海权威 (Autoridad Profunda)": {
        "mode": "text", "font_family": "Roboto Black",
        "color": "#FFFFFF", "hl_color": "#FF6F61",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "banner", "bg_color": "#1D3557", "bg_alpha": 255
    },
    "复古羊皮纸 (Pergamino Clásico)": {
        "mode": "text", "font_family": "Playfair Display Bold",
        "color": "#1A3626", "hl_color": "#9A2A2A",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 24, "bg_color": "#F4ECD8", "bg_alpha": 255,
        "bg_shadow": True, "bg_shadow_color": "#6D4C41", "bg_shadow_x": 0, "bg_shadow_y": 8, "bg_shadow_blur": 16, "bg_shadow_alpha": 20
    },
    "活力柑橘 (Cítrico Vibrante)": {
        "mode": "text", "font_family": "Montserrat Extrabold",
        "color": "#001D3D", "hl_color": "#FFFFFF",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "pill", "bg_color": "#FF9F1C", "bg_alpha": 255
    },
    "极简白盒 (Caja Blanca Minimalista)": {
        "mode": "text", "font_family": "Helvetica Neue Bold",
        "color": "#2C3E50", "hl_color": "#990000",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 32, "bg_color": "#FFFFFF", "bg_alpha": 230,
        "bg_shadow": True, "bg_shadow_color": "#000000", "bg_shadow_x": 0, "bg_shadow_y": 4, "bg_shadow_blur": 10, "bg_shadow_alpha": 15
    },
    "暗流暗盒 (Caja Oscura)": {
        "mode": "text", "font_family": "Montserrat Bold",
        "color": "#FFFFFF", "hl_color": "#2ECC71",
        "stroke": False,
        "shadow": True, "shadow_color": "#111111", "shadow_x": 0, "shadow_y": 2, "shadow_blur": 4, "shadow_alpha": 50,
        "bg": True, "bg_shape": "rounded", "bg_radius": 8, "bg_color": "#1A1E24", "bg_alpha": 140
    },
    "紫水晶滤镜 (Filtro Amatista)": {
        "mode": "text", "font_family": "Poppins SemiBold",
        "color": "#FFFFFF", "hl_color": "#FADBD8",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "gradient", "bg_color": "#4A235A", "bg_alpha": 230
    },
    "毛玻璃翠绿 (Verde Esmerilado)": {
        "mode": "text", "font_family": "Roboto Black",
        "color": "#FFFFFF", "hl_color": "#F4D03F",
        "stroke": True, "stroke_color": "#0B5345", "stroke_width": 2,
        "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 20, "bg_color": "#145A32", "bg_alpha": 102
    },
    "赛博深灰 (Gris Cibernético)": {
        "mode": "text", "font_family": "Teko SemiBold",
        "color": "#33FFFF", "hl_color": "#FF00FF",
        "stroke": False,
        "shadow": True, "shadow_color": "#000000", "shadow_x": 2, "shadow_y": 2, "shadow_blur": 0, "shadow_alpha": 100,
        "bg": True, "bg_shape": "rect", "bg_color": "#2F4F4F", "bg_alpha": 178
    },
    "柔和米黄带 (Cinta Beige Suave)": {
        "mode": "text", "font_family": "Nunito Bold",
        "color": "#3E2723", "hl_color": "#D84315",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "torn", "bg_color": "#FFF8E1", "bg_alpha": 216
    },

    # ---------------- WHATSAPP CTA CARDS (7 presets) ----------------
    "官方生态分层 (Ecosistema WhatsApp)": {
        "mode": "text", "time": 30.0, "font_family": "Roboto Black",
        "color": "#128C7E", "hl_color": "#128C7E",
        "lead_text": "Escríbeme para más info", "lead_color": "#FFFFFF", "lead_scale": 60, "lead_font": "Poppins",
        "split": "horizontal", "split_color2": "#DCF8C6", "split_alpha2": 255, "icon": "whatsapp",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 16, "bg_color": "#075E54", "bg_alpha": 255,
        "bg_border_w": 2, "bg_border_color": "#FFFFFF"
    },
    "专业深海拼图 (Azul Profesional)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#850000", "hl_color": "#850000",
        "lead_text": "ÚNETE AL GRUPO GRATIS", "lead_color": "#FFFFFF", "lead_scale": 60,
        "sub_text": "Estudio Bíblico Nocturno", "sub_color": "#3A3B45", "sub_scale": 40,
        "split": "horizontal", "split_color2": "#FFFFFF", "split_alpha2": 255, "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 20, "bg_color": "#0A2342", "bg_alpha": 255,
        "bg_shadow": True, "bg_shadow_color": "#000000", "bg_shadow_x": 0, "bg_shadow_y": 8, "bg_shadow_blur": 16, "bg_shadow_alpha": 30
    },
    "极简黑白交界 (Frontera Monocromática)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#1C1C1E", "hl_color": "#1C1C1E",
        "lead_text": "Contacto directo:", "lead_color": "#1C1C1E", "lead_scale": 50, "lead_inline": True,
        "split": "vertical", "split_color2": "#FFFFFF", "split_alpha2": 242, "icon": "whatsapp_arrow",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rect", "bg_color": "#1C1C1E", "bg_alpha": 242
    },
    "牧师呼召紫带 (Llamado Pastoral)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#4A235A", "hl_color": "#4A235A",
        "lead_text": "Hablemos de fe", "lead_color": "#FFFFFF", "lead_scale": 60,
        "split": "horizontal", "split_color2": "#FFFFFF", "split_alpha2": 255, "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 16, "bg_color": "#4A235A", "bg_alpha": 255
    },
    "黄金金融分割 (División Financiera)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#2C3E50", "hl_color": "#2C3E50",
        "lead_text": "Asesoría Gratuita", "lead_color": "#F1C40F", "lead_scale": 60,
        "split": "horizontal", "split_color2": "#F2F3F4", "split_alpha2": 255, "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rect", "bg_color": "#2C3E50", "bg_alpha": 255
    },
    "磨砂白玉胶囊 (Vidrio Esmerilado)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#900C3F", "hl_color": "#900C3F",
        "lead_text": "Contáctame", "lead_color": "#4A4036", "lead_scale": 50, "lead_inline": True,
        "split": "none", "icon": "whatsapp",
        "stroke": True, "stroke_color": "#FFFFFF", "stroke_width": 1, "shadow": False,
        "bg": True, "bg_shape": "pill", "bg_color": "#FFFFFF", "bg_alpha": 191
    },
    "暗夜流金 (Noche Dorada)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#FFD166", "hl_color": "#FFD166",
        "lead_text": "Consulta Exclusiva", "lead_color": "#E8D8A6", "lead_scale": 50,
        "sub_text": "Disponible 24/7", "sub_color": "#FFFFFF", "sub_scale": 40,
        "split": "none", "icon": "none",
        "stroke": False, "shadow": True, "shadow_color": "#FFD166", "shadow_x": 0, "shadow_y": 0, "shadow_blur": 10, "shadow_alpha": 100,
        "bg": True, "bg_shape": "rounded", "bg_radius": 24, "bg_color": "#151B29", "bg_alpha": 230,
        "bg_border_w": 1, "bg_border_color": "#D4AF37"
    },
    "翠绿信任盾牌 (Escudo Verde)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#FFFFFF", "hl_color": "#FFFFFF",
        "lead_text": "WhatsApp Directo", "lead_color": "#FFFFFF", "lead_scale": 50, "lead_inline": True,
        "split": "none", "icon": "none",
        "stroke": False, "shadow": True, "shadow_color": "#075E54", "shadow_x": 0, "shadow_y": 4, "shadow_blur": 0, "shadow_alpha": 100,
        "bg": True, "bg_shape": "rounded", "bg_radius": 12, "bg_color": "#25D366", "bg_alpha": 230
    },
    "极简半透黑盒 (Caja Translúcida)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#FFFFFF", "hl_color": "#FFFFFF",
        "underline": True, "underline_color": "#25D366", "underline_w": 2,
        "split": "none", "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 16, "bg_color": "#0F0F0F", "bg_alpha": 102
    },
    "纯白云朵悬浮 (Nube Blanca)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#128C7E", "hl_color": "#128C7E",
        "lead_text": "Escríbeme", "lead_color": "#7F8C8D", "lead_scale": 50, "lead_inline": True,
        "split": "none", "icon": "whatsapp",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "pill", "bg_color": "#FFFFFF", "bg_alpha": 255,
        "bg_shadow": True, "bg_shadow_color": "#000000", "bg_shadow_x": 0, "bg_shadow_y": 10, "bg_shadow_blur": 30, "bg_shadow_alpha": 40
    },
    "红色下划线警告 (Subrayado Urgente)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 900, "size": 90,
        "color": "#BA1826", "hl_color": "#BA1826",
        "underline": True, "underline_color": "#BA1826", "underline_w": 6,
        "split": "none", "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 8, "bg_color": "#FDFDFD", "bg_alpha": 255,
        "bg_bottom_w": 6, "bg_bottom_color": "#D90429"
    },
    "警戒黄黑封条 (Cinta de Precaución)": {
        "mode": "text", "time": 30.0, "font_family": "Impact",
        "color": "#111111", "hl_color": "#111111",
        "split": "none", "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rect", "bg_color": "#FFC107", "bg_alpha": 255
    },
    "荧光焦点框 (Marco de Enfoque Neón)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#FFFFFF", "hl_color": "#FFFFFF",
        "split": "none", "icon": "none",
        "stroke": False, "shadow": True, "shadow_color": "#39FF14", "shadow_x": 0, "shadow_y": 0, "shadow_blur": 15, "shadow_alpha": 100,
        "bg": True, "bg_shape": "outline", "bg_color": "#000000", "bg_alpha": 0,
        "bg_border_w": 4, "bg_border_color": "#39FF14"
    },
    "优惠警报红底 (Alerta de Oferta)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 700,
        "color": "#FFFFFF", "hl_color": "#FFFFFF",
        "lead_text": "Solo hoy", "lead_color": "#F1C40F", "lead_scale": 50,
        "split": "none", "icon": "none",
        "stroke": False, "shadow": False,
        "bg": True, "bg_shape": "rounded", "bg_radius": 16, "bg_color": "#E74C3C", "bg_alpha": 255
    },
    "科技蓝图指示牌 (Plano Tecnológico)": {
        "mode": "text", "time": 30.0, "font_family": "Microsoft YaHei", "weight": 300,
        "color": "#00FFFF", "hl_color": "#00FFFF",
        "split": "none", "icon": "none",
        "stroke": False, "shadow": True, "shadow_color": "#00FFFF", "shadow_x": 0, "shadow_y": 0, "shadow_blur": 10, "shadow_alpha": 80,
        "bg": True, "bg_shape": "notch", "bg_color": "#0B192C", "bg_alpha": 216
    }
}

path = r'D:\Antigravity\VideoTools\duet_data\card_presets.json'
os.makedirs(os.path.dirname(path), exist_ok=True)
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        existing = json.load(f)
else:
    existing = {}

# Merge presets (update existing)
for k, v in presets.items():
    existing[k] = v

with open(path, 'w', encoding='utf-8') as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)

print(f"Injected {len(presets)} presets into {path}")
