# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục                        | Giá trị                                                                                                                           |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Group ID                   | G03 (theo `configs/lab.yaml`; bài làm này thực hiện cá nhân)                                                                      |
| Challenge                  | T02 · Raw QC Triage — xếp hạng ảnh mờ, lóa, thiếu sáng hoặc có vấn đề chất lượng để người review xử lý                            |
| Thành viên (5–6) + vai trò | Cá nhân: Nguyen Tuan Hung (owner trong cấu hình: `Nguyen Tuan Hung - reviewer`), kiêm cấu hình, PoC, kiểm thử, review và báo cáo. |
| Git URL                    | https://github.com/hungnguyen67/K5-L2A-DAY06-NguyenTuanHung-2A202603199-DataGovernanceAndPrivacy                                  |
| Tag `demo-180m` (commit)   | Annotated tag trên commit nộp cuối; cùng trỏ vào commit với `final-24h`                                                            |
| Tag `final-24h` (commit)   | Annotated tag trên commit nộp cuối; cùng trỏ vào commit với `demo-180m`                                                            |
| Deadline (giờ VN)          | Chưa được cung cấp                                                                                                                |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Người review mất thời gian nếu ảnh tốt bị đưa vào queue (false alarm); ảnh lỗi bị bỏ sót có thể đi tiếp vào bước ingest/training, làm giảm chất lượng dữ liệu và tạo thêm chi phí kiểm tra hoặc chụp lại. Chủ sở hữu dữ liệu chịu rủi ro vận hành khi quyết định release không có bằng chứng.
- Điểm nghẽn cụ thể: Triage thủ công toàn bộ ảnh tốn công; ngân sách review cố định B=20 nên cần đưa ảnh có khả năng lỗi lên trước. PoC xử lý ảnh đơn lẻ bằng feature toàn ảnh, chưa phân tích ROI.
- Đầu vào → đầu ra: 96 ảnh JPEG synthetic (320×180 theo tài liệu T02) cùng `image_id`, `path`, `camera_id`, `light`, `split` → `ranked_review.csv` gồm `image_id, score` (score cao được review trước), queue top-20, contact sheet HTML, file quyết định HOLD.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): Chưa có ngưỡng GO được hiệu chuẩn vì ground truth/evaluator overlay chưa được cấp. Chính sách hiện thực tế trong code là HOLD (`POLICY_NOT_IMPLEMENTED`); không tự động release. GO/REWORK chỉ nên đặt sau khi có metric ẩn và quy tắc human-review được người phụ trách xác nhận.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): Fixture là dữ liệu synthetic, không phải ảnh hiện trường; feature blur/brightness/saturation chỉ là tín hiệu ưu tiên review, không phải kết luận chất lượng hay căn cứ pháp lý. Nếu đưa vào vận hành, domain owner phải xác nhận tiêu chí “defect”, người có quyền quyết định và quy trình recapture/release.

## 02 · Data & provenance

| Split          | N                | Nguồn / link                                                                                      | License | Synthetic? |
| -------------- | ---------------- | ------------------------------------------------------------------------------------------------- | ------- | ---------- |
| dev            | 56 ảnh / 14 cảnh | `fixtures/t02_raw_qc/` — `images.csv`, ảnh trong `images/`; nguồn synthetic ghi trong manifest    | CC0-1.0 | Có         |
| eval / heldout | 40 ảnh / 10 cảnh | `fixtures/t02_raw_qc/` — split eval có metadata nhưng không có `gt/labels.csv` trong bản học viên | CC0-1.0 | Có         |

- Schema & class mapping: Input `image_id, path, camera_id, light, split`; `camera_id ∈ {cam_A, cam_B}`, `light ∈ {day, dusk, night}`. Theo đề T02, GT (không có trong workspace) dùng `defect_type ∈ {none, blur, glare, dark, compression}`, `severity ∈ {0,1,2}`, `is_defect`. Một ảnh ghép prediction với GT theo `image_id`.
- Seed: 42 · Cách chia split (theo scene/group/segment?): Seed 42 theo cấu hình/manifest. Tài liệu T02 mô tả chia theo cảnh gốc; kiểm tra manifest cho thấy 24 `group_id` (14 dev, 10 eval), không trộn ảnh của cùng cảnh giữa split.
- `manifest.csv` verified (sha256): Có — `py -3.12 -m tools.verify_manifests` báo 14 manifests, 0 failing; manifest T02 ghi nguồn synthetic và CC0-1.0.
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: Không dùng dữ liệu thật; không tự xây GT. GT của fixture không được phân phối trong workspace hiện tại.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: (1) ACDC (Sakaridis et al.) cung cấp bối cảnh về khó khăn của ảnh lái xe trong điều kiện bất lợi; dùng để biện minh việc xem xét slice night/adverse conditions, không dùng ACDC làm input. (2) ISO/IEC TR 5259-6:2026 mô tả visualization framework cho data quality; liên quan cách trình bày bằng chứng review, không phải chứng nhận tuân thủ hay bằng chứng metric của PoC. Metadata được xác nhận trên IEC Webstore vì trang ISO trả HTTP 403 khi truy cập. (3) Tài liệu CVAT mô tả tự động gán nhãn, threshold và ROI; tham khảo cho human-review/ROI có thể cải tiến, CVAT không được dùng trong PoC. Cả ba URL và ngày xem 2026-11-14 được ghi ở References.
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): `images.csv + manifest.csv` → xác minh SHA-256 và đọc ảnh → tính log Laplacian sharpness, brightness trung bình, tỷ lệ pixel tối và bão hòa → chuẩn hóa theo median/MAD của split dev theo `camera_id + light` (fallback thống kê dev toàn cục nếu nhóm có dưới 3 ảnh) → cộng các anomaly dương đã clip để tạo score → chọn top-20 → contact sheet/reviewer CSV → audit quyết định review → HOLD bảo thủ → report. Pipeline ghi quyết định reviewer vào audit log nhưng chưa áp override vào prediction.
- Thành phần offline (model/weights + checksum + license nếu có): Không dùng pretrained model/weights, API hoặc network. Dùng NumPy, Pandas, Pillow và SciPy đã có trong môi trường; ảnh synthetic CC0-1.0, checksum input được kiểm bằng manifest.
- Trade-offs đã cân nhắc: Heuristic nhiều feature dễ chạy offline và giải thích được hơn model, đồng thời chuẩn hóa camera/light để giảm báo nhầm do quang học/điều kiện sáng. Đổi lại, feature toàn ảnh không định vị ROI, tỷ lệ saturated không mô tả đầy đủ glare cục bộ, chưa có feature JPEG blockiness riêng, và metadata sai có thể làm lệch chuẩn hóa. Không dùng nhãn eval để hiệu chỉnh.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): Baseline đã chạy là `src.examples.random_baseline` (random score có seed), T02, offline, seed 42, 96 ảnh, B=20; output `out/baseline/ranked_review.csv`, runtime 0.1159 s, Python 3.15.2. Đây là wiring baseline của repo, **khác baseline Laplacian ngưỡng đơn được mô tả trong mục 4 của T02.md**; cần xác nhận với giảng viên baseline nào phải dùng. `run_info.json` ghi HEAD `b0ce8bf`, nhưng không phải commit chứa các thay đổi PoC đang ở worktree.
- PoC (mô tả, version/config, commit): `src.pipeline` — heuristic blur/dark/glare với chuẩn hóa robust từ dev theo camera/light; offline, seed 42, config `configs/lab.yaml`, 96 ảnh, B=20. Output `out/poc/ranked_review.csv`; runtime 0.4872 s, Python 3.12.10. PoC và audit review được chạy từ commit `d4f4b72d3d422b8bf914981bc0f2b26a6bf3ed5a`.
- Cùng budget / cùng heldout / cùng seed: xác nhận cùng fixture pool (96 ảnh), B=20, seed 42 và cùng CPU. Chưa xác nhận được metric trên cùng heldout vì GT không có. Runtime không so sánh tuyệt đối được vì baseline chạy Python 3.15.2 còn PoC Python 3.12.10.

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit)                        | Baseline                                                               | PoC                                                                    | Δ & chú thích                                                     |
| ------------------------------------ | ---------------------------------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Primary: Defect Recall@B (tỷ lệ)     | Chưa có — GT chưa được cấp                                             | Chưa có — GT chưa được cấp                                             | Không tính Δ; higher is better                                    |
| Hard-slice: False alarm theo `light` | Chưa có — GT chưa được cấp                                             | Chưa có — GT chưa được cấp                                             | Không tính; eval có metadata day N=20, dusk N=4, night N=16       |
| Review@B / miss / FP                 | Reviewer đã ghi 20/20 quyết định `reject` và 20 ghi chú; không phải GT | Reviewer đã ghi 20/20 quyết định `reject` và 20 ghi chú; không phải GT | Miss/FP chưa xác định; B=20                                       |
| Runtime / 100 items                  | 0.1207 s/100 (Python 3.15.2)                                           | 0.5075 s/100 (Python 3.12.10)                                          | Cùng CPU, khác Python; chỉ tham khảo, chưa phải so sánh kiểm soát |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: Defect Recall@B trên đơn vị ảnh = số ảnh defect trong top-20 / tổng số ảnh defect trong split eval. TP là defect được xếp trong top-20; FN là defect eval bị bỏ ngoài top-20; FP là ảnh không defect lọt vào top-20. Denominator chính xác chưa biết vì GT ẩn; xem khai báo ở `reports/metric_contract.md`.
- Threshold / budget B / K và lúc chốt: B=20 theo `configs/tracks/t02.yaml`; không có threshold phân loại cố định, hệ thống xếp hạng theo tổng anomaly score. Tham chiếu normalization chỉ dùng split dev. Metric contract được người nộp xác nhận ngày 2026-11-14 (chưa có giờ cụ thể); chưa chạy hidden eval vì chưa có GT.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: Chưa tính được vì chưa có GT. Nếu có GT, báo N và khoảng tin cậy bootstrap theo `group_id`/cảnh (không bootstrap độc lập từng ảnh vì ảnh cùng cảnh có thể tương quan); đây là kế hoạch, chưa phải kết quả.
- Lệnh evaluate chính xác: Sau khi giảng viên cấp overlay `gt/labels.csv`, chạy `py -3.12 -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json`; baseline tương tự với `out/baseline/ranked_review.csv` và `--run-name baseline`. Hiện chưa chạy vì `fixtures/t02_raw_qc/gt/labels.csv` không có.

## 06 · Result slices

| Slice         | N                 | Baseline          | PoC               | Ghi chú                                        |
| ------------- | ----------------- | ----------------- | ----------------- | ---------------------------------------------- |
| `light=day`   | 20 ảnh trong eval | Chưa có GT metric | Chưa có GT metric | N từ metadata; không diễn giải là defect count |
| `light=dusk`  | 4 ảnh trong eval  | Chưa có GT metric | Chưa có GT metric | N từ metadata; không diễn giải là defect count |
| `light=night` | 16 ảnh trong eval | Chưa có GT metric | Chưa có GT metric | N từ metadata; không diễn giải là defect count |

- Failure case 1 (ảnh/metadata + root cause): Ghi nhận review thủ công, chưa xác nhận với GT: `img_13_3` (rank 1, score 8.0, night) được reviewer mô tả rất mờ/tối và không thể nhận diện phương tiện. Đây là hard case blur+dark; score cao vì các feature toàn ảnh cùng lệch dev. Chưa thể kết luận đây là true positive hay false alarm nếu thiếu nhãn.
- Failure case 2: Ghi nhận review thủ công, chưa xác nhận với GT: `img_17_2` (rank 13, score 5.546786, day) được mô tả có glare trắng che một vùng đường/tòa nhà và blur. Điểm yếu cần kiểm tra là glare cục bộ có thể bị loãng trong thống kê toàn ảnh; ảnh này vẫn được đưa vào queue, không chứng minh recall chung. Reviewer cũng ghi nhận lỗi hình học synthetic ở các ảnh khác (ví dụ người đi bộ chồng lên xe), nằm ngoài feature set hiện tại.
- Latency / compute (máy, CPU, ms/item): Windows 11; Intel64 Family 6 Model 140 Stepping 1, Intel64 processor; baseline 0.1159 s/96 ảnh = 0.1207 s/100 ảnh (Python 3.15.2); PoC 0.4872 s/96 ảnh = 0.5075 s/100 ảnh (Python 3.12.10). Thời gian lấy từ `out/{baseline,poc}/run_info.json`; môi trường Python khác nhau nên so sánh chỉ tham khảo.

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, B=20, sắp xếp score giảm dần; contact sheet offline ở `out/poc/contact_sheet.html`. Reviewer `Nguyen Tuan Hung` đã xuất `out/poc/review_queue_reviewed.csv`: 20 dòng đều có quyết định `reject`, 20 ghi chú, không có override_value. Các quyết định này là review thủ công, không thay thế hidden GT.
- Cách override + audit log (`out/poc/audit_log.jsonl`): Sau khi chạy lại PoC với `out/poc/review_queue_reviewed.csv`, pipeline đã ghi 20 sự kiện `review:reject` với reviewer, item, ghi chú và thời điểm review. Bản evidence được lưu thêm tại `reports/audit_log.jsonl`. Không có `override_value`; audit ghi nhận quyết định thủ công nhưng không áp dụng thay đổi vào score/prediction. `decision.json` vẫn là HOLD.
- Decision policy + `reason_code` + owner: `out/poc/decision.json` ghi `HOLD`, `reason_code=POLICY_NOT_IMPLEMENTED`, owner `Nguyen Tuan Hung - reviewer`; không có metric snapshot hoặc evidence path.
- Khi nào HOLD/REWORK thay vì tự động release: Hiện luôn HOLD vì chưa có policy và GT validation. Trong thiết kế tiếp theo, HOLD khi review/GT/decision owner chưa xác nhận; REWORK/recapture chỉ khi reviewer/domain owner kết luận ảnh không dùng được. Không tự động release từ heuristic hiện tại.

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t__ --pred out/<file> --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: `py -3.12 -m pytest -q` kết thúc exit code 0; các test cần ground truth ẩn được skip theo cấu hình repo. `py -3.12 -m pytest -q tests/test_pipeline_t02.py tests/test_cli.py` đạt 8 passed / 2 skipped.
- Máy / CPU / OS / Python: Intel64 Family 6 Model 140 Stepping 1 · Windows 11 · PoC Python 3.12.10 (baseline run ghi Python 3.15.2) · run info của lượt PoC cuối ghi SHA `d4f4b72`, commit chứa code audit review.

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: Fixture manifest ghi synthetic, CC0-1.0; không dùng data/real hoặc model pretrained. Không xác nhận được license của dữ liệu ngoài vì không có dữ liệu ngoài. Không đưa kết luận về PII/tuân thủ pháp lý cho dữ liệu vận hành từ kết quả PoC này.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: Chưa biết recall/precision, số miss/FP và tỷ lệ lỗi từng slice vì thiếu GT. Reviewer thấy các vấn đề tối/mờ, glare, lỗi hình học synthetic; đây là quan sát, không phải nhãn evaluator. Ngoại suy tuyến tính từ 0.4872 s/96 ảnh cho 960 ảnh khoảng 4.872 s trên cùng môi trường là ước tính thô, chưa benchmark 10×; I/O và môi trường có thể làm thay đổi thời gian.
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: Không có kết luận tuân thủ nào được đưa ra. Nếu thay fixture bằng ảnh thật có người/biển số, cần xác nhận căn cứ xử lý, mục đích, quyền truy cập, thời hạn lưu/xóa, license và phê duyệt DPO/legal trước khi chạy/chia sẻ.
- Kế hoạch cải tiến: (1) lấy hidden GT và chạy baseline/PoC cùng protocol; (2) xác nhận baseline chính thức với giảng viên do tài liệu T02 và target mẫu khác nhau; (3) thêm kiểm tra glare cục bộ/ROI và JPEG blockiness; (4) kiểm tra metadata light sai; (5) hoàn thiện policy áp override; audit log hiện đã ghi nhận các quyết định review; (6) báo cáo CI bootstrap theo cảnh và thêm tests cho edge cases.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email                                       | Module / vai trò                                | Commit SHA / diff chứng minh                                                                                                                     | Trình bày?    |
| -------- | ------------------------------------------------------ | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------- |
| Nguyen Tuan Hung | `hungnguyen67 <hungnn91296@gmail.com>` (Git author trùng owner của remote `origin`, phù hợp với owner trong `configs/lab.yaml`) | Làm cá nhân; config, reviewer, PoC (có trợ giúp AI), kiểm thử và báo cáo | Commit triển khai T02: `c12d483e7bcc3e7852dfa1fe9540eaac0db80128`; commit audit review: `d4f4b72d3d422b8bf914981bc0f2b26a6bf3ed5a` | Không |

Ghi chú minh bạch: Git author `hungnguyen67 <hungnn91296@gmail.com>` khớp owner của remote `origin` và nhất quán với `Nguyen Tuan Hung` trong cấu hình bài. `git shortlog` còn có author khác trong lịch sử repository; không gán các commit đó cho cá nhân. Baseline `run_info.json` ghi SHA `b0ce8bf`; lượt PoC cuối ghi `d4f4b72`, commit chứa phần ghi audit review.

## 11 · References

| URL                                                                                                                                                                                                         | Ngày xem   | 1–2 dòng ý nghĩa (không chép nguyên văn)                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| https://arxiv.org/abs/2104.13395 — Sakaridis et al., _ACDC: The Adverse Conditions Dataset with Correspondences for Robust Semantic Driving Scene Perception_                                               | 2026-11-14 | Dataset/paper nghiên cứu perception trong điều kiện adverse như nighttime, fog, rain, snow; hỗ trợ lựa chọn phân tích hard slice theo điều kiện sáng. Fixture của bài này không lấy từ ACDC. |
| https://webstore.iec.ch/en/publication/113479 — ISO/IEC TR 5259-6:2026, _Artificial intelligence — Data quality for analytics and machine learning (ML) — Part 6: Visualization framework for data quality_ | 2026-11-14 | IEC Webstore xác nhận tên, edition và ngày xuất bản 2026-05-04. Liên quan cách trực quan hóa bằng chứng/chỉ số chất lượng dữ liệu; không được dùng để tuyên bố PoC đạt chuẩn.                |
| https://docs.cvat.ai/docs/annotation/auto-annotation/automatic-annotation/ — CVAT, _Automatic annotation_                                                                                                   | 2026-11-14 | Tài liệu chính thức mô tả pre-annotation bằng model, threshold và ROI; tham khảo cho thiết kế review/ROI trong tương lai. CVAT không được dùng trong PoC này.                                |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật. (Repo URL có; tag demo/final chưa tạo.)
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy. (Run/tests đã chạy; evaluate đang chờ GT.)
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log. (Có review notes và decision HOLD; metric và audit review chưa hoàn tất.)
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N. (Provenance/split/seed/offline đã kiểm; GT và denominator eval chưa có.)
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên. (Làm cá nhân nhưng thay đổi PoC hiện chưa commit; cần xác nhận Git author/email.)
