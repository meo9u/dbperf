# Nghiệp vụ dùng cho benchmark (Phase 4)

Ghi chú các nghiệp vụ được chọn để đo hiệu năng trên MySQL và MongoDB. Chia hai loại theo mục đích đo. Tài liệu này liệt kê nghiệp vụ và quy định đặt file (mục cuối); câu SQL, pipeline MongoDB và kịch bản tải sẽ viết sau (`queries/`, `benchmark/`).

Cập nhật lần cuối: 2026-11-25.

## Loại 1: ít dùng, quét nhiều dữ liệu (so sánh từng query)

**Mục đích đo:** so sánh từng truy vấn giữa hai DB và trước/sau tối ưu. Thước đo chính là độ trễ của một lần chạy (p50, p95 qua nhiều lần chạy lặp) và kế hoạch thực thi (số dòng hoặc document phải đọc), lấy từ `EXPLAIN ANALYZE` (MySQL) và `explain("executionStats")` (MongoDB).

| #   | Nghiệp vụ                                                    | Dữ liệu phải đọc (MySQL / MongoDB)                                                             | Điểm cần để ý                                                                                                                    |
| --- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Doanh thu theo tháng                                         | `orders` / `orders`                                                                            | Tổng hợp trên phần lớn đơn (96% đơn là `delivered`). Đã có kết quả chuẩn trong 172 dòng tổng hợp của `seed/checks/` để đối chiếu |
| 2   | Top SKU bán chạy trong một kỳ                                | `orders` + `order_detail` + `sku` / `orders.lines[]` (`$unwind`) + `products`                  | Join cộng gom nhóm trên khoảng 3,1 triệu dòng đơn (1,5 triệu dòng của năm 2019). MongoDB phải mở mảng lồng                                                          |
| 3   | Doanh thu theo danh mục sản phẩm                             | `order_detail` + `sku` + `product` + `category` / `orders.lines[]` + `products` + `categories` | Đi qua 4 bảng ở MySQL, hai bước `$lookup` ở MongoDB                                                                              |
| 4   | Top khách hàng theo tổng chi tiêu                            | `orders` + `customer` / `orders` + `customers`                                                 | Gom nhóm theo khách trên toàn bộ đơn rồi nối thông tin khách                                                                     |
| 5   | Báo cáo hàng tồn thấp theo kho                               | `inventory` + `sku` + `product` + `warehouse` / `inventory` + `products` + `warehouses`        | Nối nhiều bảng nhỏ với `inventory` (321.410 dòng)                                                                             |

### Quy ước chung cho loại 1
- Chạy từng truy vấn một mình, lặp nhiều lần, bỏ lần chạy đầu (cache lạnh) hoặc ghi riêng.
- Tham số (khoảng ngày, danh mục) giống nhau trên hai DB và cố định giữa baseline và optimized.
- Mỗi cặp truy vấn phải trả kết quả giống hệt nhau trước khi đo (đối chiếu với `seed/checks/`).
- Định nghĩa "doanh thu" là đơn có `status = 'delivered'`. Đây là giả định của đồ án.

### Lưu ý về dữ liệu
Bộ dữ liệu đang nạp là `bigdata-final` (1.000.000 đơn, ~3,1 triệu dòng đơn, 321.410 dòng tồn kho, 50.000 khách, 4.000 sản phẩm, 20.000 SKU). Cache mỗi DB là 1536 MB, nhỏ hơn dữ liệu của MySQL (~560 MB dữ liệu + index nằm gọn) nhưng đủ lớn để phần lớn dữ liệu nóng nằm trong cache, nên chênh lệch do I/O đĩa chưa lộ ra. Quy mô vẫn nhỏ hơn mục tiêu 10 triệu đơn; cần ghi hạn chế này vào báo cáo.

Thống kê MySQL ảnh hưởng đến kế hoạch thực thi: chạy `ANALYZE TABLE` trước khi đo baseline (xem `docs/bao-cao-ket-qua-class1.md` mục 8.1 và `docs/bao-cao-ket-qua-class2-search.md` mục 5).

## Loại 2: tần suất cao, nhiều người dùng cùng lúc (so sánh chịu tải)

**Mục đích đo:** so sánh độ chịu tải giữa hai DB: TPS tối đa, độ trễ dưới tải và điểm bão hòa, trước/sau tối ưu. Công cụ bắn tải là k6 (chốt 2026-10-28, xem `CLAUDE.md`).

### 2 nghiệp vụ đã chọn (2026-10-27)

| # | Nghiệp vụ | Loại thao tác | Vì sao chọn |
|---|---|---|---|
| 1 | Tìm kiếm và lọc sản phẩm (theo danh mục, khoảng giá, màu, từ khóa tên, có phân trang) | Đọc | Thao tác đọc nóng nhất của workload (W1: 22,7%). Lộ rõ khác biệt giữa join (giá ở `sku`) và nhúng (`skus[]`), và là nơi baseline `OFFSET` đổi sang keyset ở Phase 5 |
| 2 | Đặt hàng (checkout, ghi, giao dịch đa document) | Ghi | Thao tác ghi có tranh chấp khóa thật (`orders` + `inventory`), nơi MySQL và MongoDB khác nhau nhiều nhất về giao dịch (W13: 3%) |

Bộ này gồm một thao tác đọc và một thao tác ghi, nên kịch bản hỗn hợp (đọc nhiều, ghi ít) đơn giản và dễ phân tích. Tỉ trọng lấy từ `docs/schema/mongodb-design-summary.md` (giả định của dự án, không phải số đo thực tế).

### Đã cân nhắc nhưng không chọn

Xem chi tiết sản phẩm, xem tồn kho của một SKU, ghi kết quả thanh toán, hủy đơn, xem lịch sử đơn hàng của khách, xem chi tiết một đơn hàng, tra khách hàng theo email.

### Quyết định đã chốt (2026-11-25)

1. **Catalog** có 4.000 sản phẩm và 20.000 SKU (không phải 900 và 2.000), đủ để tìm kiếm có ý nghĩa; mỗi danh mục lớn nhất có ~700 sản phẩm.
2. **Tìm kiếm** gồm danh mục (bắt buộc, chọn theo trọng số kích thước), và tùy chọn màu (50%), khoảng giá (60%), từ khóa tên (30%, khớp chuỗi con, không dùng `FULLTEXT`/`$text` vì khớp theo từ cho kết quả khác), phân trang trang 0–7 (`OFFSET`/`$skip`, không dùng keyset). Cùng chuỗi tham số cho hai DB (`benchmark/scenarios/lib/search_params.js`).
3. **Chạy riêng từng nghiệp vụ**, không chạy hỗn hợp; mỗi nghiệp vụ đo ở nhiều mức tải (4, 8, 16, 32, 64 VU).
4. **Mức bền và cô lập: giữ mặc định của từng DB và ghi rõ vào báo cáo.** MySQL: `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1`, REPEATABLE READ. MongoDB: `w:majority` kèm journal, snapshot isolation trong transaction.
5. **Checkout làm thay đổi dữ liệu:** đưa dữ liệu về trạng thái ban đầu trước mỗi mức tải, và sau mỗi lần chạy kiểm tra tính toàn vẹn (số đơn mới bằng số checkout thành công, `inventory_reserved_ne_pending` = 0, `status_payment_consistency` vẫn là 562 vi phạm đã có trong dữ liệu).
6. **Công cụ:** k6 gọi thẳng DB qua extension. `xk6-sql` không có API giao dịch (dùng `START TRANSACTION`/`COMMIT` trên cùng một kết nối); session của `xk6-mongo` chỉ có `insert`, `findOne`, `updateOne`, `deleteOne` và `updateOne` không trả kết quả, nên hết hàng phải được phát hiện qua lỗi ràng buộc (CHECK ở MySQL, validator ở MongoDB). Chi tiết thiết kế checkout được xác nhận bằng bước thăm dò (xem mục dưới).

### Kết quả đã có cho class 2

Tìm kiếm (`search_products`): baseline, tối ưu và so sánh trong `docs/bao-cao-ket-qua-class2-search.md`; số liệu ở `benchmark/results/<phase>/load/`.

Đặt hàng (`checkout`): baseline, biến thể tối ưu, chi phí ghi của index và kiểm tra công cụ trong `docs/bao-cao-ket-qua-class2-checkout.md`.

### Thiết kế checkout (đã xác nhận bằng thăm dò, 2026-11-25)

Mỗi yêu cầu đặt một đơn trạng thái `pending` kèm một thanh toán `pending`, 1–3 dòng hàng lấy từ **đơn mẫu** trong dữ liệu thật, tăng `inventory.quantity_reserved` cho từng (SKU, kho) trong cùng một transaction. Một nhóm nhỏ SKU "nóng" nhận phần lớn dòng hàng để tạo tranh chấp khóa thật; khi xung đột (deadlock ở MySQL, `WriteConflict` ở MongoDB) thử lại tối đa 3 lần. Đơn mẫu dùng chung cho hai DB vì `orders._id` của MongoDB và `order_id` của MySQL cùng số thứ tự (đơn 1, 2, 3 có cùng khách, tổng tiền, số dòng).

Kết quả thăm dò khả năng của extension (mọi thao tác ghi đều được rollback hoặc dùng collection tạm):

| Câu hỏi | Kết quả | Hệ quả cho thiết kế |
|---|---|---|
| MySQL: transaction qua `xk6-sql` (không có API `begin`)? | `START TRANSACTION`, các câu lệnh, `ROLLBACK`/`COMMIT` luôn chạy trên **cùng một kết nối**: 97.493/97.493 lần với 32 VU; ngữ nghĩa đúng 34.599/34.599 lần (đọc thấy giá trị mới trong transaction, rollback trả về giá trị cũ) | Dùng câu lệnh thường, không cần cấu hình thêm |
| MySQL: lỗi có bắt được không? | Bắt được bằng `try/catch`, dạng `Error <mã> (<sqlstate>): ...`. Hết hàng: `Error 3819 ... Check constraint 'chk_inventory_quantity_reserved' is violated`; deadlock: `Error 1213 (40001) Deadlock found...` | Phân loại theo mã trong thông báo; sau lỗi gọi `ROLLBACK` |
| Mongo: tạo Decimal128 từ JS? | Không: `{$numberDecimal}` không được chuyển đổi. Nhưng Decimal128, ObjectId và ngày lấy từ tài liệu đã đọc (đơn mẫu) giữ nguyên kiểu khi chèn lại; pipeline cập nhật (`$toDecimal`) cũng tạo được Decimal128 | Dựng đơn từ đơn mẫu (lines, total_amount, kiểu tiền giữ nguyên) |
| Mongo: ObjectId mới (cho `payment_id`)? | Mảng 12 số tự tạo **không** thành ObjectId. Tạo được bằng `client.aggregate` với `$toObjectId` trên chuỗi hex; kết quả giữ kiểu ObjectId | Tạo sẵn một nhóm `payment_id` trong giai đoạn init của mỗi VU |
| Mongo: số nguyên JS? | Xuất thành `long` (int64). Validator `schema_version` của `orders` yêu cầu `int` nên chèn bị từ chối (chỉ trường này sai) | Nới `orders.schema_version` thành `int` hoặc `long` **chỉ trong lúc chạy checkout** (script áp dụng; `mongodb-schema-init` đặt lại bản gốc). Ghi vào báo cáo như hạn chế của công cụ |
| Mongo: lỗi trong session? | Vi phạm validator (hết hàng) và `WriteConflict` đều ném lỗi bắt được; sau lỗi validator transaction đã bị hủy (`NoSuchTransaction` khi commit). `session.updateOne` không trả về kết quả | Hết hàng = lỗi "Document failed validation" khi cập nhật `inventory`; xung đột = chứa `WriteConflict`; luôn `abortTransaction` trong `try/catch` |
| Chạy k6 có đổi schema không? | Có: service `k6` phụ thuộc `mongodb-schema-init`, nên mỗi lần `compose run k6` đặt lại validator về bản gốc (và `docker compose up` cũng vậy) | Chạy k6 với `--no-deps`; áp dụng nới validator ngay trước khi chạy |

## Quy định đặt file

### Truy vấn Loại 1

Số thứ tự và tên lấy từ bảng Loại 1 ở trên; hai DB dùng cùng tên, chỉ khác phần mở rộng.

| # | Tên | MySQL | MongoDB |
|---|---|---|---|
| 1 | `q1_revenue_by_month` | `queries/mysql/baseline/q1_revenue_by_month.sql` | `queries/mongodb/baseline/q1_revenue_by_month.js` |
| 2 | `q2_top_skus` | `queries/mysql/baseline/q2_top_skus.sql` | `queries/mongodb/baseline/q2_top_skus.js` |
| 3 | `q3_revenue_by_category` | `queries/mysql/baseline/q3_revenue_by_category.sql` | `queries/mongodb/baseline/q3_revenue_by_category.js` |
| 4 | `q4_top_customers` | `queries/mysql/baseline/q4_top_customers.sql` | `queries/mongodb/baseline/q4_top_customers.js` |
| 5 | `q5_low_stock_by_warehouse` | `queries/mysql/baseline/q5_low_stock_by_warehouse.sql` | `queries/mongodb/baseline/q5_low_stock_by_warehouse.js` |

- Mỗi file chứa đúng một truy vấn. Dòng đầu là comment ghi `qN`, câu hỏi nghiệp vụ và tham số.
- Phase 5 đặt bản tối ưu cùng tên ở `queries/{mysql,mongodb}/optimized/`, để so sánh theo tên file.
- Tên `qN_*` đã cố định; muốn đổi thì sửa bảng này trước.

### Kết quả Loại 1

```
benchmark/results/baseline/
  meta.json                      # run_id dataset (lấy từ seed/data/manifest.json), phiên bản DB, ngày chạy
  mysql/
    qN_<name>.result.tsv         # kết quả nghiệp vụ
    qN_<name>.explain.txt        # EXPLAIN ANALYZE
    qN_<name>.timing.json        # độ trễ các lần chạy
  mongodb/
    qN_<name>.result.tsv
    qN_<name>.explain.json       # explain("executionStats")
    qN_<name>.timing.json
```

- `result.tsv`: dòng đầu là tên cột, các dòng sau phân cách bằng tab. Số nguyên không có dấu phân cách; tiền đúng 2 chữ số thập phân (`29.89`); thời gian `YYYY-MM-DD HH:MM:SS` theo UTC. Hai DB in cùng cột, cùng thứ tự dòng (luôn có khóa sắp xếp phụ), và dùng khóa tự nhiên (`sku_code`, tên danh mục, tên kho, `email`) thay vì id, vì MySQL dùng số nguyên còn MongoDB dùng `ObjectId`.
- `diff` của hai file `result.tsv` cùng tên phải rỗng trước khi đo thời gian.
- `timing.json`: `{ "query", "db", "runs", "discarded_cold", "latency_ms": { "min", "p50", "p95", "max" }, "samples_ms": [] }`. Lặp ít nhất 11 lần; lần đầu (cache lạnh) ghi riêng, không tính vào p50 và p95.
- Phase 5 ghi kết quả tối ưu vào `benchmark/results/optimized/` với cùng cấu trúc và tên file.

### Kịch bản Loại 2 (k6)

```
benchmark/scenarios/
  search_products.<db>.js        # tìm kiếm và lọc sản phẩm
  checkout.<db>.js               # đặt hàng
benchmark/results/baseline/load/
  <scenario>.<db>.summary.json   # xuất từ k6 (--summary-export)
```

- `<db>` là `mysql` hoặc `mongodb`; hai kịch bản cùng nghiệp vụ dùng cùng tham số tải (số VU, thời lượng, dữ liệu đầu vào).
- Service `k6` trong `docker-compose.yml` mount `./benchmark/scenarios` (chỉ đọc) vào `/scripts` và `./benchmark/results` vào `/results`.
- Checkout làm thay đổi dữ liệu: nạp lại dữ liệu trước mỗi lần đo và chạy lại `seed/checks/` sau đó (xem câu hỏi 4 ở trên).
