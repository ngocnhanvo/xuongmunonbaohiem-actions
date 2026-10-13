# Signed Astro unzip v2 — Blue Sea

## Mục đích

Dùng lại `ENV_FILE` (`WC_URL_CLIENT` frontend, `WC_URL` backend) để chọn đường dẫn deploy thay vì ghi cứng tên miền trong `unzip.php`.

- Astro ZIP giữ tên `escvn.zip`.
- WordPress endpoint: `/unzip.php` (bắt buộc POST có HMAC).
- Ready marker: `/unzip-v2.ready` (nội dung chính xác: `ESC_ASTRO_UNZIP_PROTOCOL=2`).
- HMAC sử dụng `SOURCE_REPO_PAT` (GitHub Actions) và `VCS_GH_ACTIONS_TOKEN` (WordPress hiện có, từ `wp-content/esc-github-trigger-token.php`).
- Giao thức kiểm tra tên miền, đường dẫn, hash SHA-256 và nội dung ZIP; giải nén vào staging, sao lưu và thay thế các thư mục build.

## Thứ tự kích hoạt an toàn

1. Xác nhận `WC_URL` (backend WordPress) và `WC_URL_CLIENT` (frontend Astro) trong GitHub Secret `ENV_FILE` trỏ đúng môi trường và FTP có hai thư mục thực tế. Riêng những workflow WordPress cũ vẫn đọc `WP_ADMIN_URL` thì cần giữ Secret này đồng bộ.
2. Đảm bảo WordPress đã có `wp-content/esc-github-trigger-token.php` và `VCS_GH_ACTIONS_TOKEN` khớp `SOURCE_REPO_PAT` GitHub Actions. Nếu token đã thay đổi, chạy lại workflow `wordpress-trigger-deploy.yml` theo quy trình vận hành.
3. Chạy **Actions → Install signed Astro unzip v2 on WordPress → Run workflow** trong repo `xuongmunonbaohiem-actions`. Workflow upload đúng hai file ở WordPress webroot: `unzip.php`, `unzip-v2.ready`; kiểm tra FTP byte-for-byte và xác thực endpoint với một lệnh `check` có ký tên (không giải nén).
4. Chỉ sau khi bước 3 thành công mới kích hoạt `Deploy Blue Sea Astro Production` hoặc `Blue Sea FTP Artifact Recovery`. Cả hai workflow chặn trước FTP upload nếu endpoint v2 không sẵn sàng.
5. Kiểm tra log `SIGNED_UNZIP_PREFLIGHT_OK` và `SIGNED_UNZIP_SUCCESS`, rồi kiểm tra website sau deploy.

**Chưa cài endpoint v2 trên hosting?** Deploy Astro sẽ dừng trước bước upload ZIP, để không gọi nhầm phiên bản PHP cũ.

## Đổi domain

```text
ENV_FILE: WC_URL_CLIENT=https://tuannguyen.io.vn
ENV_FILE: WC_URL=https://admin.tuannguyen.io.vn
GitHub Secret WP_ADMIN_URL=https://admin.tuannguyen.io.vn (chỉ cho các workflow WordPress cũ)
FTP Astro: /domains/tuannguyen.io.vn/public_html/
FTP WordPress: /domains/admin.tuannguyen.io.vn/public_html/
```

Workflow cài `unzip.php` đọc `WC_URL` từ `ENV_FILE` để suy ra thư mục WordPress, không còn phụ thuộc `WP_ADMIN_URL` riêng. Đường dẫn Astro mặc định được suy ra từ `WC_URL_CLIENT`. Đây là **đường dẫn FTP ảo** (ví dụ `/domains/khachhang.com/public_html/`); `unzip.php` tự ánh xạ sang thư mục vật lý nằm cùng cây `domains` với WordPress (`/home/.../domains/khachhang.com/public_html/`). Server PHP trả lại đường dẫn FTP ban đầu để Actions có thể xác nhận đúng đích. Không tự mở rộng quyền truy cập sang thư mục nằm ngoài cây `domains`. `FTP_ASTRO_DIR` (GitHub Variable tùy chọn) chỉ hỗ trợ đường dẫn thực tế dạng `/domains/<hostname>/public_html/`. Nếu hosting không theo cấu trúc này, quy trình **dừng an toàn** và cần bổ sung quy tắc allowlist phù hợp trước khi deploy.

Artifact Recovery cố tình từ chối ZIP của domain cũ: `.env` nằm trong ZIP phải có cùng hostname `WC_URL_CLIENT` hiện tại.

## An toàn và vận hành

- Không gọi `unzip.php` bằng GET, không đưa token vào query string hoặc `.env` của Astro.
- HMAC SHA-256 có timestamp hạn 5 phút, so sánh constant-time; không cho phép redirect HTTP.
- PHP từ chối thư mục không thuộc `/domains/*/public_html/`, ZIP sai checksum, ZIP thiếu `server/entry.mjs` hoặc `client/`.
- Khoá `flock` ngăn hai lượt giải nén cùng lúc; staging/backup yêu cầu hosting có đủ dung lượng cho hai phiên bản build cùng tồn tại trong thời gian ngắn.
- Khi thay đổi PAT trong GitHub, cập nhật cả file token WordPress; hai bên không khớp sẽ từ chối giải nén.
- HTTP 200 **chưa đủ**: script Actions xác minh JSON `ok=true`, `protocol=2`, target, host, SHA-256 và số file kích hoạt.
- Việc sửa repository không tự động ghi FTP. Workflow cài PHP được đặt ở chế độ **manual** để tránh đổi endpoint production trước khi kiểm tra.

## Kiểm thử

`Astro Unzip v2 Safety QA` đã được thêm trong Actions để kiểm tra cú pháp, từ chối GET và xác thực parser URL. QA không ghi FTP.
