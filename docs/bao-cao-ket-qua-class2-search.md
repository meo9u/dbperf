# Báo cáo class 2: tìm kiếm sản phẩm (`search_products`), trước và sau tối ưu

Ngày chạy: 2026-11-25. Phạm vi: chỉ kịch bản tìm kiếm (đọc). Checkout (ghi) chưa xây dựng, class 1 không chạy lại ở đây (xem `docs/bao-cao-ket-qua-class1.md`).

Số liệu gốc: `benchmark/results/<phase>/load/`; bảng gộp `benchmark/results/load_comparison.search_products.tsv`.

## 1. Tóm tắt

Thông lượng (TPS) và p95 (ms) ở 16 VU, 2 CPU mỗi DB, cache 1536 MB mỗi DB:

| | Baseline | Sau thêm index (`idx`) | Sau tối ưu (`optimized`) | Tăng (so với baseline sau ANALYZE) |
|---|---|---|---|---|
| MySQL | 320 TPS / 190 ms | 711 / 92 | 688 / 92 | **2,2x** |
| MongoDB | 325 TPS / 101 ms | 346 / 102 | 505 / 99 | **1,55x** |

Ở 64 VU: MySQL 299 → 659 TPS (2,2x), p95 603 → 204 ms; MongoDB 286 → 479 TPS (1,7x), p95 596 → 400 ms.

1. **MySQL được lợi từ index (cột sinh `color` + index phủ), không cần viết lại truy vấn.** Thêm hint `JOIN_ORDER` còn làm chậm đi 25%.
2. **MongoDB gần như không được lợi từ index một mình**; chỉ khi thêm `$match` + `$elemMatch` trước `$unwind` để index lọc được từng phần tử mảng thì mới nhanh hơn.
3. **Baseline đầu tiên của MySQL bị thiên lệch** vì thống kê cũ (chi tiết ở mục 5). Mốc công bằng là `baseline_r2`.
4. Sau tối ưu MySQL nhanh hơn MongoDB khoảng 1,36x về TPS; ở baseline đã `ANALYZE` hai bên ngang nhau (320 so với 325 TPS ở 16 VU).
5. Kết quả trả về không đổi ở mọi bước: 60 yêu cầu cố định, hai DB giống hệt nhau và giống kết quả tham chiếu (`results/baseline/load/search_products.verify.txt`).

## 2. Cách đo

- Mỗi yêu cầu: chọn danh mục (có trọng số theo kích thước), tùy chọn lọc theo màu (50%), khoảng giá (60%), từ khóa tên (30%), phân trang (trang 0–7, nghiêng về trang đầu). Cùng chuỗi tham số cho hai DB (`benchmark/scenarios/lib/search_params.js`). Khoảng 43% yêu cầu cho kết quả rỗng ở cả hai DB.
- k6 chạy vòng kín (không nghỉ), 4/8/16/32/64 VU, 45 giây mỗi mức, 20 giây khởi động. Container k6: 2 CPU, 2 GB.
- Trạng thái đo (thư mục kết quả):

| Phase | Schema | Yêu cầu | Ghi chú |
|---|---|---|---|
| `baseline` | không index mới | `baseline` | lần đo đầu, thống kê MySQL cũ |
| `baseline_r2` | không index mới, sau `ANALYZE` | `baseline` | **mốc so sánh công bằng**; MongoDB lần 2 để đo nhiễu |
| `idx` | thêm index | `baseline` | chỉ index |
| `optimized` | thêm index | `optimized` | index + viết lại (MongoDB). MySQL: cùng truy vấn như `idx` |
| `optimized_hint` | thêm index | MySQL `hint`, MongoDB `optimized` | thí nghiệm hint; phần MongoDB là lần chạy `optimized` thứ nhất |

## 3. Điều kiện nghẽn

Chẩn đoán lúc 16 VU trên baseline: container DB dùng ~197% CPU (trần 200%), k6 chỉ 5–10%. MySQL báo độ trễ phía server 85–115 ms mỗi yêu cầu, trung bình ~5.650 dòng đã xem mỗi yêu cầu. Vậy DB là điểm nghẽn, nên tối ưu DB có thể cho thấy hiệu quả. Thông lượng cao nhất ở mức tải thấp nhất (4 VU) và giảm dần khi tăng VU, vì chỉ có 2 CPU và các yêu cầu nặng tranh nhau.

## 4. Vì sao nhanh hơn hoặc không

### MySQL: nhanh hơn 2,2x nhờ index (không viết lại truy vấn)

Index thêm vào: cột sinh `sku.color` (stored, cùng biểu thức `JSON_UNQUOTE(JSON_EXTRACT(variant_attributes,'$.color'))`) và index phủ `sku(product_id, status, color, current_price, sku_code)`, cộng `product(category_id, status)`.

Cơ chế:
- **Bỏ phân tích JSON theo từng dòng.** Trước đó, mỗi SKU lọc theo màu phải parse JSON. Cột sinh lưu sẵn giá trị và truy vấn cũ tự dùng nó vì biểu thức giống hệt.
- **Index phủ.** Khi đi từ `product` sang `sku` theo `product_id`, mọi cột lọc và `sku_code` đều nằm trong index, nên không cần đọc dòng gốc.
- Bằng chứng (`explain.mysql.filtered.txt`): yêu cầu lọc (danh mục lớn, màu hiếm, khoảng giá) giảm từ **16,4 ms xuống 3,5 ms** sau khi có index. Yêu cầu chỉ theo danh mục vẫn ~0,4 ms vì optimizer quét `sku` theo `sku_code` và dừng khi đủ 20 dòng, không phải sắp xếp.

Hint `JOIN_ORDER(p, s)` cho yêu cầu có lọc: **536 TPS thay vì 711 ở 16 VU (−25%)**. Mình đã kiểm tra thử 7 trường hợp mẫu và thấy hint nhanh hơn, nhưng trên toàn bộ phân phối yêu cầu thì chậm hơn. Mình chưa tách được nguyên nhân cụ thể, và bài học là phải đo trên toàn bộ phân phối tải thay vì vài trường hợp chọn tay. Kết luận: bản tối ưu của MySQL là `idx`; `optimized` (688) và `idx` (711) cùng truy vấn, chênh 3% là nhiễu.

### MongoDB: index một mình không đủ, cần viết lại pipeline

- `idx` (index `{category_id, status}` và index multikey trên màu/giá): đọc 1.456 document thay vì 4.000 cho yêu cầu theo danh mục lớn, nhưng thời gian không đổi (6 → 7 ms). Phần tốn là `$unwind` ra ~3,6 nghìn SKU và `$sort` theo `sku_code`; không index nào cho thứ tự `sku_code` xuyên qua nhiều sản phẩm. Thông lượng chỉ tăng 6% (346 so với 325), nằm trong nhiễu (baseline hai lần đo cách nhau tới 8%).
- Index multikey không được dùng cho điều kiện màu/giá vì chúng nằm **sau** `$unwind`, nơi chúng không còn là điều kiện trên mảng.
- `optimized`: thêm `$match` trước `$unwind` với `skus: {$elemMatch: {status, current_price, variant_attributes.color}}`, vẫn giữ `$match` sau `$unwind` để kết quả đúng. `$elemMatch` ràng buộc các điều kiện lên **cùng một phần tử**, nên planner dùng được index multikey với cận chặt. Bằng chứng (`explain.mongodb.filtered.json`): yêu cầu lọc đọc **29 document** (so với 1.456 ở `idx`, 4.000 ở baseline) và từ 7 ms xuống ~0 ms. Thông lượng tăng 1,55x ở 16 VU và 1,7x ở 64 VU, lặp lại ở hai lần chạy (504 và 505 TPS).
- Yêu cầu chỉ theo danh mục không hưởng lợi (vẫn `$unwind` và sắp xếp cả danh mục), nên mức tăng bị giới hạn ở mức 1,55–1,7x.

### Không áp dụng
- **Phân trang keyset:** các yêu cầu chỉ tới trang 7 (`OFFSET` ≤ 140) và kết quả tối đa vài nghìn dòng, nên `OFFSET` gần như không tốn; keyset còn làm chuỗi yêu cầu có trạng thái, không còn giống nhau giữa hai DB.
- **`FULLTEXT` / `$text`:** khớp theo từ nên cho kết quả khác `LIKE '%kw%'` / `$regex`.

## 5. Bài học về thống kê MySQL

Baseline đầu (`baseline`) và lần hai (`baseline_r2`) cùng schema, cùng dữ liệu nhưng MySQL cho **399 và 669 TPS ở 4 VU** (189 và 320 ở 16 VU). Giữa hai lần chỉ có `ANALYZE TABLE sku, product` (do script rollback chạy). Plan đã đổi: từ "product trước, bảng tạm, sắp xếp ~3,6 nghìn dòng" (~7 ms cho danh mục lớn) sang "quét `sku` theo `sku_code`, tra `product`, dừng sau 20 dòng" (~0,4 ms), nhưng chậm hơn cho yêu cầu lọc hiếm (16 ms, quét ~5.900 SKU và parse JSON). Thống kê InnoDB được lấy mẫu ngẫu nhiên nên kết quả có thể đổi plan.

Hệ quả cho cách đọc: nếu lấy baseline đầu làm mốc, MySQL "tăng 3,8x" ở 16 VU; với mốc công bằng chỉ 2,2x. Báo cáo dùng `baseline_r2`. Đây là lần thứ hai (sau class 1 q5) thống kê làm thay đổi kết luận, nên mọi lần đo baseline của MySQL nên chạy `ANALYZE TABLE` trước.

## 6. Chi phí

| | Trước | Sau |
|---|---|---|
| MySQL `sku` index | 1,8 MB | 4,0 MB (cộng cột sinh `color`) |
| MongoDB `products` index | 2,7 MB | 3,1 MB |

Chi phí ghi (cập nhật giá hoặc trạng thái SKU phải cập nhật thêm index và cột sinh) **chưa đo** vì chưa có kịch bản ghi.

## 7. Hạn chế

1. Mỗi mức tải đo một lần; chỉ baseline có hai lần (MongoDB chênh ≤ 8%). Mức tăng nhỏ hơn ~10% (ví dụ MongoDB `idx`) không đáng tin.
2. Dữ liệu nhỏ (4.000 sản phẩm, 20.000 SKU) vừa trong cache; tải và phân phối yêu cầu là tổng hợp (xem mục 2).
3. Hai DB chạy lần lượt trên cùng máy; k6 và DB cùng host.
4. Độ trễ do `iteration_duration` của k6 (không dùng `Date.now()` của kịch bản, độ phân giải 1 ms).
5. Lý do hint làm chậm MySQL chưa được tách bạch (mục 4).

## 8. Chạy lại

```
python3 benchmark/run_class2.py --scenario search_products --phase baseline_r2 --variant baseline --db both
python3 benchmark/optimization.py apply --set search
python3 benchmark/run_class2.py --scenario search_products --phase idx --variant baseline --db both
python3 benchmark/run_class2.py --scenario search_products --phase optimized --variant optimized --db both
python3 benchmark/explain_search.py --phase idx          # plan của yêu cầu mẫu
python3 benchmark/compare_class2.py --scenario search_products --phases baseline_r2 baseline idx optimized optimized_hint
python3 benchmark/optimization.py rollback --set search    # trở về baseline
```
