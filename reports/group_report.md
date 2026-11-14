# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G63 |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên (5–6) + vai trò | 1. Đặng Thu Thúy (Full Pipeline Lead & Core Algorithm, Data & Review, QA) |
| Git URL | https://github.com/thuythu0965/K5-Day6-L2-DangThuThuy-03263-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ad9e707 |
| Tag `final-24h` (commit) | ad9e707 |
| Deadline (giờ VN) | 2026-11-15 18:00 |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Đội ngũ gán nhãn dữ liệu (Data Annotation) phải tốn chi phí và thời gian gắn nhãn trên các ảnh hỏng, mô hình Computer Vision huấn luyện trên dữ liệu nhiễu/lỗi quang học sẽ suy giảm độ chính xác nhận diện ngoài hiện trường, gây nguy hiểm cho hệ thống xe tự hành.
- Điểm nghẽn cụ thể: Thu thập hàng chục nghìn ảnh thô mỗi ngày nhưng ngân sách rà soát thủ công bị giới hạn nghiêm ngặt (chỉ duyệt được B=20 ảnh/mẻ). Cần lọc chính xác các ảnh lỗi nghiêm trọng nhất để tái chụp (recapture).
- Đầu vào → đầu ra: Đầu vào gồm ảnh thô 320x180 kèm metadata camera/ánh sáng (`images.csv`) → Đầu ra là bảng xếp hạng điểm nguy cơ `out/ranked_review.csv` và hàng đợi rà soát con người `out/review_queue.csv`.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): Nếu số lượng ảnh lỗi nghiêm trọng (score > 30.0) vượt quá 35 ảnh trong mẻ dữ liệu thì kích hoạt lệnh REWORK (chụp lại mẻ); ngược lại cấp phép phát hành GO kèm danh sách top-B cần khắc phục.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): Dữ liệu synthetic giả lập phản ánh trung thực phân bố quang học của cảm biến thật; quy định mức lỗi B=20 đáp ứng thời gian làm việc chuẩn của đội QC.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | fixtures/t02_raw_qc/images.csv (14 scene x 4 biến thể) | CC0-1.0 | Có (Synthetic) |
| eval / heldout | 40 | fixtures/t02_raw_qc/images.csv (10 scene x 4 biến thể) | CC0-1.0 | Có (Synthetic) |

- Schema & class mapping: `image_id, path, camera_id, light, split`. Các dạng lỗi gồm: `blur, glare, dark, compression, none`.
- Seed: 42 · Cách chia split (theo scene/group/segment?): Chia chặt chẽ theo `scene gốc` (60% dev, 40% eval) để tránh rò rỉ bối cảnh giữa các frame của cùng một cảnh.
- `manifest.csv` verified (sha256): có / không — lệnh: `python -m tools.verify_manifests` (Kiểm tra hash tự động ở bước 01 load).
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: Dùng fixture synthetic chuẩn của lab, xây dựng gold set nội bộ trên tập dev 56 mẫu để kiểm chứng phân vị và ngưỡng đặc trưng.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: 
  1. *ACDC Dataset (ETH Zürich)* — Phân tích sự suy giảm chất lượng thị giác theo điều kiện thời tiết và ánh sáng cực đoan (2026-11-14).
  2. *ISO/IEC TR 5259-6:2026* — Tiêu chuẩn quản trị chất lượng dữ liệu huấn luyện học máy (Data Quality for Analytics and ML) (2026-11-14).
  3. *Wang et al., Blind Measurement of Blocking Artifacts in Images (IEEE)* — Phương pháp đo tỷ số gradient biên khối 8x8 cho nén JPEG (2026-11-14).
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): `01 load` (kiểm tra manifest và đọc metadata) → `02 process` (trích xuất 4 đặc trưng thích ứng: adaptive sharpness, grid glare, adaptive dark, regularized JPEG blockiness) → `03 rank` (tạo review queue top-20) → `04 review` (duyệt mẫu offline qua HTML contact sheet, ghi audit log) → `05 decide` (áp dụng quality gate ra quyết định GO/REWORK).
- Thành phần offline (model/weights + checksum + license nếu có): Không dùng mô hình tải ngoài; sử dụng toán tử đại số ma trận và vi phân cục bộ trên NumPy/SciPy/Pillow, đảm bảo 100% offline.
- Trade-offs đã cân nhắc: Giữa việc đo lóa toàn cục (nhanh nhưng bỏ sót lóa cục bộ tại biển số) và lưới mịn 6x6 (tính toán thêm vài mili-giây nhưng bắt trọn mọi vùng lóa góc). Chọn giải pháp lưới 6x6 kết hợp hệ số điều hòa để loại bỏ hoàn toàn hiện tượng nổ số chia ở ảnh phẳng.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): Một ngưỡng Laplacian toàn ảnh duy nhất đo độ sắc nét (`score = 1000 / (var + 1.0)`), commit b0ce8bf.
- PoC (mô tả, version/config, commit): Đa đặc trưng kết hợp (Độ sắc nét thích ứng theo camera & ánh sáng, lưới phát hiện lóa 6x6, ngưỡng tối thích ứng và tỷ số vi phân biên khối JPEG), commit ad9e707.
- Cùng budget / cùng heldout / cùng seed: xác nhận Cùng budget B=20, cùng split dev (N=56), cùng seed 42.

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.3810 | 0.4762 | 0.0952 | +25.0% | higher | 56 |
| Precision@B (GT defects in top-B / B) | all | 0.8000 | 1.0000 | 0.2000 | +25.0% | higher | 56 |
| Defect-type accuracy (GT defects) (fraction) | all | 0.5714 | 0.5952 | 0.0238 | +4.2% | higher | 42 |
| False alarm in top-B (clean images in top-B / clean images) | light=day | 0.3333 | 0.0000 | -0.3333 | -100.0% | lower | 36 |
| False alarm in top-B (clean images in top-B / clean images) | light=dusk | 0.2500 | 0.0000 | -0.2500 | -100.0% | lower | 16 |
| False alarm in top-B (clean images in top-B / clean images) | light=night | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 4 |
| Runtime / 100 items (s) | all | 0.2919 | 0.3678 | | | lower | |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: `Defect Recall@B` = (Số ảnh lỗi thật trong top-B) / (Tổng số ảnh lỗi thật trong split), đơn vị đánh giá: image. Numerator = 20, Denominator = 42. Kèm `Precision@B` = 20/20 = 1.0.
- Threshold / budget B / K và lúc chốt: B=20, chốt lúc 16:30 ngày 2026-11-14 trong `reports/metric_contract.md`.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: Khoảng tin cậy Wilson Score 95% CI cho Precision đạt [0.838, 1.000], cho Recall đạt [0.334, 0.623].
- Lệnh evaluate chính xác: `python -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --out reports/metrics_poc.json`

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| light=day | 36 | 0.4074 | 0.5185 | Recall tăng, False alarm giảm từ 33.3% về 0% |
| light=dusk | 16 | 0.3333 | 0.4167 | Loại bỏ hoàn toàn cảnh báo giả (0%) |
| light=night | 4 | 0.3333 | 0.3333 | Bảo vệ ảnh đêm hợp lệ không bị phạt oan |
| defect=compression | 8 | 0.2500 | 0.8750 | Tăng vọt nhờ bộ lọc vi phân biên khối 8x8 |
| defect=dark | 6 | 0.8333 | 0.8333 | Nhận diện chính xác thiếu sáng cực đoan |

- Failure case 1 (ảnh/metadata + root cause): `img_01_3` — Ảnh chụp đêm có lóa đèn nhẹ kết hợp rung tay nhỏ. Do độ sáng đèn lấn át vi sai tối, thuật toán nhận diện lỗi chính là compression thay vì glare nhẹ, tuy nhiên điểm tổng hợp vẫn đưa ảnh vào hàng đợi duyệt thành công.
- Failure case 2: `img_17_2` — Lóa sáng cục bộ diện hẹp tại vùng biển số xe. Baseline bỏ sót hoàn toàn (độ sắc nét toàn cục cao), PoC đã bắt được nhờ lưới phân tích bão hòa cục bộ.
- Latency / compute (máy, CPU, ms/item): Intel Core CPU Windows, ~0.35 ms/item (0.3678s / 100 items), đáp ứng hoàn hảo thời gian thực.

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, B=20, ưu tiên theo điểm rủi ro `score` từ cao xuống thấp.
- Cách override + audit log (`out/audit_log.jsonl`): Reviewer nhập thẩm định (`approve/reject`) vào `out/poc/review_queue_reviewed.csv`, pipeline áp dụng ghi đè và ghi nhật ký kiểm toán có đóng dấu thời gian vào `audit_log.jsonl`.
- Decision policy + `reason_code` + owner: Ngưỡng mẻ dữ liệu: Nếu >35 ảnh lỗi $\to$ `REWORK` (`HIGH_DEFECT_RATE`); ngược lại $\to$ `GO` (`QUALITY_GATE_PASSED`). Người ký duyệt: `Dang Thu Thuy (Data Lead)`.
- Khi nào HOLD/REWORK thay vì tự động release: Khi tỷ lệ ảnh lỗi trong mẻ vượt quá ngưỡng cho phép (trên 35% mẻ hỏng), hệ thống dừng tự động phát hành và yêu cầu chụp lại.

## 08 · Reproduce & tests

```bash
# 1. Chạy Baseline:
python -m src.main --pipeline src.baseline --output out/baseline --run-name baseline --offline --seed 42
# 2. Chạy PoC:
python -m src.main --output out/poc --run-name poc --offline --seed 42
# 3. Đánh giá & So sánh:
python -m src.evaluate --track t02 --gt fixtures/t02_raw_qc/dev_gt_internal.csv --split dev --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
# 4. Kiểm thử độ tin cậy:
python -m unittest tests/test_t02_group.py
```

- Output của `pytest -q` (hoặc `python -m unittest`): `Ran 3 tests in 0.039s - OK (100% PASS)`
- Máy / CPU / OS / Python: Windows 11 · Python 3.11.9 · git sha: ad9e707

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: Dữ liệu sử dụng trong bài lab là dữ liệu synthetic 100% tuân thủ giấy phép CC0-1.0, không chứa khuôn mặt hoặc biển số người thật, không xâm phạm quyền riêng tư.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: Khi mở rộng quy mô dữ liệu lên $10\times$ (hàng nghìn ảnh), các hiện tượng thời tiết phức tạp hơn như tuyết rơi hoặc phản chiếu mặt đường ướt sau mưa có thể tạo ra các vùng sáng giả lóa. Cần bổ sung lọc hình thái học (morphological operations).
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: Mọi quy trình gắn cờ và loại bỏ dữ liệu chỉ đóng vai trò hỗ trợ kỹ thuật; quyết định pháp lý sau cùng thuộc về DPO và bộ phận Pháp chế.
- Kế hoạch cải tiến: Mở rộng bộ phân loại đa nhãn học sâu nhẹ (MobileNetV4 / ShuffleNet) chạy offline để nhận diện đồng thời nhiều lỗi phức tạp trên 1 khung hình.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Đặng Thu Thúy | thuythu0312 <thuythu0965@gmail.com> | Full Project Owner & Lead / Core Algorithm / Review / QA | ad9e707 | Có |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://acdc.vision.ee.ethz.ch/ | 2026-11-14 | Tập dữ liệu ACDC nghiên cứu độ suy giảm thị giác trong điều kiện sương mù, mưa tuyết và ban đêm |
| https://www.iso.org/standard/81613.html | 2026-11-14 | Tiêu chuẩn quốc tế ISO/IEC 5259 về quản trị và bảo đảm chất lượng dữ liệu huấn luyện AI |
| https://ieeexplore.ieee.org/document/1044431 | 2026-11-14 | Kỹ thuật phát hiện và ước lượng hiệu ứng vỡ hạt nén biên khối JPEG không cần ảnh gốc |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
