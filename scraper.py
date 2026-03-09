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
from datetime import datetime
from bs4 import BeautifulSoup
import time

# ── Cấu hình ─────────────────────────────────────────────────────────────────
OUTPUT_FILE   = "streams.json"
SOURCE_NAME   = "Bún Chả TV"          # tên nguồn hiển thị trong monplayer
PLAYLIST_ID   = "buncha"              # id playlist trong monplayer
PLAYLIST_NAME = "Bún Chả TV"

# ⚠️  QUAN TRỌNG: Điền URL GitHub Pages của bạn vào đây sau khi deploy!
# Monplayer dùng URL này để tự động refresh playlist (lấy link m3u8 mới).
# Nếu để trống, stream sẽ bị lỗi sau khi link hết hạn (~vài tiếng).
# Ví dụ: "https://YOUR_USERNAME.github.io/Get-IPTV/streams.json"
PLAYLIST_URL  = "https://raw.githubusercontent.com/VietNM127/Get-IPTV-scraper/main/streams.json"

LOGO_URL      = "https://kaytee1012.github.io/buncha_logo.png"
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

def _short_id(text: str, length: int = 12) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:length]

def _channel_id(match_id: str) -> str:
    """Tạo channel ID dạng kaytee-XXXXXXXXXXXX (12 hex chars)"""
    return f"kaytee-{_short_id(match_id, 12)}"

def _link_id(url: str) -> str:
    """Tạo link ID dạng lnk-XXXXXXXXXX (10 hex chars)"""
    return f"lnk-{_short_id(url, 10)}"


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

            # Lấy match_id từ class tbs2_XXXXXXXXX
            id_match = re.search(r"tbs2_(\d+)", classes)
            if not id_match:
                continue
            match_id = id_match.group(1)

            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            # Phân loại trạng thái
            is_live    = "stream_m_live" in classes
            is_today   = "stream_m_today" in classes
            if not (is_live or is_today):
                continue

            link_tag = container.find("a", class_="grid-match__body", href=True)
            if not link_tag:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = self.base_url + href

            info = self._extract_card_info(container, link_tag, match_id, is_live)
            info["page_url"] = href
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

            # Tìm tất cả m3u8 từ jwplayer file: "..."
            found = re.findall(
                r"""['"]file['"]\s*:\s*['"]( https?://[^'"]+\.m3u8[^'"]*)['"]\s*""",
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

            return unique

        except Exception as e:
            print(f"    ✗ Lỗi trang detail ({url}): {e}")
            return []

    # ── Bước 3: Xuất JSON định dạng monplayer ────────────────────────────────

    def build_monplayer_json(self, matches_with_streams):
        """Tạo cấu trúc JSON chuẩn monplayer."""
        channels_live    = []
        channels_upcoming = []

        for m in matches_with_streams:
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
            # Dùng logo_a làm thumbnail card
            thumbnail  = logo_a

            emoji = _sport_emoji(league)
            label_text  = "● Live"       if is_live else "⏳ Sắp Live"
            label_color = "#ff0000"      if is_live else "#d54f1a"

            # Tạo danh sách stream_links
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

            uid = _channel_id(match_id)
            thumb_key = f"thumbs/{uid}.webp"
            channel = {
                "id":             uid,
                "name":           f"{emoji} {title} | {match_time}",
                "type":           "single",
                "display":        "thumbnail-only",
                "enable_detail":  False,
                "image": {
                    "padding":          1,
                    "background_color": "#ececec",
                    "display":          "contain",
                    "url":              thumbnail,
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
                    "thumb":     thumbnail,
                    "thumb_key": thumb_key,
                },
            }

            if is_live:
                channels_live.append(channel)
            else:
                channels_upcoming.append(channel)

        groups = []
        if channels_live:
            groups.append({
                "id":            "live",
                "name":          "🔴 Live",
                "display":       "vertical",
                "grid_number":   2,
                "enable_detail": False,
                "channels":      channels_live,
            })
        if channels_upcoming:
            groups.append({
                "id":            "upcoming",
                "name":          "⏳ Sắp Live",
                "display":       "vertical",
                "grid_number":   2,
                "enable_detail": False,
                "channels":      channels_upcoming,
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
        stream_links = scraper.get_stream_links(m)
        m["stream_links"] = stream_links
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


