# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.
>
> **Trạng thái:** Người nộp đã xác nhận khai báo này ngày 2026-11-14; giờ xác nhận chưa được cung cấp. Chưa chạy eval do ground truth chưa được cấp.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | Số ảnh `is_defect=1` trong top-B / tổng số ảnh `is_defect=1` trong split eval. B=20; denominator chưa biết vì GT ẩn chưa được cấp. |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép chính xác theo `image_id`; evaluator lọc prediction theo ảnh có trong GT eval và xếp score giảm dần. |
| Candidate pool cố định | 96 ảnh trong `fixtures/t02_raw_qc/images.csv`; 56 dev (14 cảnh) và 40 eval (10 cảnh). Eval chỉ dùng 40 ảnh khi có GT. |
| Review budget B / K | B=20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Không có threshold phân loại. Với từng feature, chuẩn hóa lệch khỏi median dev bằng robust scale (1.4826×MAD; fallback IQR/std); tham chiếu riêng theo `camera_id + light` khi nhóm có ≥3 ảnh dev, nếu không dùng dev toàn cục. Score là tổng anomaly dương, mỗi thành phần clip tối đa 4: blur (log Laplacian thấp), dark (mean brightness thấp hoặc frac_dark cao), glare (frac_saturated cao). Không dùng nhãn eval để chọn trọng số/ngưỡng. |
| Eval split (không dùng để tune) | `split=eval`, 40 ảnh thuộc 10 cảnh; GT tương ứng chưa có trong workspace. |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Miss/FN: GT defect ngoài top-20. False alarm/FP: ảnh không defect trong top-20. Báo thêm Precision@B và false alarm trong từng slice light. Chưa thể tính số lượng khi chưa có GT. |
| Slices sẽ báo cáo (≥2) | `light` (day/dusk/night) và `defect_type` (blur/glare/dark/compression); slice metrics chưa tính do thiếu GT. |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Chưa tính CI. Khi có GT, dự kiến bootstrap theo cảnh (`group_id`) để giữ tương quan ảnh cùng cảnh; báo N và khoảng tin cậy, không coi ảnh trong một cảnh là độc lập. |
| Ngày giờ chốt + người chốt | 2026-11-14 (giờ xác nhận chưa được cung cấp); Nguyen Tuan Hung - reviewer (owner trong `configs/lab.yaml`), đã xác nhận. |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
