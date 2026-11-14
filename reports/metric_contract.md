# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage (ảnh mờ, lóa và thiếu sáng) |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | Numerator: số ảnh lỗi thật (GT defects) trong top-B; Denominator: tổng số ảnh lỗi thật trong split eval |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp theo định danh ảnh image_id |
| Candidate pool cố định | 96 ảnh synthetic từ 24 cảnh gốc (fixtures/t02_raw_qc/images.csv) |
| Review budget B / K | B = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Tinh chỉnh hoàn toàn trên split dev (60% cảnh gốc); không dùng nhãn eval để tune. Xác định phân vị và ngưỡng đa đặc trưng (sharpness, saturation, dark fraction) theo camera_id và light condition |
| Eval split (không dùng để tune) | eval (40% cảnh gốc còn lại, chia theo scene) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | False Alarm trong top-B theo slice ban đêm (night); Bỏ sót lỗi lóa cục bộ tại vùng biển số (glare FN) |
| Slices sẽ báo cáo (≥2) | 1. Slice điều kiện ánh sáng (day / dusk / night); 2. Slice loại camera (cam_A / cam_B) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson Score 95% Confidence Interval cho tỷ lệ phân loại nhị phân |
| Ngày giờ chốt + người chốt | 2026-11-14 16:30 · Đặng Thu Thúy |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
