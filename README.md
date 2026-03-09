# 📺 IPTV Stream Scraper

Hệ thống tự động cào dữ liệu live stream từ bunchatv1.net và xuất bản JSON cho IPTV players (monplayer, TiviMate, v.v.)

## 🚀 Tính năng

- ✅ Tự động cào dữ liệu mỗi 10 phút (có thể tùy chỉnh)
- ✅ Trích xuất link m3u8 kèm headers (Referer, User-Agent)
- ✅ Xuất bản JSON public qua GitHub Pages
- ✅ Không cần server/VPS - chạy hoàn toàn trên GitHub Actions
- ✅ Tương thích với monplayer và các IPTV players khác

## 📦 Cài đặt

### Bước 1: Fork hoặc Clone repo này

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### Bước 2: Test script locally (tùy chọn)

```bash
# Cài đặt dependencies
pip install -r requirements.txt

# Chạy thử scraper
python scraper.py
```

Nếu thành công, sẽ có file `streams.json` được tạo ra.

### Bước 3: Deploy lên GitHub

```bash
git add .
git commit -m "Initial commit"
git push origin main
```

### Bước 4: Bật GitHub Actions

1. Vào repository trên GitHub
2. Click tab **Actions**
3. Nếu workflows bị disabled, click **"I understand my workflows, go ahead and enable them"**
4. GitHub Actions sẽ tự động chạy mỗi 10 phút

### Bước 5: Bật GitHub Pages

1. Vào **Settings** → **Pages**
2. Source: chọn **GitHub Actions**
3. Hoặc chọn **Deploy from a branch** → **main** branch → **/root**
4. Sau vài phút, file JSON sẽ có tại:
   ```
   https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/streams.json
   ```

## 📝 Sử dụng

### Link JSON public

Sau khi deploy, sử dụng link này trong monplayer:

```
https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/streams.json
```

### Format JSON Output

```json
{
  "updated_at": "2026-03-09T10:30:00",
  "total_streams": 5,
  "streams": [
    {
      "title": "Man United vs Liverpool",
      "thumbnail": "https://example.com/thumb.jpg",
      "stream_url": "https://cdn.example.com/stream/index.m3u8",
      "request_headers": {
        "Referer": "https://player.example.com",
        "User-Agent": "Mozilla/5.0 ...",
        "Origin": "https://player.example.com"
      }
    }
  ]
}
```

## ⚙️ Tùy chỉnh

### Thay đổi tần suất cào dữ liệu

Sửa file `.github/workflows/scraper.yml`:

```yaml
schedule:
  # Mỗi 5 phút
  - cron: '*/5 * * * *'
  
  # Mỗi 15 phút
  - cron: '*/15 * * * *'
  
  # Mỗi giờ
  - cron: '0 * * * *'
```

### Thay đổi nguồn website

Sửa file `scraper.py`, dòng 15:

```python
self.base_url = "https://WEBSITE_KHAC.com"
```

Sau đó điều chỉnh các selector CSS trong hàm `extract_match_info()` cho phù hợp.

## 🔧 Troubleshooting

### Không tìm thấy stream

1. Website có thể thay đổi cấu trúc HTML
2. Cần inspect trang web và cập nhật CSS selectors trong `scraper.py`
3. Test bằng cách chạy `python scraper.py` local

### GitHub Actions không chạy

1. Kiểm tra tab Actions có bị disabled không
2. Đảm bảo file workflow ở đúng thư mục `.github/workflows/`
3. Kiểm tra syntax YAML có đúng không

### Link JSON trả về 404

1. Đảm bảo GitHub Pages đã được bật
2. Đợi vài phút để GitHub Pages deploy
3. Kiểm tra file `streams.json` đã được commit chưa

## 📱 Sử dụng với monplayer

1. Mở monplayer
2. Thêm nguồn JSON:
   ```
   https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/streams.json
   ```
3. monplayer sẽ tự động parse và hiển thị các stream

## ⚠️ Lưu ý

- Cào dữ liệu có thể vi phạm Terms of Service của website gốc
- Chỉ sử dụng cho mục đích cá nhân, không thương mại
- GitHub Actions có giới hạn 2000 phút/tháng (free tier)
- Với cron mỗi 10 phút: ~4320 lần chạy/tháng (mỗi lần ~1-2 phút)

## 📄 License

MIT License - Tự do sử dụng và chỉnh sửa

## 🤝 Đóng góp

Pull requests are welcome! Nếu có lỗi hoặc ý tưởng cải tiến, hãy tạo issue.
