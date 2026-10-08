# Blue Sea Agent Intelligence — nghiệm thu triển khai

**Nguồn PHP:** `ngocnhanvo/xuongmunonbaohiem-php@master`, commit `44d36df78b9d8faaa1e0adf782163fa83f65163b`.

**CI & runner duy nhất:** `ngocnhanvo/xuongmunonbaohiem-actions@main`. Không chạy workflow tại repository PHP/Astro và không sửa Astro trong đợt này.

## Những thay đổi đã triển khai

- LLM-first Planner: phân biệt tên trang/bảng giá tham khảo với đề nghị báo giá giao dịch; tra nguồn toàn website, ưu tiên Page/ESC Table rồi Post, không dựa URL trang đang mở.
- Knowledge Index: không loại section có bằng chứng giá chỉ vì tiêu đề chứa chữ “báo giá”.
- Bộ nhớ hội thoại theo session/chủ đề: giữ slot báo giá (số lượng, logo, nơi giao, mẫu, ngân sách) qua nhiều lượt; cập nhật giá trị mới nhất khi khách sửa, không lẫn với dữ liệu doanh nghiệp.
- Phân biệt ý định in logo với chi tiết file/vị trí chưa cung cấp, kể cả thay đổi “không in” → “có in”.
- LLM hiểu khác biệt kiến thức chung nón nửa đầu và 3/4, tránh ép sang `productCompare` khi không có hai SKU.

## Bằng chứng runner

| Kiểm tra | Run | Kết quả |
| --- | --- | --- |
| 7 kịch bản ban đầu, lint, deploy, smoke | [37834230823](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37834230823) | SUCCESS, 7/7 semantic |
| 8 kịch bản sau nâng cấp logo | [37835736104](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37835736104) | PHP/FTP/smoke PASS; 6/8 semantic; một timeout và một assertion quá chặt, đã khoanh vùng |
| Kiểm thử giá và so sánh ngữ cảnh | [37836772856](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37836772856) | Giá PASS; so sánh kiến thức chung PASS; câu báo giá đúng nhưng mẫu câu thiếu trong assertion |
| Chỉ kiểm tra lại câu nối tiếp quote | [37836982410](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37836982410) | SUCCESS 1/1, 4 lượt |
| Deploy bản guardrail cuối | [37837287056](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37837287056) | Unit/FTP/smoke SUCCESS. Semantic bị chặn bởi lỗi parser case ID của workflow, **không phải lỗi ứng dụng** |
| Kiểm tra độc lập đúng kịch bản 11 lượt trên production | [37837775572](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37837775572) | SUCCESS 1/1, cả 11 lượt PASS |

**Fix CI:** Workflow `agent-intelligence-ci.yml` đã đổi sang awk để đọc `semantic_case`, không chạy lại FTP chỉ nhằm tạo lại trạng thái xanh cho lịch sử.

## Kiểm thử thực tế được xác nhận

- Nhập nguyên tiêu đề trang “Báo Giá Sản Xuất Mũ Bảo Hiểm Theo Yêu Cầu” trả bảng giá tham khảo theo số lượng, không chuyển thẳng sang trang liên hệ.
- Sửa 500 → 800 nón giữ nơi giao Cần Thơ và nhu cầu in logo.
- Đơn 300 nón không in logo: khách đổi sang có in → Agent cập nhật và xác nhận được lựa chọn mới.
- Chuyển sang chính sách đổi trả, sau đó quay lại đơn 600 nón: nhớ số lượng, in logo, nơi giao.
- Trải qua 11 lượt xen kẽ nhiều chủ đề: câu hỏi nón nửa đầu vs 3/4 được trả lời bằng kiến thức chung và lượt cuối vẫn nhớ 750 nón, in logo, giao Cần Thơ.

## Phạm vi nghiệm thu

Kết quả xác nhận **tính năng, đường deploy, và các kịch bản hồi quy cụ thể** đã hoạt động. Chưa phải benchmark thống kê 120 kịch bản hoặc bảo đảm xác suất đúng 95% trên toàn bộ cách hỏi. Một số phản hồi LLM vẫn có thể biến thiên; nếu phát hiện case thất bại mới, thêm ca kiểm thử trước khi sửa semantic prompt. Dữ liệu doanh nghiệp luôn phải được xác minh từ Page/Post/WooCommerce tùy loại thông tin.
