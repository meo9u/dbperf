# Báo cáo class 2: đặt hàng (`checkout`, luồng ghi)

Ngày chạy: 2026-11-25. Phạm vi: nghiệp vụ đặt hàng bằng transaction đa bảng (MySQL) / đa document (MongoDB) ở 4, 8, 16, 32 VU; so sánh baseline, biến thể tối ưu và chi phí ghi của các index đã thêm ở class 1 và tìm kiếm. Báo cáo tìm kiếm: `docs/bao-cao-ket-qua-class2-search.md`; class 1: `docs/bao-cao-ket-qua-class1.md`.

Số liệu gốc: `benchmark/results/<phase>/load/` với `<phase>` là `baseline_checkout`, `baseline_checkout_r2`, `optimized_checkout`, `indexed_checkout`, `harness_interpolate`; bảng gộp `benchmark/results/load_comparison.checkout.tsv`.

## 1. Tóm tắt

Thông lượng (checkout hoàn thành mỗi giây) và p95 (ms), baseline hai lần chạy:

| VU | MySQL TPS | MySQL p95 | MongoDB TPS | MongoDB p95 |
|---|---|---|---|---|
| 4 | 513 / 643 | 9,7 / 8,4 | 1.751 / 1.930 | 3,0 / 2,8 |
| 8 | 576 / 758 | 18,0 / 12,6 | 2.691 / 2.624 | 3,8 / 5,0 |
| 16 | 691 / 772 | 32,0 / 31,2 | 2.700 / 2.688 | 46,8 / 49,4 |
| 32 | 790 / 800 | 58,8 / 69,6 | 2.680 / 2.672 | 67,7 / 70,2 |

1. **MongoDB cho thông lượng cao hơn MySQL khoảng 3,4 lần ở 32 VU** (2.680 so với 790–800) và bão hòa sớm (từ 8 VU); MySQL còn tăng dần khi thêm VU. Về p95 ở 32 VU hai bên gần nhau (~68 ms so với ~59–70 ms), còn p50 khác xa (MongoDB ~4 ms, MySQL ~35–38 ms).
2. **Không có lỗi, không mất ghi**: ở mọi mức tải, số đơn mới đúng bằng số checkout thành công, và các kiểm tra logic của seed chỉ còn 562 vi phạm đã có sẵn trong dữ liệu. Sau cùng một dãy 40 checkout, nội dung đơn của hai DB giống hệt nhau (cùng dấu vân tay) và 232 aggregate nghiệp vụ trùng khớp.
3. **Tranh chấp khóa khác bản chất**: MySQL chờ khóa (không có giao dịch nào bị hủy, 0 deadlock trong 23–36 nghìn checkout mỗi mức); MongoDB hủy giao dịch ngay khi xung đột (`WriteConflict`) và ứng dụng phải thử lại, tỉ lệ thử lại tăng theo tải (0,0% ở 4 VU lên 0,7% ở 32 VU; 1–2 checkout ở 32 VU hết 3 lượt thử).
4. **Tối ưu thứ tự khóa + ít lượt gọi hơn không cho khác biệt đo được** ở cả hai DB (nằm trong vùng nhiễu).
5. **Chi phí ghi của các index đã thêm:** MongoDB giảm 20–30% thông lượng khi bão hòa (32 VU: 2.680 → 1.876); MySQL không có khác biệt đo được.

## 2. Cách đo

- Mỗi checkout đặt một đơn `pending` kèm thanh toán `pending`, 1–3 dòng hàng lấy từ **đơn mẫu** thật (`benchmark/scenarios/lib/checkout_templates.json`: 500 đơn "nóng" chứa một trong 200 SKU bán nhiều nhất và 500 đơn "nguội", 2.000 khách), 50% checkout dùng đơn nóng để tạo tranh chấp trên cùng hàng tồn kho. Cùng chuỗi yêu cầu cho hai DB (sinh theo VU và số lần lặp).
- Mỗi checkout là một transaction: tăng `inventory.quantity_reserved` cho từng (SKU, kho), chèn đơn, các dòng hàng và thanh toán. Xung đột (deadlock ở MySQL, `WriteConflict` ở MongoDB) thử lại tối đa 3 lần.
- **Cấu hình độ bền và cô lập: mặc định của từng DB.** MySQL: `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1` (binlog bật), REPEATABLE READ. MongoDB: write concern `majority`, read concern `local`, WiredTiger (single-node replica set). Cache mỗi DB 1536 MB, 2 CPU, 4 GB; k6 2 CPU, 2 GB.
- **Trước mỗi mức tải, dữ liệu được nạp lại từ `seed/data`** (khoảng 40–50 giây mỗi DB, giữ nguyên index, rồi `ANALYZE TABLE`). Sau đó cộng 100.000 vào `quantity_on_hand` của mọi dòng tồn kho ở cả hai DB: không có thao tác này, DB nhanh hơn hoàn thành nhiều checkout hơn và làm cạn các hàng ít tồn kho (tối thiểu 20) sớm hơn (lần chạy thử cho 3.232 lỗi hết hàng ở MongoDB và 7 ở MySQL), nên hai DB không còn làm cùng khối lượng việc. Vì vậy báo cáo này đo thông lượng và tranh chấp khóa, không đo hành vi hết hàng; đường hết hàng đã được kiểm tra riêng (MySQL: `Error 3819 ... Check constraint 'chk_inventory_quantity_reserved' is violated`; MongoDB: `Document failed validation` của validator `inventory`).
- 45 giây mỗi mức, 4/8/16/32 VU; không chạy 64 VU vì k6 đã dùng ~88% CPU khi chạy MongoDB ở 8 VU và ~81% ở 32 VU. Chẩn đoán CPU: DB chạm trần (MySQL 175–190%, MongoDB 195% trên 200%), k6 thấp hơn (MySQL run 26–43%, MongoDB run 61–88%), nên nghẽn nằm ở DB.
- Độ trễ là `iteration_duration` của k6 (một checkout, kể cả các lần thử lại và thời gian chờ giữa các lần).

## 3. Cơ chế

### MySQL (InnoDB)
- Một checkout gồm khoảng 7–10 câu lệnh (`START TRANSACTION`, một `UPDATE inventory` mỗi dòng hàng, `INSERT orders`, một `INSERT order_detail` mỗi dòng, `INSERT payment`, `COMMIT`), mỗi câu là một lượt gọi tới server. `xk6-sql` không có API giao dịch nên các câu lệnh chạy trên cùng một kết nối (đã kiểm tra: kết nối giữ nguyên trong 97.493/97.493 lần với 32 VU).
- **Khóa bi quan:** `UPDATE` khóa hàng tồn kho đến khi `COMMIT`; giao dịch tới sau chờ khóa thay vì bị hủy. Với 1–3 dòng hàng và thứ tự cập nhật theo đơn mẫu, không xảy ra deadlock nào trong các lần chạy, nên khóa chỉ biểu hiện ở độ trễ.
- **Commit bền:** `flush_log_at_trx_commit=1` và `sync_binlog=1` buộc đồng bộ redo log và binlog khi commit. Độ trễ p50 ~6 ms ở 4 VU và thông lượng tăng dần theo số VU (513/643 → 790/800) phù hợp với việc các commit đồng thời dùng chung một lần đồng bộ đĩa (group commit); mình chưa đo riêng thời gian fsync nên đây là suy luận từ hình dạng đường cong. Ở 8–32 VU CPU của MySQL đạt 175–190%.

### MongoDB (WiredTiger)
- Đơn, dòng hàng, thanh toán và địa chỉ giao hàng nằm trong **một document**, nên checkout chỉ cần `updateOne` mỗi dòng hàng, **một** `insert` và commit: ít lượt gọi hơn nhiều so với MySQL (đây là lợi thế của mô hình nhúng).
- **Khóa lạc quan:** hai transaction ghi cùng document đồng thời thì bên sau nhận `WriteConflict` ngay và phải thử lại (đã kiểm tra trực tiếp). Số lần thử lại tăng theo mức tải: 10–22 (4 VU), 69–82 (8 VU), 221–250 (16 VU), 805–807 (32 VU) trên ~120 nghìn checkout; 1–2 checkout mỗi lần chạy ở 32 VU hết 3 lượt thử.
- Thông lượng đạt ~2.700 từ 8 VU rồi đứng yên trong khi CPU DB ở 195%: nghẽn tính toán, không phải nghẽn đĩa.
- p95 nhảy từ ~4 ms (8 VU) lên ~47–49 ms (16 VU) trong khi p50 vẫn ~3 ms: một phần nhỏ giao dịch bị chậm hơn nhiều. Mình cho rằng đó là thử lại do xung đột cộng với hàng đợi CPU, nhưng chưa tách riêng nguyên nhân.

## 4. Kết quả các phiên bản

TPS (p95 ms):

| VU | MySQL baseline (2 lần) | MySQL tối ưu | MySQL có index | MongoDB baseline (2 lần) | MongoDB tối ưu | MongoDB có index |
|---|---|---|---|---|---|---|
| 4 | 513 / 643 | 602 (8,9) | 582 (9,2) | 1.751 / 1.930 | 1.839 (3,0) | 1.727 (3,1) |
| 8 | 576 / 758 | 687 (14,9) | 698 (14,1) | 2.691 / 2.624 | 2.675 (3,9) | **2.154** (7,5) |
| 16 | 691 / 772 | 695 (31,3) | 759 (27,8) | 2.700 / 2.688 | 2.703 (44,4) | **2.086** (61,7) |
| 32 | 790 / 800 | 838 (56,2) | 799 (61,1) | 2.680 / 2.672 | 2.653 (66,6) | **1.876** (81,7) |

**Độ nhiễu.** Hai lần đo baseline của MySQL chênh tới 25–32% ở 4–8 VU (513 so với 643, 576 so với 758), 12% ở 16 VU và 1% ở 32 VU; MongoDB chênh 10% ở 4 VU và ≤ 2% từ 8 VU. Chỉ các chênh lệch vượt khoảng này mới được xem là thật.

### Biến thể tối ưu: không có tác dụng đo được
Biến thể `optimized` ghi đơn trước, giữ khóa các hàng tồn kho nóng đến cuối và theo thứ tự cố định `(sku_id, warehouse_id)`; với MySQL còn gộp các dòng hàng vào một câu `INSERT` nhiều dòng (ít lượt gọi hơn, giao dịch ngắn hơn).
- MySQL: 602/687/695/838 nằm trong khoảng của hai lần baseline (513–643, 576–758, 691–772, 790–800), nên **không kết luận được có cải thiện**. Ở 32 VU không đổi.
- MongoDB: 1.839/2.675/2.703/2.653 giống baseline; số lần thử lại không giảm (893 so với 805–807 ở 32 VU). Điều này hợp lý: xung đột ghi của MongoDB là hủy ngay chứ không phải chờ, nên thứ tự lấy khóa không ngăn được nó.
- MySQL không có deadlock nào ở baseline, nên thứ tự khóa không có gì để ngăn.

### Thuế ghi của index: có ở MongoDB, không đo được ở MySQL
Áp dụng cả hai bộ index (class 1 và tìm kiếm) rồi chạy checkout y hệt:
- **MongoDB: giảm 18% (8 VU), 22% (16 VU), 30% (32 VU)** thông lượng, p95 xấu đi (3,9 → 7,5 ms ở 8 VU; 66 → 82 ms ở 32 VU). Mức giảm vượt nhiễu của MongoDB (≤ 2%). Mỗi đơn mới phải cập nhật thêm hai index ghép ba trường trên `orders`, và mỗi dòng hàng phải ghi thêm trường `quantity_available` (cùng index của nó) vì MongoDB không tự suy ra được giá trị này như cột sinh của MySQL. Mình chưa tách phần nào trong hai nguồn này chiếm nhiều hơn.
- **MySQL: không khác biệt đo được** (582/698/759/799 so với baseline 513–643/576–758/691–772/790–800). Ở 32 VU nơi nhiễu nhỏ (1%), chênh lệch ≤ 1% nên thuế nếu có là rất nhỏ. Cột sinh `quantity_available` được MySQL tự cập nhật.
- Quan sát thêm khi nạp lại dữ liệu có index: MySQL 47 → 58 giây, MongoDB 32 → 85 giây (mỗi trường hợp đo một lần).

### Công cụ có làm MySQL bị đánh giá thấp không?
`xk6-sql` mặc định chuẩn bị câu lệnh có tham số trên server (prepare + execute + close). Bật `interpolateParams=true` (thay tham số ở phía client): 675/719/856 TPS ở 4/8/32 VU so với baseline 513–643/576–758/790–800, tức tối đa ~7% ở 32 VU và nằm trong nhiễu ở mức thấp. Vậy lựa chọn này không quyết định kết quả; các số liệu chính vẫn dùng cấu hình mặc định.

## 5. Điều chỉnh dữ liệu và công cụ phải làm để đo được

1. **Tồn kho được cộng thêm 100.000** mỗi dòng sau mỗi lần nạp lại (mục 2).
2. **Validator `orders.schema_version` của MongoDB được nới từ `int` sang `int` hoặc `long`** chỉ trong lúc chạy checkout, vì `xk6-mongo` xuất mọi số nguyên JS thành `int64`. Giá trị vẫn là 1; các validator khác nguyên vẹn. `docker compose run k6` mặc định chạy lại `mongodb-schema-init` (đặt lại validator), nên k6 chạy với `--no-deps`.
3. **Đơn MongoDB phải dựng từ đơn mẫu**: `xk6-mongo` không tạo được Decimal128 hoặc ObjectId mới từ JS; giá trị đọc từ DB giữ nguyên kiểu khi ghi lại, và ObjectId mới được tạo phía server bằng `$toObjectId`.
4. **Sửa script kiểm tra `seed/checks/mongodb_logic.js`:** các so sánh số lượng tồn kho dùng `!==` nên bị sai khi trường là `Long` (sau `$inc` từ k6); đã chuyển sang `Number(...)`. Không đổi kết quả trên dữ liệu gốc.
5. Kết quả MySQL baseline đầu tiên ở mức tải thấp thấp hơn lần hai khá nhiều (mục 4); mình chưa tìm ra nguyên nhân (có thể là trạng thái cache sau lần nạp lại đầu tiên) nên cả hai lần đều được báo cáo.

## 6. Hạn chế

- Chỉ 4–32 VU, một đợt đo mỗi cấu hình (baseline hai đợt). Chênh lệch dưới ~25% ở MySQL mức tải thấp và dưới ~10% ở MongoDB không kết luận được.
- Hai DB chạy lần lượt trên cùng máy; k6 và DB cùng host, mỗi bên giới hạn 2 CPU.
- Khối lượng công việc là tổng hợp: 1–3 dòng hàng, 2.000 khách, 1.000 đơn mẫu, tồn kho dồi dào; không đo hành vi khi hết hàng và không có luồng đọc song song.
- Độ bền theo mặc định của từng DB (MySQL fsync hai lần mỗi commit, MongoDB `majority` trên một nút), nên so sánh TPS ghi phản ánh cấu hình an toàn mặc định chứ không phải cùng mức bền tuyệt đối.
- Các giải thích về nguyên nhân (group commit, đuôi p95 của MongoDB) là suy luận từ hình dạng đường cong và số liệu CPU, chưa có thí nghiệm riêng.

## 7. Chạy lại

```
python3 benchmark/run_checkout.py --phase baseline_checkout --db both --levels 4,8,16,32 --duration 45s
python3 benchmark/run_checkout.py --phase optimized_checkout --variant optimized --db both --levels 4,8,16,32 --duration 45s
# chi phí ghi của index: áp dụng hai bộ index, đo, rồi hoàn nguyên
python3 benchmark/optimization.py apply && python3 benchmark/optimization.py apply --set search
python3 benchmark/run_checkout.py --phase indexed_checkout --indexed --db both --levels 4,8,16,32 --duration 45s
python3 benchmark/optimization.py rollback --set search && python3 benchmark/optimization.py rollback
python3 benchmark/compare_class2.py --scenario checkout --phases baseline_checkout baseline_checkout_r2 optimized_checkout indexed_checkout
```
