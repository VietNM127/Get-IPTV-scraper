#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV Stream Scraper for bunchatv1.net
Output format: monplayer JSON (groups → channels → sources → stream_links)
"""

import requests
import json
import re
import hashlib
import os
import io
from datetime import datetime
from bs4 import BeautifulSoup
import time
from PIL import Image, ImageDraw, ImageFont

# ── Cấu hình ─────────────────────────────────────────────────────────────────
OUTPUT_FILE   = "streams.json"
SOURCE_NAME   = "Bánh Bao TV"          # tên nguồn hiển thị trong monplayer
PLAYLIST_ID   = "banhbao"              # id playlist trong monplayer
PLAYLIST_NAME = "Bánh Bao TV"

# ⚠️  QUAN TRỌNG: Điền URL GitHub Pages của bạn vào đây sau khi deploy!
# Monplayer dùng URL này để tự động refresh playlist (lấy link m3u8 mới).
# Nếu để trống, stream sẽ bị lỗi sau khi link hết hạn (~vài tiếng).
# Ví dụ: "https://YOUR_USERNAME.github.io/Get-IPTV/streams.json"
PLAYLIST_URL  = "https://raw.githubusercontent.com/VietNM127/Get-IPTV-scraper/main/streams.json"

LOGO_URL      = "https://scontent.fhan5-10.fna.fbcdn.net/v/t39.30808-6/580821357_1151084077132266_6103102651618107715_n.jpg?_nc_cat=101&ccb=1-7&_nc_sid=dd6889&_nc_eui2=AeHUhbo5R5NFXmgOsxANQC8gQnG2fAweQLJCcbZ8DB5AspcyzbUEI3Fnt2SR9nPUCJIxSOvjCFwBmURc4-UcM0m7&_nc_ohc=NfNQg-r-20MQ7kNvwFQH_Hs&_nc_oc=Adlx7DDa7esB8i9ImfAcuFbsTHFW6crNh8CbWHDzXj4R7GOrWtSFEJCjwlWjihJRg9OdDKehAdO6jiKBcpo7NaXa&_nc_zt=23&_nc_ht=scontent.fhan5-10.fna&_nc_gid=hYKh8Di3yDWxq5OwpW28nQ&_nc_ss=8&oh=00_AfwW4Se45di6s_O1g06AmqYWNCKGt41h8Gv5LClCaWpo8g&oe=69B4B51E"
# ─────────────────────────────────────────────────────────────────────────────

SPORT_EMOJI = {
    "billiard": "🎱", "bida": "🎱", "pba": "🎱", "lpba": "🎱",
    "basket": "🏀", "nba": "🏀", "bóng rổ": "🏀",
    "tennis": "🎾", "atp": "🎾", "wta": "🎾",
    "cầu lông": "🏸", "badminton": "🏸",
    "bóng chuyền": "🏐", "volleyball": "🏐",
    "võ thuật": "🥊", "mma": "🥊", "boxing": "🥊", "one ": "🥊",
}

def _sport_emoji(league: str) -> str:
    low = league.lower()
    for kw, emoji in SPORT_EMOJI.items():
        if kw in low:
            return emoji
    return "⚽"

# Thứ tự ưu tiên hiển thị nhóm môn thể thao
SPORT_ORDER = [
    "⚽ Bóng Đá", "🏀 Bóng Rổ", "🎾 Tennis", "🏸 Cầu Lông",
    "🏐 Bóng Chuyền", "🎱 Billiard", "🥊 Võ Thuật", "🏓 Bóng Bàn",
]

def _sport_category(league: str, title: str = "") -> tuple:
    """Trả về (emoji, tên_môn) dựa vào tên giải đấu và tên đội/vận động viên."""
    combined = (league + " " + title).lower()

    if any(k in combined for k in ["billiard", "bida", "pba", "lpba"]):
        return "🎱", "Billiard"

    # Bóng rổ: tên giải + tên câu lạc bộ NBA
    NBA_KW = ["nba", "basket", "bóng rổ",
              "jazz", "warriors", "lakers", "celtics", "knicks", "clippers",
              "bulls", "nets", "heat", "spurs", "bucks", "suns", "nuggets",
              "cavaliers", "sixers", "raptors", "magic", "pistons", "pacers",
              "hornets", "hawks", "wizards", "kings", "thunder", "blazers",
              "timberwolves", "pelicans", "rockets", "grizzlies", "mavericks"]
    if any(k in combined for k in NBA_KW):
        return "🏀", "Bóng Rổ"

    # Tennis: tên giải hoặc dạng "Họ T. vs Họ T." (viết tắt) hoặc tên tay vợt nổi tiếng
    TENNIS_KW = ["tennis", "atp", "wta", "indian wells", "roland garros",
                 "wimbledon", "us open", "australian open", "davis cup",
                 "medvedev", "djokovic", "nadal", "federer", "alcaraz", 
                 "sinner", "rybakina", "sabalenka"]
    if any(k in combined for k in TENNIS_KW):
        return "🎾", "Tennis"
    # Detect từ dạng tên viết tắt: "Họ X. vs Họ Y." → có khả năng là tennis/cầu lông
    if re.match(r'^[a-z]+ [a-z]\. vs [a-z]+ [a-z]\.', title.lower()):
        return "🎾", "Tennis"

    if any(k in combined for k in ["cầu lông", "badminton", "bwf"]):
        return "🏸", "Cầu Lông"
    if any(k in combined for k in ["bóng chuyền", "volleyball"]):
        return "🏐", "Bóng Chuyền"
    if any(k in combined for k in ["võ thuật", "mma", "boxing", "one championship", "ufc"]):
        return "🥊", "Võ Thuật"
    if any(k in combined for k in ["bóng bàn", "table tennis", "ittf", "wtt"]):
        return "🏓", "Bóng Bàn"
    
    # Detect tên người châu Á viết hoa toàn bộ họ (pattern bóng bàn/cầu lông)
    # VD: "ZHOU Qihao vs HUANG Youzheng" → cả 2 đều có HỌ VIẾT HOA
    if re.search(r'\b[A-Z]{2,}\s+[A-Z][a-z]+\s+vs\s+[A-Z]{2,}\s+[A-Z][a-z]+', title):
        return "🏓", "Bóng Bàn"
    
    return "⚽", "Bóng Đá"

def _short_id(text: str, length: int = 12) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:length]

def _channel_id(match_id: str) -> str:
    """Tạo channel ID dạng kaytee-XXXXXXXXXXXX (12 hex chars)"""
    return f"kaytee-{_short_id(match_id, 12)}"

def _link_id(url: str) -> str:
    """Tạo link ID dạng lnk-XXXXXXXXXX (10 hex chars)"""
    return f"lnk-{_short_id(url, 10)}"


def generate_thumb(logo_a_url: str, logo_b_url: str, channel_id: str, session,
                   team_a: str = "", team_b: str = "",
                   match_time: str = "", league: str = "") -> str:
    """
    Tạo ảnh composite 1600x1200 (khớp với reference):
      [Logo A]     VS      [Logo B]
      [Tên A]    [Giờ]     [Tên B]
               [Tên giải]
    Logo mỗi đội được đặt trong ô vuông cố định → kích thước đồng đều.
    """
    W, H = 1600, 1200
    BG = (245, 245, 245)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Load font ─────────────────────────────────────────────────────────────
    def load_font(size, bold=False):
        candidates = (
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf", "arialbd.ttf"]
            if bold else
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arial.ttf", "arial.ttf"]
        )
        for p in candidates:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_vs     = load_font(160, bold=False)
    font_time   = load_font(80,  bold=False)
    font_team   = load_font(64,  bold=False)
    font_league = load_font(52,  bold=False)

    # ── Paste logo vào ô vuông cố định 360x360 ────────────────────────────────
    SLOT = 360       # kích thước ô vuông cố định cho mỗi logo
    LOGO_CY = 390    # tâm dọc của ô logo

    def paste_logo(url, cx):
        """Đặt logo vào ô vuông SLOT×SLOT căn giữa tại (cx, LOGO_CY)."""
        slot_img = Image.new("RGB", (SLOT, SLOT), BG)  # ô vuông nền
        if url:
            try:
                r = session.get(url, timeout=8)
                r.raise_for_status()
                logo = Image.open(io.BytesIO(r.content)).convert("RGBA")
                logo.thumbnail((SLOT, SLOT), Image.LANCZOS)   # thu nhỏ vừa ô
                bg = Image.new("RGBA", logo.size, (*BG, 255))
                bg.paste(logo, mask=logo.split()[3])
                logo_rgb = bg.convert("RGB")
                # Căn giữa logo trong ô vuông
                ox = (SLOT - logo_rgb.width)  // 2
                oy = (SLOT - logo_rgb.height) // 2
                slot_img.paste(logo_rgb, (ox, oy))
            except Exception:
                pass
        # Dán ô vuông vào canvas chính
        x = cx - SLOT // 2
        y = LOGO_CY - SLOT // 2
        img.paste(slot_img, (x, y))
        return y + SLOT   # y dưới cùng của ô

    bottom_a = paste_logo(logo_a_url, W // 4)        # x=400
    bottom_b = paste_logo(logo_b_url, 3 * W // 4)   # x=1200

    # ── VS + Giờ ở trung tâm ─────────────────────────────────────────────────
    draw.text((W // 2, LOGO_CY - 20), "VS",
              fill="#e84545", font=font_vs, anchor="mm")
    if match_time:
        time_display = match_time.split()[0]   # chỉ lấy "HH:MM"
        draw.text((W // 2, LOGO_CY + 115), time_display,
                  fill="#ff8000", font=font_time, anchor="mm")

    # ── Tên 2 đội bên dưới logo ───────────────────────────────────────────────
    team_y = max(bottom_a, bottom_b) + 44
    ZONE_W = W // 2 - 60

    def draw_team_name(name, cx, y):
        if not name:
            return
        words = name.split()
        lines, cur = [], ""
        for word in words:
            test = (cur + " " + word).strip()
            bb = draw.textbbox((0, 0), test, font=font_team)
            if bb[2] - bb[0] <= ZONE_W:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        lh = 76
        for i, line in enumerate(lines[:2]):
            draw.text((cx, y + i * lh), line,
                      fill="#222222", font=font_team, anchor="mm")

    draw_team_name(team_a, W // 4, team_y)
    draw_team_name(team_b, 3 * W // 4, team_y)

    # ── Tên giải đấu ở dưới cùng ─────────────────────────────────────────────
    if league:
        league_disp = league
        bb = draw.textbbox((0, 0), league_disp, font=font_league)
        while bb[2] - bb[0] > W - 120:
            league_disp = league_disp[:-1]
            bb = draw.textbbox((0, 0), league_disp + "…", font=font_league)
            league_disp_show = league_disp + "…"
        else:
            league_disp_show = league_disp
        draw.text((W // 2, H - 60), league_disp_show,
                  fill="#888888", font=font_league, anchor="mm")

    os.makedirs("thumbs", exist_ok=True)
    path = f"thumbs/{channel_id}.png"
    img.save(path, "PNG", optimize=True)
    return path


class BunchaTVScraper:
    def __init__(self):
        self.base_url = "https://bunchatv1.net"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        # QUAN TRỌNG: chỉ set User-Agent, KHÔNG set Accept-Language/Encoding
        # vì server sẽ trả HTML rút gọn (~22KB) nếu có các header đó
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    # ── Bước 1: Lấy danh sách trận ───────────────────────────────────────────

    def collect_all_matches(self):
        """
        Quét trang chủ để lấy TẤT CẢ trận (live + sắp live).
        Mỗi trận chỉ lấy 1 lần dù xuất hiện ở nhiều section (dedup bằng match_id).
        """
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Đang quét {self.base_url}...")
        response = self.session.get(self.base_url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        seen_ids = set()
        matches  = []

        # Class "item_streaming" xuất hiện ở TẤT CẢ sections (HOT, SÓNG QUỐC TẾ, LỊCH BL...)
        # tbs2_MATCHID nằm trong class list → dùng để dedup
        all_containers = soup.find_all("div", class_="item_streaming")
        print(f"  Tổng containers tìm thấy: {len(all_containers)}")

        for container in all_containers:
            classes = " ".join(container.get("class", []))

            link_tag = container.find("a", class_="grid-match__body", href=True)
            if not link_tag:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = self.base_url + href

            # Chỉ lấy trận HÔM NAY (kiểm tra ngày trong URL)
            today_str = datetime.now().strftime("%d-%m-%Y")
            if today_str not in href:
                continue

            # Lấy match_id từ class tbs2_XXXXXXXXX (HOT section)
            # hoặc từ cuối URL (SÓNG QUỐC TẾ section không có class tbs2_)
            id_match = re.search(r"tbs2_(\d+)", classes)
            if id_match:
                match_id = id_match.group(1)
            else:
                url_id = re.search(r"/(\d+)/?$", href)
                if not url_id:
                    continue
                match_id = url_id.group(1)

            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            # Lấy giờ thi đấu từ URL trước (cần để check is_live fallback)
            # VD: .../eyupspor-vs-kocaelispor-2000-09-03-2026/601293394 → "20:00 09/03"
            time_from_url = ""
            url_time = re.search(r'-(\d{4})-(\d{2})-(\d{2})-\d{4}/', href)
            if url_time:
                hhmm, dd, mm = url_time.group(1), url_time.group(2), url_time.group(3)
                time_from_url = f"{hhmm[:2]}:{hhmm[2:]} {dd}/{mm}"

            # Phân loại live/sắp live từ CSS class
            is_live = "stream_m_live" in classes

            # Fallback: nếu giờ hiện tại đã qua giờ bắt đầu (trong vòng 4h) → coi là live
            if not is_live and time_from_url:
                try:
                    hh = int(time_from_url[:2])
                    mm_t = int(time_from_url[3:5])
                    now = datetime.now()
                    match_start = now.replace(hour=hh, minute=mm_t, second=0, microsecond=0)
                    elapsed = (now - match_start).total_seconds()
                    # Chỉ set live nếu ĐÃ QUA giờ bắt đầu (elapsed > 0) và trong vòng 4h
                    if 0 < elapsed <= 14400:
                        is_live = True
                except Exception:
                    pass

            info = self._extract_card_info(container, link_tag, match_id, is_live)
            info["page_url"] = href
            # Dùng giờ từ URL nếu selector CSS không tìm được
            if not info["match_time"] and time_from_url:
                info["match_time"] = time_from_url
            matches.append(info)

        print(f"  → {sum(1 for m in matches if m['is_live'])} live  |  "
              f"{sum(1 for m in matches if not m['is_live'])} sắp live")
        return matches

    def _extract_card_info(self, container, link_tag, match_id, is_live):
        """Trích xuất metadata từ card HTML trên trang chủ."""
        # League
        league_el = container.find("span", class_="text-ellipsis")
        league = league_el.get_text(strip=True) if league_el else ""

        # Tên 2 đội
        home_el = container.find("span", class_=re.compile(r"team--home-name"))
        away_el = container.find("span", class_=re.compile(r"team--away-name"))
        team_a  = home_el.get_text(strip=True) if home_el else ""
        team_b  = away_el.get_text(strip=True) if away_el else ""
        title   = f"{team_a} vs {team_b}" if team_a else link_tag.get("title", "Unknown")

        # Logo riêng từng đội
        logos = container.find_all("img", class_=re.compile(r"team__logo"))
        logo_a = logos[0].get("src", "") if len(logos) > 0 else ""
        logo_b = logos[1].get("src", "") if len(logos) > 1 else ""

        # Thời gian hiển thị (vd: "17:00 09/03")
        time_el    = container.find("div", class_="grid-match__datef")
        match_time = time_el.get_text(strip=True) if time_el else ""

        return {
            "match_id":   match_id,
            "title":      title,
            "league":     league,
            "team_a":     team_a,
            "team_b":     team_b,
            "logo_a":     logo_a,
            "logo_b":     logo_b,
            "match_time": match_time,
            "is_live":    is_live,
            "page_url":   "",   # sẽ điền sau
        }

    # ── Bước 2: Lấy stream links từ trang detail ─────────────────────────────

    def get_stream_links(self, match_info):
        """
        Truy cập trang detail để lấy TẤT CẢ m3u8 URLs (có thể nhiều nguồn).
        Referer = URL trang detail của trận (quan trọng, CDN kiểm tra cái này).
        """
        url = match_info["page_url"]
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # Lấy og:image làm thumbnail composite (ảnh ghép 2 đội)
            # (bỡ qua - trang detail không có og:image)

            # Tìm tất cả m3u8 từ jwplayer file: "..."
            found = re.findall(
                r"""['"']file['"']\s*:\s*['"']\s*(https?://[^'"']+\.m3u8[^'"']*)['"]\s*""",
                html
            )
            # Fallback nếu regex trên không khớp (do khoảng trắng)
            if not found:
                found = re.findall(
                    r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
                    html
                )

            # Loại bỏ trùng lặp, giữ thứ tự
            seen_urls = set()
            unique = []
            for u in found:
                u = u.strip()
                if u not in seen_urls:
                    seen_urls.add(u)
                    unique.append(u)

            return unique, ""

        except Exception as e:
            print(f"    ✗ Lỗi trang detail ({url}): {e}")
            return [], ""

    # ── Bước 3: Xuất JSON định dạng monplayer ────────────────────────────────

    def build_monplayer_json(self, matches_with_streams):
        """Tạo cấu trúc JSON chuẩn monplayer."""
        from collections import defaultdict

        # Sắp xếp tất cả trận theo giờ bắt đầu (HH:MM)
        sorted_matches = sorted(
            matches_with_streams,
            key=lambda m: m.get("match_time", "").split()[0] if m.get("match_time") else "99:99"
        )

        # live_groups / upcoming_groups: (emoji, sport_name) → [channels]
        live_groups     = defaultdict(list)
        upcoming_groups = defaultdict(list)

        for m in sorted_matches:
            stream_links = m.get("stream_links", [])
            if not stream_links:
                continue

            match_id   = m["match_id"]
            title      = m["title"]
            league     = m["league"]
            match_time = m["match_time"]
            is_live    = m["is_live"]
            page_url   = m["page_url"]
            logo_a     = m["logo_a"]
            logo_b     = m["logo_b"]

            # Chỉ dùng HH:MM trong tên kênh
            time_hhmm = match_time.split()[0] if match_time else ""

            # Tạo ảnh composite: logo A + VS + giờ + logo B + tên đội + tên giải
            uid = _channel_id(match_id)
            thumb_path = generate_thumb(
                logo_a, logo_b, uid, self.session,
                team_a=m["team_a"], team_b=m["team_b"],
                match_time=match_time, league=league,
            )
            thumb_url = (
                f"https://raw.githubusercontent.com/VietNM127/Get-IPTV-scraper/main/{thumb_path}?v={int(datetime.now().timestamp())}"
                if thumb_path else logo_a
            )

            sport_emoji, sport_name = _sport_category(league, title)
            label_text  = "● Live"  if is_live else "⏳ Sắp Live"
            label_color = "#ff0000" if is_live else "#d54f1a"

            links_list = []
            for i, url in enumerate(stream_links):
                links_list.append({
                    "id":      _link_id(url),
                    "name":    f"Link {i+1}",
                    "type":    "hls",
                    "default": i == 0,
                    "url":     url,
                    "request_headers": [
                        {"key": "Referer",    "value": page_url},
                        {"key": "User-Agent", "value": "Mozilla/5.0"},
                    ],
                })

            thumb_key = f"thumbs/{uid}.webp"
            channel = {
                "id":             uid,
                "name":           f"{sport_emoji} {title} | {time_hhmm}",
                "type":           "single",
                "display":        "thumbnail-only",
                "enable_detail":  False,
                "image": {
                    "padding":          1,
                    "background_color": "#ececec",
                    "display":          "contain",
                    "url":              thumb_url,
                    "width":            1600,
                    "height":           1200,
                },
                "labels": [{
                    "text":       label_text,
                    "position":   "top-left",
                    "color":      "#00ffffff",
                    "text_color": label_color,
                }],
                "sources": [{
                    "id":   f"src-{match_id}",
                    "name": SOURCE_NAME,
                    "contents": [{
                        "id":   f"ct-{match_id}",
                        "name": title,
                        "streams": [{
                            "id":           f"st-{match_id}",
                            "name":         "KT",
                            "stream_links": links_list,
                        }],
                    }],
                }],
                "org_metadata": {
                    "league":    league,
                    "team_a":    m["team_a"],
                    "team_b":    m["team_b"],
                    "logo_a":    logo_a,
                    "logo_b":    logo_b,
                    "thumb":     thumb_url,
                    "thumb_key": thumb_key,
                },
            }

            sport_key = (sport_emoji, sport_name)
            if is_live:
                live_groups[sport_key].append(channel)
            else:
                upcoming_groups[sport_key].append(channel)

        # Sắp xếp nhóm theo thứ tự ưu tiên môn thể thao
        def _sport_sort(key):
            label = f"{key[0]} {key[1]}"
            try:
                return SPORT_ORDER.index(label)
            except ValueError:
                return 99

        groups = []
        for sport_key in sorted(live_groups.keys(), key=_sport_sort):
            e, name = sport_key
            groups.append({
                "id":            f"live_{name.lower().replace(' ', '_')}",
                "name":          f"🔴 Live {e} {name}",
                "display":       "vertical",
                "grid_number":   2,
                "enable_detail": False,
                "channels":      live_groups[sport_key],
            })
        for sport_key in sorted(upcoming_groups.keys(), key=_sport_sort):
            e, name = sport_key
            groups.append({
                "id":            f"upcoming_{name.lower().replace(' ', '_')}",
                "name":          f"⏳ Sắp Live {e} {name}",
                "display":       "vertical",
                "grid_number":   2,
                "enable_detail": False,
                "channels":      upcoming_groups[sport_key],
            })

        return {
            "id":          PLAYLIST_ID,
            "url":         PLAYLIST_URL,
            "name":        PLAYLIST_NAME,
            "color":       "#1cb57a",
            "grid_number": 3,
            "image":       {"type": "cover", "url": LOGO_URL},
            "updated_at":  datetime.now().isoformat(),
            "groups":      groups,
        }

    def save_json(self, data, output_file=OUTPUT_FILE):
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        total = sum(len(g["channels"]) for g in data.get("groups", []))
        print(f"\n✓ Đã lưu {total} kênh vào {output_file}")


def main():
    print("=" * 60)
    print("IPTV Stream Scraper - bunchatv1.net")
    print("=" * 60)

    scraper = BunchaTVScraper()

    # Bước 1: Thu thập danh sách trận
    matches = scraper.collect_all_matches()
    if not matches:
        print("⚠ Không tìm thấy trận nào.")
        scraper.save_json(scraper.build_monplayer_json([]))
        return

    # Bước 2: Lấy stream links cho từng trận
    print(f"\nĐang lấy stream links cho {len(matches)} trận...")
    for m in matches:
        stream_links, _ = scraper.get_stream_links(m)
        m["stream_links"] = stream_links
        m["og_image"] = ""
        status = f"{len(stream_links)} link(s)" if stream_links else "✗ không có stream"
        print(f"  [{status}] {m['title']} ({m['match_time']})")
        time.sleep(0.4)   # tránh spam

    # Bước 3: Xuất JSON monplayer
    data = scraper.build_monplayer_json(matches)
    scraper.save_json(data)

    live_count     = sum(1 for m in matches if m["is_live"] and m.get("stream_links"))
    upcoming_count = sum(1 for m in matches if not m["is_live"] and m.get("stream_links"))
    print(f"  → Live: {live_count}  |  Sắp live: {upcoming_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()


