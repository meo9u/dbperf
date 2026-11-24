# Tóm tắt thiết kế MongoDB (theo quy trình 4 bước)

## Bước 1. Xác định workload

**Quy mô (giả định của dự án):** 500K customer, 200K SKU, 10M đơn; thiết kế chịu 10x (5M, 2M, 100M) mà không đổi cấu trúc. Mix khoảng 85% đọc, 15% ghi, **chưa chuẩn hóa lại** sau khi bỏ các thao tác không còn.

**Thao tác đọc** (% tổng số thao tác):


| Collection     | Thao tác                                                                                                         | %        | Ghi chú                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------ |
| **products**   | W1 liệt kê theo category 22,7; W2 chi tiết sản phẩm 22,8; W3 tra theo `sku_code` 2                               | **47,5** | Nóng nhất. W1 chỉ lọc đúng `category_id` (không còn "gồm cả category con").                |
| **orders**     | W6 lịch sử đơn của customer 9; W7 xem một đơn 9; W8 lọc theo ngày và trạng thái 1,5; W9 doanh thu theo tháng 0,1 | **19,6** | W6, W8, W9 là 3 truy vấn baseline của giai đoạn 4 (BQ1, BQ2, BQ3). "Ngày" là `created_at`. |
| **inventory**  | W4 xem tồn kho 8,3                                                                                               | 8,3      | Đồng thời là collection bị ghi nhiều nhất.                                                 |
| **customers**  | W5 tra theo email 6                                                                                              | 6        |                                                                                            |
| **categories** | W11 danh sách category 3                                                                                         | 3        | Nhỏ, cache được ở ứng dụng.                                                                |
| **warehouses** | W12 danh sách kho 0,2                                                                                            | 0,2      |                                                                                            |


**Thao tác ghi** (khoảng 15%): W13 checkout (3%), W14 ghi kết quả thanh toán, W15 chuyển trạng thái (`shipped` sang `delivered`), W16 xuất kho, W17 hủy hoặc trả hàng, W18–W19 đăng ký và sửa customer, W20 quản trị catalog, W21 nhập kho, W23 job hết hạn đơn chưa thanh toán. W13, W16, W17, W23 chạm cả `orders` và `inventory` nên cần transaction đa document.

**Mục tiêu độ trễ (giả định):** đọc p95 ≤ 50 ms, ghi ≤ 100 ms, W9 là tác vụ lô ≤ 30 s.

**Kích thước document** (đo ngày 2026-10-22 trên `mongo:8.0.32`, văn bản ASCII):


| Collection                          | Điển hình (B) | Tối đa theo validator, ký tự 3 byte (B) |
| ----------------------------------- | ------------- | --------------------------------------- |
| categories                          | 99            | 542                                     |
| warehouses                          | 138           | 1.612                                   |
| inventory                           | 153           | 247                                     |
| customers                           | 210           | 1.626                                   |
| products (3 SKU, mô tả 1.000 ký tự) | 1.711         | 157.706 (50 SKU, mô tả 4.000 ký tự)     |
| orders (3 dòng, 1 payment)          | 806           | 8.746 (50 dòng, 5 payment)              |


Document lớn nhất (`products`) dưới 1% giới hạn 16 MiB.

**Dung lượng dữ liệu ước tính** (tính từ kích thước điển hình ở trên nhân với số lượng giả định): `orders` 10M × 806 B ≈ 8,1 GB; `products` 66.667 × 1.711 B ≈ 0,11 GB; `customers` 500K × 210 B ≈ 0,1 GB; `inventory` 600K × 153 B ≈ 0,09 GB. Tổng dữ liệu khoảng **8,4 GB** ở quy mô cơ sở (khoảng 84 GB ở 10x), cộng index (mục bước 4) khoảng 1 GB. Cache WiredTiger ước tính 1,5 GB (chưa kiểm chứng), nên dataset vẫn lớn hơn cache khoảng 6 lần. Working set chưa được tính lại cho thiết kế mới.

## Bước 2. Ánh xạ quan hệ (embed hay reference)

**9 quan hệ FK của ERD, kết quả 6 collection cho 9 bảng:**


| Quan hệ                   | N trung bình / tối đa | Quyết định                                                        | Lý do                                                                                                                    |
| ------------------------- | --------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| product → sku             | 3 / 50                | **Embed** `products.skus[]`                                       | Có trần, đọc cùng nhau ở W2                                                                                              |
| orders → order\_detail    | 3 / 50                | **Embed** `orders.lines[]`                                        | Có trần, bất biến sau checkout                                                                                           |
| orders → payment          | 1,2 / 5               | **Embed** `orders.payments[]`                                     | Có trần                                                                                                                  |
| orders → địa chỉ giao     | 1                     | **Embed** `orders.shipping{}`                                     | Snapshot địa chỉ lúc đặt                                                                                                 |
| category → product        | khoảng 133, lệch      | **Reference** `products.category_id`                              | Không có trần                                                                                                            |
| customer → orders         | 20 / 2.000            | **Reference** `orders.customer_id`                                | Không có trần, tăng theo thời gian                                                                                       |
| warehouse → inventory     | 60.000                | **Reference** `inventory.warehouse_id`                            | Không có trần                                                                                                            |
| sku → inventory           | 3 / 10                | **Collection riêng**, mỗi document là một cặp (sku, warehouse)    | Ghi ở mỗi đơn (khoảng 6,6% mix) so với đọc catalog 47,5%: tách ra để khỏi ghi lại document catalog và tranh chấp với đọc |
| sku, warehouse → dòng đơn | không có trần         | **Reference** `lines[].sku_id`, `lines[].warehouse_id` (optional) | Chỉ kèm snapshot giá                                                                                                     |


**6 collection:** `categories`, `products` (gồm `skus[]`), `warehouses`, `inventory`, `customers`, `orders` (gồm `lines[]`, `payments[]`, `shipping`).

**Chi phí nhất quán:** các thao tác ưu tiên cao (W1, W2, W5, W6, W7, W8, W9, W13, W14, W15) đều **0 `$lookup`**. Vì `inventory` tách riêng nên checkout, xuất kho, hủy hoặc trả hàng và hết hạn đơn là transaction đa document; các thao tác còn lại là cập nhật một document. Toàn vẹn tham chiếu do ứng dụng giữ (không có FK), quy ước không xóa cứng.

**`_id`:** ObjectId do client sinh. `orders._id` lấy từ khóa idempotency của checkout nên thử lại không tạo đơn trùng.

**Hệ quả của việc đơn giản hóa ERD:** dòng đơn không còn snapshot tên, mã, biến thể SKU, nên W7 muốn hiện chúng phải đọc thêm `products` theo `skus.sku_id` (1 truy vấn index ở ứng dụng).

## Bước 3. Áp dụng design pattern


| Pattern                                    | Dùng ở                                      | Để giải quyết                                                                                                   |
| ------------------------------------------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Extended Reference** (snapshot bất biến) | `orders.lines[].unit_price_snapshot`        | Giữ đúng giá lúc mua, đọc đơn không cần tra catalog để biết giá. Chỉ còn snapshot giá.                          |
| **Computed** (tính khi ghi)                | `lines[].line_total`, `orders.total_amount` | W9 doanh thu chỉ đọc `total_amount` từ index, không phải đọc hết document. Tương đương cột generated của MySQL. |
| **Schema Versioning**                      | `schema_version` ở mọi document             | Migration kiểu expand/contract, không downtime.                                                                 |


Các pattern đã cân nhắc và không dùng, vì không có vấn đề đo được: Bucket, Attribute, Polymorphic, Subset, Outlier, Approximation, Archive, Document Versioning. Riêng việc không tổng hợp trước doanh thu nhằm giữ phép so sánh công bằng với MySQL.

**Đã bỏ so với thiết kế cũ:** pattern **Tree** (`ancestors`, `category_path`), vì category nay là danh mục phẳng.

### Field của từng collection


| Collection          | Field                                                                                                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `categories`        | `_id`, `schema_version`, `name`, `status`, `created_at`                                                                                                                |
| `products`          | `_id`, `schema_version`, `category_id`, `name`, `description?`, `status`, `skus[]`, `created_at`, `updated_at`                                                         |
| `products.skus[]`   | `sku_id`, `sku_code` (chữ hoa), `variant_attributes` (≤8 khóa), `current_price`, `status`, `updated_at`                                                                |
| `warehouses`        | `_id`, `schema_version`, `name`, `address`, `city`, `status`                                                                                                           |
| `inventory`         | `_id`, `schema_version`, `sku_id`, `warehouse_id`, `quantity_on_hand`, `quantity_reserved`, `last_receipt_id?`, `updated_at`                                           |
| `customers`         | `_id`, `schema_version`, `full_name`, `address`, `email` (chữ thường), `phone?`, `created_at`, `updated_at`                                                            |
| `orders`            | `_id`, `schema_version`, `customer_id`, `status`, `payment_due_at?`, `shipping{recipient_name, phone, address}`, `total_amount`, `lines[]`, `payments[]`, `created_at` |
| `orders.lines[]`    | `sku_id`, `unit_price_snapshot`, `quantity`, `line_total`, `warehouse_id?`                                                                                             |
| `orders.payments[]` | `payment_id`, `payment_method`, `amount`, `status`, `created_at`                                                                                                       |


Dấu `?` là field optional (vắng mặt, không bao giờ `null`). Tiền là `Decimal128`, thời gian là BSON date.

### Validator

`validationLevel: strict`, `additionalProperties: false`, và `$expr` ép các đẳng thức:

- `line_total = quantity × unit_price_snapshot`
- `total_amount = Σ lines.line_total`
- `quantity_reserved ≤ quantity_on_hand`
- không trùng `sku_id` hoặc `sku_code` trong một product, không trùng `payment_id` trong một đơn
- `payment_due_at` chỉ tồn tại khi đơn đang `pending`

## Bước 4. Tạo index

**Đã tạo trong file schema (4 index unique bắt buộc):** `products.skus.sku_id`, `products.skus.sku_code`, `inventory (sku_id, warehouse_id)`, `customers.email`.

**Index tối ưu (vẽ trên giấy, tạo ở giai đoạn 5):** dẫn xuất lại cho thiết kế mới theo quy tắc ESR (equality, sort, range) và đã chạy `explain()` trên mẫu.


| Index                          | Khóa                                                           | Phục vụ                    | Ghi chú                                                                                                                            |
| ------------------------------ | -------------------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `ix_orders_customer_summary`   | `customer_id`, `created_at↓`, `_id↓`, `status`, `total_amount` | **W6 (BQ1)**               | Covered. `_id` đứng trước `status` và `total_amount` để sort `(created_at, _id)` khớp thứ tự index, không có bước SORT.            |
| `ix_orders_status_date`        | `status`, `created_at`, `total_amount`                         | **W8 (BQ2)**, **W9 (BQ3)** | Equality trước, sort và range cùng trên `created_at`. `total_amount` giúp W9 covered. W8 không covered vì thiếu `_id` trong index. |
| `ix_orders_payment_due`        | `payment_due_at` (index một phần, chỉ khi field tồn tại)       | W23 hết hạn đơn            | Chỉ chứa các đơn đang chờ thanh toán.                                                                                              |
| `ix_products_category_listing` | `category_id`, `status`, `created_at↓`, `_id↓`                 | **W1**                     | Nay là index một khóa thông thường (không còn multikey).                                                                           |


Không cần index riêng cho `categories` (tối đa khoảng 500 document, cache ở ứng dụng) và `warehouses` (tối đa khoảng 100 document). W2, W7 tra theo `_id`; W3, W5 đã có index unique.

**Kế hoạch thực thi đo được** (mẫu tổng hợp 50.000 đơn, 5.000 product, 2.000 customer, trên container `mongo:8.0.32` tạm không giới hạn tài nguyên; chỉ so sánh trước và sau, không dùng để kết luận độ trễ):


| Thao tác          | Trước index                                  | Sau index                                              |
| ----------------- | -------------------------------------------- | ------------------------------------------------------ |
| W6                | `SORT > COLLSCAN`: 50.000 document để trả 20 | `PROJECTION_COVERED > IXSCAN`: 20 khóa, **0 document** |
| W8                | `SORT > COLLSCAN`: 50.000 document để trả 50 | `FETCH > IXSCAN`: 50 khóa, 50 document                 |
| W9 (cửa sổ 1 năm) | quét 50.000 document                         | 12.399 khóa, **0 document** (covered)                  |
| W1                | `SORT > COLLSCAN`: 5.000 document để trả 20  | `FETCH > IXSCAN`: 20 khóa, 20 document, không SORT     |
| W23               |                                              | `IXSCAN` index một phần                                |
| W3, W5            |                                              | `EXPRESS_IXSCAN`: 1 khóa, 1 document                   |


Hai kế hoạch "trước index" của W6 và W8 là mốc xuất phát cho giai đoạn 4 (đo trước tối ưu) và giai đoạn 5.

**Kích thước và chi phí ghi**

- Độ dài khóa đo trên mẫu 50.000 đơn (index tạo sau khi nạp): `ix_orders_customer_summary` khoảng 51 B/khóa, `ix_orders_status_date` khoảng 20 B/khóa, `ix_products_category_listing` khoảng 30 B/khóa. Ngoại suy tuyến tính lên 10M đơn cho khoảng 0,5 GB và 0,2 GB. Đây là ước lượng thô: mẫu chỉ có 2.000 customer nên nén tiền tố tốt hơn thực tế (với 500K customer khóa có thể lớn hơn); cần đo lại ở giai đoạn 3–4 trên dữ liệu thật.
- Mỗi đơn mới ghi 3 entry index lúc chèn (`_id`, `ix_orders_customer_summary`, `ix_orders_status_date`), thêm 1 nếu không phải COD (`ix_orders_payment_due`). Mỗi lần đổi `status` phải viết lại 2 entry, vì `status` nằm trong cả hai index lớn. Đây là chi phí đổi lấy W6 và W9 covered.

## Khác biệt có chủ đích so với MySQL

- Không có 9 FK. Ứng dụng giữ toàn vẹn tham chiếu và quy ước không xóa cứng.
- Không sửa dòng đơn sau khi tạo.
- MongoDB chặt hơn ở trần mảng và chuẩn hóa chữ hoa/thường (`sku_code` chữ hoa, `email` chữ thường).
- `lines[].warehouse_id` để optional (parity với cột nullable của MySQL).
- `orders.total_amount`: MongoDB ép đẳng thức `= Σ line_total` bằng validator; MySQL để là cột thường và quy ước tầng ứng dụng.
- Field chỉ có ở Mongo, không có trong ERD: `inventory.last_receipt_id` (nhập kho idempotent) và `orders.payment_due_at` (hết hạn đơn chưa thanh toán).

