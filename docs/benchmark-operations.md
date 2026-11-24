# Nghiệp vụ dùng cho benchmark (Phase 4)

Ghi chú các nghiệp vụ được chọn để đo hiệu năng trên MySQL và MongoDB. Chia hai loại theo mục đích đo. Tài liệu này liệt kê nghiệp vụ và quy định đặt file (mục cuối); câu SQL, pipeline MongoDB và kịch bản tải sẽ viết sau (`queries/`, `benchmark/`).

Cập nhật lần cuối: 2026-10-28.

## Loại 1: ít dùng, quét nhiều dữ liệu (so sánh từng query)

**Mục đích đo:** so sánh từng truy vấn giữa hai DB và trước/sau tối ưu. Thước đo chính là độ trễ của một lần chạy (p50, p95 qua nhiều lần chạy lặp) và kế hoạch thực thi (số dòng hoặc document phải đọc), lấy từ `EXPLAIN ANALYZE` (MySQL) và `explain("executionStats")` (MongoDB).

| #   | Nghiệp vụ                                                    | Dữ liệu phải đọc (MySQL / MongoDB)                                                             | Điểm cần để ý                                                                                                                    |
| --- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Doanh thu theo tháng                                         | `orders` / `orders`                                                                            | Tổng hợp trên phần lớn đơn (96% đơn là `delivered`). Đã có kết quả chuẩn trong 172 dòng tổng hợp của `seed/checks/` để đối chiếu |
| 2   | Top SKU bán chạy trong một kỳ                                | `orders` + `order_detail` + `sku` / `orders.lines[]` (`$unwind`) + `products`                  | Join cộng gom nhóm trên khoảng 312K dòng đơn. MongoDB phải mở mảng lồng                                                          |
| 3   | Doanh thu theo danh mục sản phẩm                             | `order_detail` + `sku` + `product` + `category` / `orders.lines[]` + `products` + `categories` | Đi qua 4 bảng ở MySQL, hai bước `$lookup` ở MongoDB                                                                              |
| 4   | Top khách hàng theo tổng chi tiêu                            | `orders` + `customer` / `orders` + `customers`                                                 | Gom nhóm theo khách trên toàn bộ đơn rồi nối thông tin khách                                                                     |
| 5   | Báo cáo hàng tồn thấp theo kho                               | `inventory` + `sku` + `product` + `warehouse` / `inventory` + `products` + `warehouses`        | Nối nhiều bảng nhỏ với `inventory` (khoảng 66K dòng)                                                                             |

### Quy ước chung cho loại 1
- Chạy từng truy vấn một mình, lặp nhiều lần, bỏ lần chạy đầu (cache lạnh) hoặc ghi riêng.
- Tham số (khoảng ngày, danh mục) giống nhau trên hai DB và cố định giữa baseline và optimized.
- Mỗi cặp truy vấn phải trả kết quả giống hệt nhau trước khi đo (đối chiếu với `seed/checks/`).
- Định nghĩa "doanh thu" là đơn có `status = 'delivered'`. Đây là giả định của tôi, cần bạn xác nhận.

### Lưu ý về dữ liệu
Bộ pilot (100K đơn, 312K dòng đơn, 66K tồn kho) nằm gọn trong cache của container (4 GB RAM), nên chênh lệch giữa hai DB và tác dụng của index sẽ nhỏ hơn so với dữ liệu 10M đơn. Cần ghi hạn chế này vào báo cáo.

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

### Câu hỏi chưa giải quyết
1. Catalog hiện chỉ có 900 sản phẩm và 2.000 SKU, nên tìm kiếm và lọc sản phẩm ít có ý nghĩa với dữ liệu này.
2. Tìm theo từ khóa tên có đưa vào không (chưa có index hỗ trợ, quét toàn bộ cả hai DB)?
3. Checkout: số dòng hàng mỗi đơn, tỉ lệ SKU "nóng" gây tranh chấp trên `inventory`, chính sách thử lại khi xung đột (deadlock ở MySQL, `WriteConflict` ở MongoDB).
4. Checkout làm thay đổi dữ liệu: mỗi lần đo có nạp lại dữ liệu trước không, và sau đó có chạy lại `seed/checks/` không (đặc biệt `inventory_reserved_ne_pending` để phát hiện cập nhật bị mất)?
5. Công cụ bắn tải đã chốt là k6 gọi thẳng DB qua extension (2026-10-28). `xk6-mongo` có `StartSession`/`StartTransaction`/`CommitTransaction`, nhưng Session chỉ có `Insert`, `FindOne`, `UpdateOne`, `DeleteOne`, nên checkout phải viết trong phạm vi các thao tác đó.
6. Mức độ bền khi ghi và mức cô lập của hai DB cần được đặt tương đương trước khi so sánh TPS ghi.
7. Tỉ lệ đọc và ghi trong kịch bản hỗn hợp (ví dụ chia theo tỉ trọng 22,7% và 3%, hay chạy riêng từng nghiệp vụ).

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
