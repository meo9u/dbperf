# Báo cáo kết quả benchmark class 1: MySQL (InnoDB) và MongoDB (WiredTiger)

Ngày chạy: 2026-11-25. Phạm vi: 5 truy vấn class 1 (quét nhiều dữ liệu) ở trạng thái baseline, sau khi thêm index, và sau khi viết lại truy vấn. Class 2 (k6, tải đồng thời) chưa chạy.

Số liệu gốc: `benchmark/results/{baseline,idx,optimized,rollback_check}/`, bảng tổng hợp `benchmark/results/comparison.tsv`.

---

## 1. Tóm tắt

| Query | Nghiệp vụ | MySQL (ms): baseline → tối ưu | MongoDB (ms): baseline → tối ưu |
|---|---|---|---|
| q1 | Doanh thu theo tháng | 412 → 342 (1,2x) | 539 → 560 (1,0x) |
| q2 | Top 20 SKU năm 2019 | 4194 → 1608 (2,6x) | 1456 → 1486 (1,0x) |
| q3 | Doanh thu theo danh mục | 9079 → 2744 (3,3x) | 2201 → 2150 (1,0x) |
| q4 | Top 20 khách hàng | 1833 → 197 (9,3x) | 1306 → 1099 (1,2x) |
| q5 | Tồn kho thấp theo kho | 197 → 19 (10x) | 272 → 173 (1,6x) |

p50 của 11 lần chạy đo. "Baseline" ở đây là baseline **sau `ANALYZE TABLE`** (`results/baseline_analyzed/`), mốc công bằng vì thống kê của MySQL đã được làm mới. Baseline gốc (thống kê cũ từ lúc nạp dữ liệu, `results/baseline/`) chỉ khác ở MySQL q5 (475 ms), xem mục 8.1.

Các kết luận chính:

1. **Ở baseline, MongoDB nhanh hơn MySQL ở 3/5 query** (q2, q3, q4), vì đơn hàng và dòng hàng được nhúng chung một document nên không phải join. MySQL nhanh hơn ở q1 (quét một bảng, không có join) và q5 (197 so với 272 ms, sau khi thống kê được làm mới).
2. **Sau tối ưu, MySQL nhanh hơn MongoDB ở 3/5 query** (q1, q4, q5); ở q2 và q3 MongoDB vẫn nhỉnh hơn (1,1x và 1,3x). Tối ưu có hiệu quả lớn với MySQL vì chi phí của nó nằm ở số lần tra cứu index và thứ tự join, cả hai đều can thiệp được. Chi phí của MongoDB nằm ở việc duyệt và gom nhóm hàng triệu dòng hàng, và index không giảm được phần đó.
3. **Thêm index có thể làm chậm đi.** `status = 'delivered'` chiếm 96% đơn, nên index bắt đầu bằng `status` hầu như không lọc được gì. Ở bước chỉ thêm index, MongoDB q1–q3 chậm hơn tới 1,8x và MySQL q2, q3 chậm hơn 1,26x.
4. **Kết quả truy vấn không đổi** ở mọi bước (mọi `result.tsv` giống baseline, và giống nhau giữa hai DB).

---

## 2. Môi trường và phương pháp đo

| Mục | Giá trị |
|---|---|
| Dữ liệu | bộ `bigdata`: 1.000.000 đơn, ~3,1 triệu dòng hàng, 50.000 khách, 20.000 SKU, 321.410 dòng tồn kho |
| Phiên bản | MySQL 9.7.2, MongoDB 8.0.32 (single-node replica set `rs0`) |
| Tài nguyên mỗi DB | 2 CPU, giới hạn RAM 4 GB |
| Cache | InnoDB buffer pool 1536 MB; WiredTiger cache 1536 MB (đã cân bằng, mặc định ban đầu là 128 MB so với 1536 MB) |
| Số lần chạy | 1 lần đầu (ghi riêng) + 11 lần đo, lấy p50 và p95 |
| Cách tính thời gian | trong cùng một phiên DB, không tính thời gian khởi động tiến trình: MySQL đọc `TIMER_WAIT` từ `performance_schema`, MongoDB dùng `performance.now()` quanh truy vấn |
| Cổng kiểm tra | kết quả hai DB phải giống hệt (`diff` rỗng) trước khi ghi số liệu; bước tối ưu còn phải giống baseline |

Công cụ: `benchmark/run_class1.py` (đo), `benchmark/optimization.py` (áp dụng và hoàn nguyên index), `benchmark/compare.py` (so sánh).

Ba bước đo cho phép tách được ảnh hưởng của từng thay đổi:

| Bước | Schema | Truy vấn |
|---|---|---|
| `baseline` | chỉ index bắt buộc (PK, FK, unique); thống kê MySQL cũ từ lúc nạp dữ liệu | `queries/*/baseline/` |
| `baseline_analyzed` | như `baseline`, nhưng đã chạy `ANALYZE TABLE` (mốc so sánh công bằng) | `queries/*/baseline/` |
| `idx` | thêm index | giữ nguyên truy vấn baseline |
| `optimized` | thêm index | truy vấn viết lại (`queries/*/optimized/`) |

---

## 3. Cơ chế hoạt động cần biết

### 3.1 InnoDB (MySQL)

- **Clustered index.** Bảng chính là một cây B+ theo khóa chính. Mỗi dòng nằm ở lá của cây này. Vì vậy quét toàn bảng nghĩa là duyệt tuần tự các lá.
- **Secondary index.** Lá của index phụ chứa giá trị cột index cộng khóa chính. Muốn lấy cột khác phải đi thêm một lượt xuống cây chính (tra cứu hai bước). Nếu index đã chứa mọi cột truy vấn cần thì không phải tra cứu nữa. Đó là **covering index** và plan ghi `Covering index ...`.
- **Index FK tự sinh.** InnoDB tạo index cho mọi cột khóa ngoại. Đây là lý do `orders.customer_id` đã có index từ đầu ở MySQL, còn MongoDB thì không.
- **Join.** Cách chính là *nested loop*: với mỗi dòng của bảng ngoài, tra cứu bảng trong bằng index. Chi phí ≈ số dòng ngoài × chi phí một lần tra. Với vài triệu dòng, mỗi lần tra chỉ ~1 µs nhưng cộng lại thành giây.
- **GROUP BY.** Nếu dữ liệu không đến theo thứ tự nhóm, MySQL tạo bảng tạm trong bộ nhớ, thêm từng dòng vào để cộng dồn (`Aggregate using temporary table`). Nếu index trả dữ liệu đã sắp theo cột nhóm thì gom nhóm theo luồng, không cần bảng tạm (`Group aggregate`).
- **Optimizer theo chi phí.** MySQL ước lượng số dòng từ thống kê index (số giá trị phân biệt, mẫu ngẫu nhiên) rồi chọn plan rẻ nhất theo mô hình chi phí. Nếu thống kê hoặc mô hình lệch, plan có thể sai. `EXPLAIN ANALYZE` cho thấy cả số dòng ước lượng (`rows=`) lẫn thực tế (`actual ... rows=`).

### 3.2 WiredTiger (MongoDB)

- **Collection là một cây B+ theo `RecordId`** (mã nội bộ). Document nằm ở lá. Quét collection (`COLLSCAN`) là duyệt tuần tự các lá.
- **Index** ánh xạ giá trị khóa đến `RecordId`. Để lấy phần còn lại của document, cần một bước `FETCH`: tra `RecordId` trong cây của collection. Nếu index chứa đủ trường thì dùng **covered query** (`PROJECTION_COVERED`) và không phải đọc document.
- **Mô hình nhúng.** Mỗi đơn chứa luôn mảng `lines[]`. Đọc một đơn là có đủ các dòng hàng, không cần join. Cái giá phải trả: mỗi document to hơn, và truy vấn trên từng dòng hàng phải `$unwind` mảng ra.
- **Aggregation pipeline.** Chạy tuần tự các giai đoạn: `$match` → `$unwind` → `$group` → `$lookup`. `$group` giữ bảng băm trong bộ nhớ. `$lookup` là phép join và dùng index ở collection bị tra nếu có.
- **Chọn plan.** MongoDB không giữ thống kê phân phối giá trị như histogram. Nó chạy thử ngắn các plan ứng viên (kể cả plan dùng index) và chọn plan nhỉnh hơn trong khoảng thử đó.

### 3.3 Điểm chung quan trọng: độ chọn lọc (selectivity)

Index chỉ giúp khi nó loại được phần lớn dữ liệu. Ở đây 960.500 trong 1.000.000 đơn (96%) có `status = 'delivered'`, nên điều kiện này không loại gì cả. Index bắt đầu bằng `status` chỉ có ích khi nó là **covering** (tránh đọc dòng) hoặc cho **thứ tự** sẵn có (ví dụ theo `created_at` hay `customer_id` bên trong `status`).

---

## 4. Baseline: vì sao mỗi query nhanh hoặc chậm

Cả hai DB đều quét toàn bộ 1.000.000 đơn ở q1–q4 (MySQL `Table scan on orders`, MongoDB `COLLSCAN`). Khác biệt nằm ở những gì xảy ra sau đó.

### q1: Doanh thu theo tháng (MySQL 431 ms, MongoDB 553 ms)

- Chỉ đọc một bảng, không có join. Cả hai quét 1M đơn, lọc `delivered`, gom theo tháng.
- MySQL quét ~150 ms, lọc xong ở ~245 ms, gom nhóm bằng bảng tạm đến 525 ms (số `EXPLAIN ANALYZE` có chi phí đo đạc nên cao hơn số p50).
- MongoDB phải đọc cả document đơn (lớn vì có `lines[]`, `payments[]`, `shipping`) chỉ để lấy ba trường. MySQL đọc dòng `orders` hẹp hơn nhiều: bảng `orders` chỉ 119 MB, trong khi toàn bộ dữ liệu MongoDB là ~876 MB chưa nén (nén còn ~259 MB trên đĩa; con số đo lúc nạp dữ liệu).
- Nên MySQL nhanh hơn một chút. Đây là query duy nhất mà mô hình nhúng không có lợi.

### q2: Top 20 SKU năm 2019 (MySQL 4240 ms, MongoDB 1498 ms)

- **MySQL:** lọc 487.220 đơn năm 2019 → tra `order_detail` theo `order_id` (3,12 dòng mỗi đơn, 1,52 triệu dòng) → tra bảng `sku` theo khóa chính cho **từng** dòng (1,52 triệu lần) → mới gom nhóm. Riêng các lần tra `sku` và `order_detail` đã mất khoảng 3 s. Phần gom nhóm xảy ra *sau* join nên nó phải xử lý 1,52 triệu dòng đã nối.
- **MongoDB:** đọc 1M document, lọc năm 2019, `$unwind` ra 1,52 triệu dòng hàng, gom nhóm theo `sku_id` (còn ~19.000 nhóm), rồi `$lookup` sang `products` chỉ **19.000 lần** (một lần mỗi nhóm). Vì gom nhóm xảy ra trước `$lookup`, join rất rẻ.
- Chênh lệch 2,8x đến từ chỗ MySQL join trước, gom sau, còn MongoDB gom trước, join sau.

### q3: Doanh thu theo danh mục (MySQL 9039 ms, MongoDB 2131 ms)

- **MySQL:** 960.500 đơn → 2,99 triệu dòng hàng → mỗi dòng tra `sku`, `product`, `category`. Từ `EXPLAIN ANALYZE`: 2,99 triệu lần tra `sku` (~0,81 µs mỗi lần), 2,99 triệu lần tra `product` (~0,6 µs), 2,99 triệu lần tra `category` (~0,3 µs). Cộng với ~0,96 triệu lần tra `order_detail`, tổng khoảng 10 triệu lần tra index. Đây là bài toán điển hình của nested loop: cộng dồn hàng triệu thao tác nhỏ.
- **MongoDB:** `$unwind` 2,99 triệu dòng, gom theo `sku_id`, rồi `$lookup` 19.344 lần sang `products` và 19 lần sang `categories`. Phần tốn nhất là đọc, mở mảng và gom 2,99 triệu dòng.
- Chênh 4,2x, lớn nhất trong các query, vì q3 có nhiều bước join nhất.

### q4: Top 20 khách hàng (MySQL 1981 ms, MongoDB 1191 ms)

- **MySQL:** quét 1M đơn, lọc, rồi tra `customer` bằng khóa chính 960.500 lần (~0,77 µs mỗi lần), gom nhóm vào bảng tạm 50.000 nhóm.
- **MongoDB:** gom theo `customer_id` ngay (50.000 nhóm), sau đó chỉ `$lookup` 50.000 lần sang `customers`. Join xảy ra sau gom nhóm nên ít lần hơn gần 20 lần.
- Cùng nguyên lý với q2: gom nhóm trước, join sau thì rẻ hơn.

### q5: Tồn kho thấp theo kho (MySQL 475 ms, MongoDB 254 ms)

- Điều kiện `quantity_on_hand - quantity_reserved <= 25` là một **biểu thức**, nên không index nào dùng được: cả hai đều phải đọc toàn bộ 321.410 dòng tồn kho.
- **MySQL (baseline):** optimizer chọn thứ tự join `warehouse × (product ⋈ sku)` → 20 kho × 20.000 SKU = 400.000 cặp, rồi tra `inventory` cho từng cặp (400.000 lần) và lọc, trong khi chỉ 4.037 dòng thỏa. Plan này đắt vì tạo ra 400.000 cặp rồi bỏ gần hết.
- **MongoDB:** đọc `inventory` một lần, lọc còn 4.037 dòng rồi mới `$lookup` 4.037 lần.
- **Sau `ANALYZE`** MySQL đổi plan: đi từ `warehouse` (20 dòng), mỗi kho quét ~16.000 dòng `inventory` qua `fk_inventory_warehouse` rồi lọc biểu thức, xong mới tra `sku` và `product` cho 4.037 dòng thỏa. Còn 197 ms, nhanh hơn MongoDB (272 ms). Con số 475 ms ở trên là của plan do thống kê cũ.

---

## 5. Tối ưu đã áp dụng

### 5.1 Index và cột bổ sung (`schema/*/optimization/`)

| Đối tượng | MySQL | MongoDB |
|---|---|---|
| `orders` (q1, q2) | `(status, created_at, total_amount)` | `{status, created_at, total_amount}` |
| `orders` (q4) | `(status, customer_id, total_amount)` | `{status, customer_id, total_amount}` |
| `order_detail` (q2, q3) | `(order_id, sku_id, quantity, line_total)` covering | không có tương đương (dòng hàng nằm trong `orders.lines[]`) |
| `inventory` (q5) | cột sinh `quantity_available` (STORED) + index | trường `quantity_available` lưu sẵn + index (phải sửa validator) |

### 5.2 Viết lại truy vấn (`queries/*/optimized/`)

- **MySQL q2, q3:** gom `order_detail` theo `sku_id` trong bảng dẫn xuất trước (còn ~19.000 nhóm), rồi mới join `sku`, `product`, `category`. Dùng `JOIN_ORDER(o, d)` và `USE INDEX` để buộc thứ tự và index đúng.
- **MySQL q4:** gom `orders` theo `customer_id` trước, rồi join `customer`.
- **MySQL q5:** lọc trực tiếp trên cột `quantity_available` có index.
- **MongoDB q1, q2, q3:** thêm `hint: {$natural: 1}` để ép quét collection (lý do ở mục 6.2).
- **MongoDB q5:** lọc theo trường `quantity_available` đã lưu.
- MySQL q1 và MongoDB q4 giữ nguyên truy vấn.

---

## 6. Sau tối ưu: vì sao nhanh hơn, vì sao chậm hơn

### 6.1 Bảng đầy đủ (p50, ms)

| Query | DB | Baseline gốc | Baseline sau ANALYZE | + index | + viết lại | Tăng tốc so với sau ANALYZE |
|---|---|---|---|---|---|---|
| q1 | MySQL | 431 | 412 | 337 | 342 | 1,21x |
| q1 | MongoDB | 553 | 539 | 713 | 560 | 0,96x |
| q2 | MySQL | 4240 | 4194 | 5340 | 1608 | 2,61x |
| q2 | MongoDB | 1498 | 1456 | 2158 | 1486 | 0,98x |
| q3 | MySQL | 9039 | 9079 | 11432 | 2744 | 3,31x |
| q3 | MongoDB | 2131 | 2201 | 3927 | 2150 | 1,02x |
| q4 | MySQL | 1981 | 1833 | 624 | 197 | 9,31x |
| q4 | MongoDB | 1191 | 1306 | 1102 | 1099 | 1,19x |
| q5 | MySQL | 475 | 197 | 21 | 19 | 10,2x |
| q5 | MongoDB | 254 | 272 | 271 | 173 | 1,57x |

Độ nhiễu giữa các đợt chạy cùng cấu hình: MongoDB q4 baseline là 1191, 1246 và 1306 ms ở ba đợt (±5–10%), q3 là 2131, 2182, 2201 ms. Vì vậy mức "1,08x–1,19x" của MongoDB q4 nằm trong vùng nhiễu, và chỉ các mức tăng từ khoảng 1,3x trở lên mới đáng tin.

Số tài liệu/dòng phải đọc (từ plan): MongoDB q4 giảm từ 1.000.000 xuống **0** tài liệu đọc từ collection cho giai đoạn lọc (chỉ 50.000 document `customers` được tra ở bước `$lookup`); MongoDB q5 giảm từ 321.410 xuống 4.037.

### 6.2 Những trường hợp nhanh hơn

**MySQL q4 (10x): covering index cho thứ tự gom nhóm sẵn.**
Index `(status, customer_id, total_amount)` chứa đủ ba cột cần, nên không phải đọc dòng `orders`. Trong cùng `status`, các mục đã sắp theo `customer_id`, nên MySQL gom nhóm theo luồng (`Group aggregate`, ~170 ms cho 960.500 mục) thay vì bảng tạm. Viết lại thêm một bước: gom 960.500 dòng thành 50.000 nhóm *trước*, rồi mới join `customer` (50.000 lần tra thay vì 960.500). Số lần tra giảm gần 20 lần.

**MySQL q5 (10x so với baseline sau `ANALYZE`): biểu thức biến thành khoảng quét trên index.**
Cột sinh `quantity_available` được lưu và có index nên điều kiện `<= 25` chuyển thành một `Index range scan` trên 4.037 mục. MySQL đi từ `inventory` đã lọc (4.037 dòng) rồi mới tra `warehouse`, `sku`, `product` (4.037 lần mỗi bảng). Không có index thì phải đọc toàn bộ 321.410 dòng `inventory` và tính biểu thức cho từng dòng (baseline sau `ANALYZE`: duyệt từng kho theo `fk_inventory_warehouse`, ~16.000 dòng mỗi kho). Baseline gốc còn tệ hơn vì thống kê cũ (mục 8.1).

**MySQL q2 (2,6x) và q3 (3,3x): gom nhóm trước, join sau.**
Viết lại buộc MySQL đọc `order_detail` qua covering index theo `order_id` (không đụng dòng gốc), gom ngay theo `sku_id` còn ~19.000 nhóm, rồi mới tra `sku` (và `product`, `category`) cho ~19.000 nhóm thay vì 1,5–3 triệu dòng. Cùng một phép tính, nhưng số lần tra giảm khoảng 100–150 lần. Phần còn lại (theo `EXPLAIN ANALYZE`: ~1,3–1,8 s ở q2, ~2,2–3,1 s ở q3, đã gồm chi phí đo) là đọc và gom 1,5–3 triệu dòng hàng, không thể bỏ nếu không tiền tổng hợp.

**MySQL q1 (1,26x): covering index nhỏ hơn bảng.**
Plan chuyển từ `Table scan on orders` sang `Covering index lookup ... idx_orders_status_created_total`, đọc 960.500 mục index (rộng ba cột) thay vì 1M dòng đầy đủ. Bảng tạm để gom theo tháng vẫn còn nên mức tăng khiêm tốn.

**MongoDB q5 (1,46x).**
Lọc trực tiếp trên trường có index nên chỉ 4.037 document `inventory` được đọc thay vì 321.410. Phần còn lại là hai lần `$lookup` (4.037 lần mỗi lần) và sắp xếp, nên mức tăng không lớn.

**MongoDB q4 (1,08x).**
Index covering giúp giai đoạn lọc không đọc document nào, nhưng `$group` vẫn phải băm 960.500 mục vào 50.000 nhóm. MongoDB không có gom nhóm theo luồng trên index sắp thứ tự như MySQL, nên phần lớn thời gian vẫn còn.

### 6.3 Những trường hợp chậm hơn (và vì sao)

**MongoDB q1 (553 → 713 ms), q2 (1498 → 2158 ms), q3 (2131 → 3927 ms) ở bước chỉ thêm index.**
Sau khi có index bắt đầu bằng `status`, planner chọn dùng nó:

- q1: dùng covered index, 0 document đọc, 960.500 khóa. Vẫn chậm hơn `COLLSCAN` (713 so với 563 ms đo lại cùng điều kiện).
- q2, q3: dùng index rồi `FETCH` 487.220 (q2) hoặc 960.500 (q3) document.

Giải thích (suy ra từ plan và số đo, chưa đo riêng từng bước):

1. Index trên `status` không loại được gì (96% khớp), nên nó không giảm khối lượng, chỉ thêm việc.
2. `FETCH` là tra `RecordId` trong cây collection, gần như từng điểm một. Với gần 1 triệu lần, tổng chi phí lớn hơn việc đi tuần tự qua các lá của `COLLSCAN`.
3. Với covered query ở q1, mỗi khóa index phải được giải mã từ trang B-tree (gồm chuỗi, ngày, số thập phân), và 960.500 khóa này không rẻ hơn việc đọc tuần tự các document.
4. MongoDB không có thống kê phân phối nên không biết `delivered` chiếm 96%; thử ngắn không lộ ra chi phí tích lũy này.

Cách xử lý: `hint: {$natural: 1}` buộc `COLLSCAN`. Đã đo lại riêng: q1 713 → 563 ms, q2 1728 → 1068 ms, q3 3723 → 1950 ms. Kết quả: bước `optimized` đưa MongoDB q1–q3 về bằng baseline, không nhanh hơn. Kết luận trung thực: **với q1–q3 không có index nào giúp MongoDB**, vì chi phí nằm ở việc duyệt và gom nhóm hàng triệu dòng hàng.

**MySQL q2 (4240 → 5340 ms) và q3 (9039 → 11432 ms) ở bước chỉ thêm index.**
Index thêm vào không giúp mà làm optimizer chọn plan khác, tệ hơn:

- q2: optimizer chọn `idx_orders_status_customer_total` (chỉ lọc `status`, ước lượng 496.281 dòng) rồi lọc `created_at` sau, nên đọc 960.500 mục thay vì khoảng quét 487.220 mục trên `idx_orders_status_created_total`. Các mục đó lại không chứa `created_at`, nên còn phải tra dòng gốc.
- q3: optimizer đổi thứ tự join: đi từ `sku` (20.000) → `order_detail` theo `sku_id` (~156 dòng mỗi SKU) → tra `orders` theo khóa chính 3,12 triệu lần để kiểm tra `delivered`. Nhiều lần tra hơn plan cũ.
- Dấu hiệu của ước lượng sai: plan ghi `rows=496281` cho `status='delivered'` trong khi thực tế là 960.500 (lệch gần 2 lần).

**Thí nghiệm histogram (`results/idx_histogram/`).** Để kiểm tra xem ước lượng sai có sửa được bằng thống kê không, mình tạo histogram 100 bucket trên `orders.status` và `orders.customer_id` (`ANALYZE TABLE ... UPDATE HISTOGRAM`) rồi chạy lại q2, q3 bằng truy vấn baseline. Kết quả: **không đổi gì**. Ước lượng vẫn là `rows=495903` (thực tế 960.500), q2 vẫn chọn `idx_orders_status_customer_total`, q3 vẫn đi từ `sku` (q2 6907 ms, q3 11172 ms, không tốt hơn bước `idx`). Lý do (theo tài liệu MySQL, mình chưa kiểm chứng riêng): với cột đã có index, optimizer ước lượng điều kiện `status = 'delivered'` bằng index dive trên chính index chứ không dùng histogram; histogram chỉ có tác dụng với cột không có index. Vậy giả thuyết "thống kê không đủ" bị bác bỏ cho trường hợp này; nguyên nhân thật là sai số của ước lượng index dive ở khoảng giá trị rất lớn (96% bảng), và cách xử lý thực tế vẫn là gợi ý (`JOIN_ORDER`, `USE INDEX`) và viết lại truy vấn.

Cách xử lý: viết lại truy vấn buộc thứ tự join (`JOIN_ORDER`) và index (`USE INDEX`), và gom nhóm trước. Đây là lý do bước `optimized` mới cho hiệu quả, trong khi `idx` một mình thì không.

### 6.4 Chi phí đĩa của index (MB)

| | Baseline | Sau tối ưu | Tăng |
|---|---|---|---|
| MySQL `orders` (index) | 19,5 | 66,6 | +47,1 |
| MySQL `order_detail` (index) | 172,8 | 213,9 | +41,1 |
| MySQL `inventory` (index) | 12,0 | 20,5 | +8,5 |
| MongoDB `orders` (index) | 25,8 | 72,6 | +46,8 |
| MongoDB `inventory` (index) | 24,2 | 25,9 | +1,7 |

Kích thước dữ liệu trên đĩa: MySQL `orders` 118,6 MB, `order_detail` 159,7 MB; MongoDB `orders` 237 MB (`storageSize`, đã nén).
Mỗi index ghi thêm chi phí khi `INSERT`/`UPDATE` (mỗi đơn mới phải cập nhật thêm hai index trên `orders`, và mỗi dòng hàng một index trên `order_detail`), nhưng **chưa đo** vì chưa có kịch bản ghi (checkout) của class 2.

---

## 7. So sánh tổng thể sau tối ưu

| Query | MySQL (ms) | MongoDB (ms) | Nhanh hơn |
|---|---|---|---|
| q1 | 342 | 560 | MySQL 1,6x |
| q2 | 1608 | 1486 | MongoDB 1,08x |
| q3 | 2744 | 2150 | MongoDB 1,28x |
| q4 | 197 | 1099 | MySQL 5,6x |
| q5 | 19 | 173 | MySQL 9x |

Nhận xét:

- **Mô hình nhúng của MongoDB thắng khi cần gom nhiều dòng hàng đã nằm sẵn trong đơn** (q2, q3), nhưng phần lợi thế này mỏng đi nhiều sau khi MySQL được viết lại (từ 2,8x và 4,2x còn 1,1x và 1,3x).
- **MySQL thắng khi truy vấn có thể phục vụ hoàn toàn từ index** (q1, q4, q5): covering index, gom nhóm theo luồng và khoảng quét chính xác là điểm mạnh của InnoDB, còn MongoDB tương đương chỉ ở mức covered scan và băm trong bộ nhớ.
- **MongoDB gần như không được tối ưu thêm bằng index ở các truy vấn quét** vì chi phí nằm ở dữ liệu cần duyệt chứ không phải ở cách tìm. Hướng cải thiện còn lại là tiền tổng hợp (bảng tóm tắt hoặc `$merge`), chưa làm vì đánh đổi độ cũ của dữ liệu.

---

## 8. Hạn chế và độ tin cậy

1. **Thống kê MySQL và baseline.** Baseline gốc của MySQL q5 (475 ms) dùng thống kê cũ từ lúc nạp dữ liệu. Sau `ANALYZE TABLE`, optimizer đổi thứ tự join và q5 còn 197 ms mà chưa cần index (đã đo lại ở `results/baseline_analyzed/`). Vì thế mọi mức tăng tốc trong báo cáo được tính theo baseline sau `ANALYZE`. Với q5 điều này giảm mức tăng từ 24x xuống 10x. Bốn query còn lại gần như không đổi (±8%).
2. **Tái lập.** Sau rollback, các query khác tái hiện baseline trong khoảng ±8% (`results/rollback_check/`); danh sách index khớp baseline ban đầu.
3. **Thời gian đo trong phiên DB**, không gồm truyền kết quả qua mạng và khởi động tiến trình. "Lần chạy đầu" không phải cache lạnh thật vì cache đã ấm từ các lần chạy trước.
4. **Quy mô dữ liệu** (1M đơn) vẫn nhỏ hơn mục tiêu của đề (10M+ đơn). Dữ liệu vừa trong cache 1536 MB, nên chênh lệch do I/O đĩa chưa lộ ra.
5. **Giả định "doanh thu = chỉ đơn `delivered`"** là giả định của đồ án.
6. **Dữ liệu có một check FAIL** (`status_payment_consistency`, 562 dòng) giống hệt ở hai DB, nên không làm lệch so sánh.
7. Các giải thích về *tại sao* (mục 6.3) được suy ra từ plan và số đo; chưa có thí nghiệm riêng tách từng nguyên nhân, trừ việc đo lại `$natural` so với index đã nêu.
8. Một đợt chạy mỗi cấu hình trên một máy, 11 lần đo; p95 sát p50 (trong ~5–10%) nên độ ổn định tốt, nhưng chưa lặp lại ở nhiều đợt.

---

## 9. Việc tiếp theo

1. (Đã làm) Đo lại baseline sau `ANALYZE TABLE` (mục 8.1).
2. (Đã làm) Thử histogram: không thay đổi plan (mục 6.3).
3. Quyết định có làm bước tiền tổng hợp cho q1, q3 hay chỉ đưa vào khuyến nghị.
4. Class 2 (k6): tìm kiếm sản phẩm và checkout, gồm đo chi phí ghi của các index mới.

## 10. Chạy lại

```
python3 benchmark/run_class1.py --phase baseline --db both
# mốc công bằng: ANALYZE TABLE trên mọi bảng MySQL rồi chạy lại baseline
python3 benchmark/run_class1.py --phase baseline_analyzed --query-phase baseline --db both
python3 benchmark/optimization.py apply
python3 benchmark/run_class1.py --phase idx --query-phase baseline --db both
python3 benchmark/run_class1.py --phase optimized --db both
python3 benchmark/compare.py
python3 benchmark/optimization.py rollback     # trở về baseline
```
