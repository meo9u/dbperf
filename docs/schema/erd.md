# ERD — Mô hình thực thể e-commerce (bản nháp Giai đoạn 2)

Nguồn: phân tích thực thể/quan hệ cho 9 bảng trong [erd.dbml](erd.dbml) (bản đã đơn giản hóa, xem 3.4.22) (database-agnostic, dùng chung trước khi tách `schema/mysql` 3NF và `schema/mongodb` embedding/referencing). Tài liệu này giải thích thuộc tính từng thực thể và đánh giá thiết kế theo ACID/3NF.

## 1. Thuộc tính từng thực thể

### category
| Thuộc tính | Ghi chú |
|---|---|
| category_id (PK) | |
| name | |
| status | `ENUM('active', 'inactive')` — xem 3.4.19 |
| created_at | |

### product
| Thuộc tính | Ghi chú |
|---|---|
| product_id (PK) | |
| category_id (FK → category) | |
| name | |
| description | |
| status | `ENUM('active', 'inactive')` (gộp từ `active`/`discontinued` cũ) — xem 3.4.19 |
| created_at | |

`product` là sản phẩm ở mức khái niệm (ví dụ "Áo thun ABC"); giá và tồn kho nằm ở `sku` vì mỗi biến thể có thể khác giá/khác tồn.

### sku (biến thể sản phẩm — size, màu...)
| Thuộc tính | Ghi chú |
|---|---|
| sku_id (PK) | |
| product_id (FK → product) | |
| sku_code (unique) | mã biến thể, ví dụ `ABC-RED-M` |
| variant_attributes | JSON, ví dụ `{"color": "red", "size": "M"}` |
| current_price | giá bán hiện hành — **không** dùng để tính tiền đơn hàng cũ |
| status | `ENUM('active', 'inactive')` (gộp từ `active`/`discontinued` cũ) — xem 3.4.19 |

### warehouse
| Thuộc tính | Ghi chú |
|---|---|
| warehouse_id (PK) | |
| name | |
| address | |
| city | |
| status | `ENUM('active', 'inactive')` — xem 3.4.19 |

### inventory (tồn kho của 1 sku tại 1 warehouse)
| Thuộc tính | Ghi chú |
|---|---|
| inventory_id (PK) | unique composite (sku_id, warehouse_id) |
| sku_id (FK → sku) | |
| warehouse_id (FK → warehouse) | |
| quantity_on_hand | tồn thực tế |
| quantity_reserved | đã giữ cho đơn chưa xuất kho |
| updated_at | |

### customer
| Thuộc tính | Ghi chú |
|---|---|
| customer_id (PK) | |
| full_name | |
| address | địa chỉ của khách hàng (khác với địa chỉ giao hàng snapshot trong `orders`) |
| email (unique) | |
| phone | |
| created_at | |

### orders
| Thuộc tính | Ghi chú |
|---|---|
| order_id (PK) | |
| customer_id (FK → customer) | |
| status | `ENUM('pending', 'shipped', 'delivered', 'cancelled', 'returned')` — xem 3.4.19 |
| shipping_recipient_name, shipping_phone, shipping_address | snapshot địa chỉ tại thời điểm đặt |
| total_amount | tổng tiền đơn hàng; công thức tính xem 3.4.22 |
| created_at | thời điểm đặt đơn (không còn cột `order_date` riêng, xem 3.4.22) |

`payment_method` đã chuyển sang bảng `payment` (xem dưới) — một đơn có thể có nhiều lần thử thanh toán (thất bại rồi thử lại), nên phương thức thanh toán thuộc về từng lần thanh toán, không phải thuộc tính cố định của đơn.

### order_detail (dòng chi tiết đơn hàng)
| Thuộc tính | Ghi chú |
|---|---|
| order_detail_id (PK) | |
| order_id (FK → orders) | |
| sku_id (FK → sku) | |
| unit_price_snapshot | **snapshot** giá chốt tại thời điểm mua, **không** = `sku.current_price` — đáp ứng yêu cầu lưu lịch sử giá tại thời điểm mua trong PLAN.md. Tên, mã và biến thể của SKU không còn được snapshot (xem 3.4.22) |
| quantity | |
| line_total | = quantity × unit_price_snapshot |
| warehouse_id (FK → warehouse, nullable) | kho xuất hàng cho dòng này |

### payment (giao dịch thanh toán)
| Thuộc tính | Ghi chú |
|---|---|
| payment_id (PK) | |
| order_id (FK → orders) | 1 đơn có thể có N lần thanh toán (thử lại sau khi fail) |
| payment_method | `ENUM('credit_card', 'bank_transfer', 'cod', 'e_wallet')` — xem 3.4.19 |
| amount | số tiền của lần thanh toán này |
| status | `ENUM('pending', 'success', 'failed', 'refunded')` — **độc lập** với `order.status` (vòng đời thanh toán khác vòng đời vận chuyển) |
| created_at | |

Tách `payment` khỏi `order` để mô hình đúng bài toán transaction đa bảng kinh điển của e-commerce: tạo `order` + ghi `payment` + trừ `inventory` phải atomic cùng nhau — đúng trọng tâm lý thuyết "Transaction management" và so sánh ACID giữa InnoDB/WiredTiger của đồ án.

## 2. Sơ đồ quan hệ (cardinality)

```
category (1) ──< (N) product
product  (1) ──< (N) sku

sku       (1) ──< (N) inventory
warehouse (1) ──< (N) inventory          [sku ↔ warehouse là N-N, giải qua inventory]

customer (1) ──< (N) orders
orders   (1) ──< (N) order_detail
sku      (1) ──< (N) order_detail
warehouse(1) ──< (N) order_detail        [optional: kho xuất cho từng dòng]

orders   (1) ──< (N) payment
```

## 3. Đánh giá thiết kế

### 3.1 Về ACID

ACID chủ yếu do **storage engine + transaction boundary của ứng dụng** đảm nhiệm (InnoDB lo Atomicity/Isolation/Durability qua redo/undo log và row-lock), không phải thứ một lược đồ bảng tự thân "đạt được". Thiết kế bảng có thể hỗ trợ hoặc cản trở việc giữ ACID khi ứng dụng thao tác:

| Thuộc tính | Đánh giá trên thiết kế hiện tại |
|---|---|
| Atomicity | Ổn ở mức cấu trúc: flow checkout (trừ `inventory`, tạo `order` + `order_detail`) là các bảng độc lập, bọc được trong 1 transaction InnoDB. |
| Consistency | `not null` đã khai đủ; `CHECK` đã enforce đầy đủ cho mọi cột định lượng/tiền tệ — xem 3.4.8. `order_detail.line_total` và `order.total_amount` không còn cần CHECK tính toán vì đã là cột `GENERATED ALWAYS AS` — xem 3.4.15, 3.4.16. `order.subtotal_amount` đã bị bỏ khỏi ERD; công thức của `total_amount` cần chốt lại — xem 3.4.22. |
| Isolation | Rủi ro ở `inventory`: hai đơn hàng chốt đồng thời cùng 1 `sku_id` sẽ race trên `quantity_on_hand`/`quantity_reserved` nếu ứng dụng không dùng `SELECT ... FOR UPDATE` hoặc optimistic locking (chưa có cột `version` hỗ trợ). |
| Durability | Ngoài phạm vi schema (do InnoDB WAL đảm nhiệm) — không có vấn đề. |

Kết luận: thiết kế không vi phạm ACID. Consistency đã được củng cố đáng kể ở `schema/mysql/schema.sql`; khoảng hở còn lại chỉ là thiếu cột `version` cho optimistic locking ở `inventory` (3.3.1) — mang tính tuỳ chọn, không bắt buộc.

### 3.2 Về chuẩn 3NF

| Bảng | Verdict |
|---|---|
| category | ✓ 3NF |
| product | ✓ 3NF |
| sku | ⚠️ `variant_attributes` lưu dạng JSON — không phải 1NF chặt chẽ, nhưng là lựa chọn có chủ đích (xem 3.4.11) |
| warehouse | ✓ 3NF |
| inventory | ✓ 3NF (`quantity_on_hand`, `quantity_reserved` phụ thuộc đầy đủ vào composite `(sku_id, warehouse_id)`) |
| customer | ✓ 3NF |
| orders | ✓ 3NF; `total_amount` là dữ liệu suy diễn từ các dòng `order_detail`, công thức chưa chốt (3.4.22) |
| order_detail | ✓ `line_total` là cột `GENERATED ALWAYS AS`, không còn là dữ liệu lưu trùng độc lập nữa (3.4.15) |
| payment | ✓ 3NF |

### 3.3 Vấn đề còn tồn tại (chưa xử lý xong)

**3.3.1 — Vấn đề nhỏ, không bắt buộc sửa**

- `inventory` chưa có cột `version`/optimistic-lock, nên rủi ro Isolation đã nêu ở 3.1 vẫn chưa có giải pháp cấu trúc trong DDL — phải dựa hoàn toàn vào kỷ luật `SELECT ... FOR UPDATE` ở tầng ứng dụng.

### 3.4 Đã khắc phục

**3.4.1 — FK delete action cho dữ liệu lịch sử**

Toàn bộ FK trong `erd.dbml` đã khai `delete: restrict`, bao gồm `order_detail.sku_id`, `order_detail.order_id`, `order.customer_id`, và các FK còn lại (`product.category_id`, `sku.product_id`, `inventory.sku_id`/`warehouse_id`, `category.parent_category_id`, `order_detail.warehouse_id`, `order_status_history.order_id`, `payment.order_id`). Chặn hard `DELETE` lên bất kỳ bảng cha nào còn dòng con tham chiếu, thay vì cascade xoá hoặc để tham chiếu treo — bảo vệ lịch sử giao dịch.

**3.4.2 — Quy ước soft-delete cho `product` / `sku`** (nay mở rộng cho cả `category`, xem 3.4.13)

Vì `delete: restrict` chặn hẳn việc xoá cứng, tầng ứng dụng phải tuân theo quy ước: không bao giờ `DELETE FROM product`/`sku`; "xoá" nghĩa là `UPDATE ... SET status = 'inactive'`. Truy vấn catalog lọc theo `status = 'active'`; truy vấn lịch sử đơn (`order_detail`, báo cáo doanh thu) không lọc theo status vì đã có snapshot riêng. Mới dừng ở mức quy ước thiết kế/tài liệu, chưa có cơ chế bắt buộc tầng DB (RBAC là report-only ở Giai đoạn 6).

**3.4.3 — Khai báo `not null`/`null` tường minh**

`erd.dbml` đã khai `not null` cho mọi cột bắt buộc (mặc định DBML là nullable) và `[null]` tường minh cho các cột optional (`category.parent_category_id`, `product.description`/`brand`, `customer.phone`, `order_detail.warehouse_id`, `order_status_history.note`, `payment.transaction_ref`/`paid_at`).

**3.4.4 — Bảng lịch sử trạng thái đơn**

Đã bổ sung `order_status_history` (append-only, 1 `order` — N history), theo đúng yêu cầu PLAN.md Giai đoạn 2. **[Đã lỗi thời: bảng này đã bị bỏ khỏi ERD, xem 3.4.22.]**

**3.4.5 — Tách trạng thái thanh toán khỏi trạng thái vận chuyển**

Trước đây `order.status` gộp chung thanh toán và vận chuyển (đơn "cancelled" sau khi đã "shipped" nghĩa là gì?). Đã tách bảng `payment` với `payment.status` (pending/success/failed/refunded) riêng; `order.status` giờ chỉ còn phản ánh vòng đời tổng thể/vận chuyển.

**3.4.6 — Đã bỏ `cart`/`cart_item`**

Không nằm trong quy mô dữ liệu hay truy vấn baseline đã lên kế hoạch; `inventory` đã đảm nhiệm tốt hơn vai trò minh hoạ row-level vs document-level locking.

**3.4.7 — Đã tối ưu kiểu dữ liệu thuộc tính**

Toàn bộ cột trong `erd.dbml` đã chuyển từ kiểu generic (`integer`, `varchar`, `decimal`) sang kiểu cụ thể:
- PK/FK: `int` trong `erd.dbml` (DBML không có cách khai `unsigned` nào xuất đúng sang SQL một cách ổn định, tương tự vấn đề cú pháp nêu ở 3.4.18, nên để plain `int`); DDL thật ở `schema/mysql/schema.sql` dùng `INT UNSIGNED` (đủ dung lượng cho dữ liệu đồ án, chiếm nửa dung lượng so với `BIGINT`).
- Tiền tệ: `decimal(12,2)` cho mọi cột tiền (`current_price`, `unit_price_snapshot`, `line_total`, `subtotal_amount`/`shipping_fee`/`discount_amount`/`total_amount`, `payment.amount`) — giải quyết vấn đề thiếu precision/scale nêu ở bản trước.
- Số lượng: `order_detail.quantity` dùng `smallint` trong `erd.dbml` / `SMALLINT UNSIGNED` trong DDL thật (số lượng 1 dòng đơn luôn nhỏ); `inventory.quantity_on_hand`/`quantity_reserved` dùng `int` / `INT UNSIGNED` (tồn kho tổng có thể lớn hơn).
- Chuỗi: các cột `varchar` đã có độ dài cụ thể thay vì để trống (`email varchar(255)`, `sku_code varchar(64)`, `shipping_phone varchar(20)`, `name varchar(150)`...).
- `payment.payment_method` trước là `varchar` tự do dù đã có tập giá trị cố định trong note (`credit_card/bank_transfer/cod/e_wallet`) — nay chuyển thành enum `payment_method_type` giống các cột status khác.

**3.4.8 — `CHECK` constraint đầy đủ trong `schema/mysql/schema.sql`, kể cả 2 ràng buộc tính toán**

DBML vẫn không hỗ trợ CHECK (không đổi), nhưng DDL thật ở `schema/mysql/schema.sql` nay đã có CHECK `>= 0`/`> 0` cho mọi cột định lượng và tiền tệ: `inventory.quantity_on_hand`/`quantity_reserved`, `order_detail.quantity`/`unit_price_snapshot`, `sku.current_price`, `order.subtotal_amount`/`shipping_fee`/`discount_amount`/`total_amount`, `payment.amount`. (`order_detail.line_total` và `order.total_amount` không cần CHECK tính toán — cả hai đã chuyển sang `GENERATED ALWAYS AS`, xem 3.4.15, 3.4.16.)

**3.4.10 — Thêm `updated_at` cho `product`, `sku`, `customer`, `order`**

Cả 4 bảng nay đều có `updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`, cùng kiểu với `inventory.updated_at` đã có từ trước. Đồng nhất hoá việc theo dõi lần sửa cuối trên mọi bảng dữ liệu chính (trừ `warehouse`, `category`, `payment`, các bảng lịch sử — những bảng mà việc sửa sau khi tạo không có ý nghĩa nghiệp vụ hoặc không được phép).

**3.4.11 — `sku.variant_attributes` chuyển sang kiểu JSON**

Thay vì giữ 1 cột text tự do (đánh đổi đã chấp nhận trước đó) hoặc tách `color`/`size`/EAV, chọn phương án thứ ba: cột `JSON`, ví dụ `{"color": "red", "size": "M"}`. Không phải 1NF chặt chẽ (giá trị vẫn là một cấu trúc lồng nhau, không phải scalar), nhưng:
- Có thể filter/index theo từng thuộc tính riêng sau này qua `JSON_EXTRACT` hoặc cột generated + index, nếu Giai đoạn 5 cần.
- Đối xứng về mặt kiến trúc với phía MongoDB, nơi vốn dĩ sẽ embed các thuộc tính biến thể trực tiếp trong document — cùng một cách biểu diễn dữ liệu ở cả 2 hệ, thuận lợi khi so sánh.
- Không cần enum cố định trước tập thuộc tính (color/size) như Option A, cũng không cần bảng phụ như Option B (EAV).

Áp dụng tương tự cho `order_detail.variant_snapshot` (cùng kiểu JSON, cùng shape) để nhất quán giữa dữ liệu hiện hành và dữ liệu snapshot lịch sử. **[Đã lỗi thời: `variant_snapshot` đã bị bỏ khỏi ERD, xem 3.4.22.]**

**3.4.12 — Bỏ giá trị `paid` khỏi `order_status`**

`order_status` (dùng chung ở `order.status` và `order_status_history.status`; bảng sau đã bỏ, xem 3.4.22) giờ chỉ còn `pending/shipped/delivered/cancelled/returned`. Trạng thái "đã thanh toán" được suy ra từ sự tồn tại một `payment.status = success`, không cần trùng lặp ý nghĩa ở `order.status` nữa.

**3.4.13 — Thêm `status` cho `category`**

Thêm enum `category_status` (`active`/`inactive`), theo đúng mẫu `product_status`/`sku_status`/`warehouse_status`. Nhờ vậy quy ước soft-delete ở 3.4.2 giờ áp dụng được cho cả `category`: "ngừng dùng" một category nghĩa là `UPDATE category SET status = 'inactive'`, không cần (và không được phép, do `delete: restrict`) xoá cứng một category còn sản phẩm tham chiếu.

**3.4.14 — Chốt phương án cho `order.subtotal_amount`: quy ước tầng ứng dụng** **[Đã lỗi thời: `subtotal_amount` đã bị bỏ khỏi ERD, xem 3.4.22.]**

Không dùng trigger. `order.subtotal_amount` (và do đó `order.total_amount`) phải được tầng ứng dụng tính lại và ghi **trong cùng transaction** với bất kỳ `INSERT`/`UPDATE`/`DELETE` nào trên `order_detail` của đơn đó — không có gì enforce ở DB. Lý do chọn quy ước thay vì trigger: đơn giản hơn, không tốn công viết/test trigger, và đối xứng với MongoDB — bên đó cũng không có cơ chế tương đương trigger nên dữ liệu suy diễn ở cả 2 hệ đều do tầng ứng dụng đảm nhiệm giống nhau, thuận tiện cho báo cáo so sánh. Đánh đổi: rủi ro lệch dữ liệu nếu ứng dụng có bug/crash giữa chừng vẫn tồn tại, không được DB chặn lại như 2 giá trị single-row kia.

**3.4.15 — `order_detail.line_total` chuyển sang `GENERATED ALWAYS AS`**

Thay vì cột lưu trữ thường + CHECK tính toán (`chk_order_detail_line_total_calc`), `line_total` giờ là cột tính toán thật sự:
```sql
line_total DECIMAL(12,2)
  GENERATED ALWAYS AS (quantity * unit_price_snapshot) STORED
  NOT NULL COMMENT 'quantity * unit_price_snapshot'
```
Dùng `STORED` (không phải `VIRTUAL`) vì cột này được đọc thường xuyên (lịch sử đơn, báo cáo doanh thu) — tính sẵn một lần khi ghi, không phải tính lại mỗi lần đọc. Ứng dụng không còn được phép (và không cần) tự set giá trị `line_total` khi `INSERT` — MySQL tự tính, không thể lệch. `chk_order_detail_line_total` (`>= 0`) cũng bỏ theo vì giờ vô nghĩa (không thể `INSERT`/`UPDATE` trực tiếp vào cột generated).

**3.4.16 — `order.total_amount` cũng chuyển sang `GENERATED ALWAYS AS`** **[Công thức dưới đây đã lỗi thời: `subtotal_amount`, `shipping_fee`, `discount_amount` đã bị bỏ khỏi ERD, xem 3.4.22.]**

Cùng lý do và cùng cách làm như 3.4.15:
```sql
total_amount DECIMAL(12,2)
  GENERATED ALWAYS AS (subtotal_amount + shipping_fee - discount_amount) STORED
  NOT NULL
```
Bỏ `chk_order_total_amount_calc` (không còn cần, cột tự tính). **Giữ lại** `chk_order_total_amount CHECK (total_amount >= 0)` — ràng buộc này *không* suy ra được từ 3 CHECK còn lại (`subtotal_amount >= 0`, `shipping_fee >= 0`, `discount_amount >= 0`) vì `discount_amount` vẫn có thể lớn hơn `subtotal_amount + shipping_fee`, khiến `total_amount` âm; CHECK này chặn đúng trường hợp đó. Sau thay đổi này, `order` chỉ còn `subtotal_amount` (3.4.14) là dữ liệu suy diễn do tầng ứng dụng tự giữ đồng bộ — mọi giá trị suy diễn single-row khác trong toàn schema đều đã là cột generated.

**3.4.17 — Gộp mọi `status`/`payment_method` vào một bảng `lookup_value` dùng chung ("one true lookup table")**

Theo yêu cầu cụ thể: domain chỉ 2 trạng thái (`product.status`, `sku.status`, `warehouse.status`, `category.status`) gộp chung thành `type = 'active_inactive'` (bỏ tên riêng như `discontinued`, dùng `active`/`inactive` thống nhất); domain >2 trạng thái giữ `type` riêng (`order_status` 5 giá trị, `payment_status` 4 giá trị, `payment_method` 4 giá trị). Tất cả nằm trong 1 bảng `lookup_value (lookup_value_id, type, code)`, unique `(type, code)`; mọi cột status/payment_method trong các bảng khác đổi từ `ENUM` sang `*_id INT UNSIGNED` FK vào bảng này.

Đây là pattern **"one true lookup table" (OTLT)** — một anti-pattern được ghi nhận rõ trong tài liệu thiết kế CSDL (ví dụ *SQL Antipatterns* của Bill Karwin), chọn có chủ đích theo yêu cầu, không phải sơ suất. Đánh đổi đã kiểm chứng thực tế trên MySQL: FK chỉ đảm bảo `status_id` tồn tại trong `lookup_value`, **không** đảm bảo đúng `type` mong đợi của cột đó — chạy thử `UPDATE order SET status_id = <lookup_value_id của 1 dòng type='payment_method'>` thành công, không bị DB chặn (MySQL CHECK không hỗ trợ subquery nên không thể validate chéo bảng `type` này). Tầng ứng dụng phải tự đảm bảo luôn lookup đúng `type` khi set các cột `*_id` này — xem thêm 3.3.1.

Lợi ích đánh đổi lại: 1 bảng duy nhất thay vì 7 bảng lookup riêng lẻ, và domain `order_status` không còn bị khai lặp ở cả `order` lẫn `order_status_history` như khi dùng `ENUM` (ENUM của MySQL không dùng chung được giữa các cột).

**3.4.18 — Sửa cú pháp DBML: `delete: restrict` phải khai ở `Ref:` độc lập, không khai inline trên cột**

Khai `column [ref: > table.column, delete: restrict]` **parse được** nhưng sai: parser DBML thật coi `delete` là "custom setting" chung chung, nên giá trị `restrict` không có dấu nháy sẽ bị từ chối (`Custom setting 'delete' must be a string or a color literal`); nếu thêm dấu nháy (`delete: "restrict"`) thì qua được bước parse nhưng khi export SQL, action bị **âm thầm bỏ qua** — FK sinh ra không có `ON DELETE RESTRICT` nào cả. Cú pháp đúng duy nhất là khai `Ref:` như một statement độc lập: `Ref: child.fk_column > parent.pk_column [delete: restrict]`.

Đã viết lại toàn bộ 11 quan hệ FK trong `erd.dbml` sang dạng `Ref:` độc lập ở cuối file (cột chỉ còn giữ `not null`/`null`/`note`). Đã kiểm chứng bằng `@dbml/cli` (`dbml2sql erd.dbml --mysql`) thật — parse sạch, cả 11 FK đều sinh đúng `ON DELETE RESTRICT`.

**3.4.19 — Revert 3.4.17: bỏ `lookup_value`, quay lại `ENUM` riêng từng bảng**

Sau khi cân nhắc lại trade-off đã ghi ở 3.4.17/3.3.1, quyết định **không giữ** pattern OTLT nữa: lỗ hổng type-safety đã kiểm chứng thực tế (FK vào `lookup_value` không chặn được việc gán sai `type`, ví dụ gán một `payment_method` row vào `order.status_id`) được xem là rủi ro thật, không chỉ lý thuyết, trong khi lợi ích đổi lại (ít bảng hơn) không đáng với một đồ án có quy mô domain nhỏ (chỉ 7 giá trị trạng thái, 4 bảng 2-trạng-thái).

Đã bỏ hẳn bảng `lookup_value` (và `INSERT` seed data của nó). Mọi cột `*_status_id`/`payment_method_id` quay lại thành cột `ENUM` khai trực tiếp trên từng bảng, đúng tập giá trị đã dùng khi còn là lookup table:
- `category.status`, `product.status`, `sku.status`, `warehouse.status`: `ENUM('active', 'inactive')`.
- `order.status`, `order_status_history.status`: `ENUM('pending', 'shipped', 'delivered', 'cancelled', 'returned')`.
- `payment.payment_method`: `ENUM('credit_card', 'bank_transfer', 'cod', 'e_wallet')`.
- `payment.status`: `ENUM('pending', 'success', 'failed', 'refunded')`.

Đánh đổi ngược lại: MySQL không có kiểu `ENUM` dùng chung đặt tên như Postgres, nên `order_status` phải khai lặp giá trị ở cả `order` và `order_status_history` (chấp nhận được — chỉ là một danh sách hằng số lặp lại ở 2 chỗ, không phải logic). Đổi lại, mỗi cột giờ được DB enforce đúng domain tại thời điểm `INSERT`/`UPDATE` — không còn khả năng gán nhầm `type` như với `lookup_value`. Trong `erd.dbml`, các giá trị dùng chung (`active_inactive_status`, `order_status_enum`, `payment_status_enum`, `payment_method_enum`) được khai bằng `Enum` block của DBML để tránh lặp lại danh sách giá trị trong file model, dù bản SQL thật (`schema/mysql/schema.sql`) vẫn phải lặp theo giới hạn cú pháp `ENUM` của MySQL.

**3.4.20 — Không có entity `admin`/nhân viên vận hành**

Một phiên bản `erd.dbml` sớm (viết cùng lúc với `docs/SRS.md`, trước khi nhánh này hợp nhất với `main`) có bảng `admin` (tài khoản nhân viên, dùng để ghi nhận ai cập nhật catalog/inventory/trạng thái đơn). Bản hiện tại không còn bảng này. Giữ nguyên, không khôi phục: xác thực/ủy quyền nhân viên (RBAC) được CLAUDE.md xếp hẳn vào mục "Out of scope" — chỉ là khuyến nghị report-only ở Giai đoạn 6, không triển khai ở bất kỳ giai đoạn nào của đồ án. Model hiện tại coi mọi thay đổi catalog/inventory/trạng thái là hành động của tầng ứng dụng, không gắn với một actor `admin` cụ thể trong schema.

**3.4.21 — Không có cột VAT/thuế**

Tương tự 3.4.20, phiên bản sớm đó có `order_detail.vat_rate_snapshot` (immutable sau khi tạo). Bản hiện tại không còn cột này. Giữ nguyên: mục tiêu đồ án là so sánh hiệu năng/ACID giữa MySQL và MongoDB trên cùng một workload, không phải mô phỏng đầy đủ nghiệp vụ kế toán/hoá đơn. Thuế, nếu cần cho báo cáo, có thể coi là một phần đã gộp trong `discount_amount`/`shipping_fee` hiện có hoặc tính ở tầng ứng dụng — không cần một cột snapshot thuế riêng trong schema.

**3.4.22 — Đơn giản hóa ERD: bỏ 1 bảng và nhiều thuộc tính**

`erd.dbml` được thu gọn từ 10 xuống 9 bảng. Những gì đã bỏ hoặc đổi:

| Bảng | Thay đổi | Hệ quả |
|---|---|---|
| `order_status_history` | **Bỏ cả bảng** | `orders.status` là nguồn duy nhất về trạng thái; không còn audit trail và không còn truy vấn "đơn nằm ở trạng thái X bao lâu". |
| `category` | Bỏ `slug`, `parent_category_id` | Danh mục phẳng, không còn cây cha-con, không còn rủi ro chu trình (3.3.1 cũ) và không còn tra category theo URL. |
| `product` | Bỏ `brand` | |
| `customer` | Thêm `address`, bỏ `password_hash` | Không còn lưu credential. |
| `orders` (trước là `order`) | Bỏ `order_date`, `subtotal_amount`, `shipping_fee`, `discount_amount`, `updated_at` | Thời điểm đặt đơn là `created_at`. |
| `order_detail` | Bỏ `product_name_snapshot`, `sku_code_snapshot`, `variant_snapshot` | Chỉ còn snapshot giá (`unit_price_snapshot`); tên, mã, biến thể của dòng đơn cũ phải lấy từ `sku`/`product` hiện hành. |
| `payment` | Bỏ `transaction_ref`, `paid_at` | Không còn ràng buộc unique trên payment và không còn thời điểm thanh toán thành công. |

Số FK giảm từ 11 xuống 9 (bỏ `category.parent_category_id` và `order_status_history.order_id`). Các mục 3.4.1, 3.4.3, 3.4.4, 3.4.8, 3.4.10, 3.4.11, 3.4.12, 3.4.14, 3.4.16 và 3.4.18 phía trên mô tả trạng thái trước thay đổi này và được giữ làm lịch sử quyết định.

**`orders.total_amount`:** ghi chú trong `erd.dbml` vẫn nêu công thức `subtotal_amount + shipping_fee - discount_amount`, nhưng ba cột đó không còn, và tổng các dòng đơn là phép tính liên hàng nên không thể là cột `GENERATED`. Cách chốt ở cả hai phía: `total_amount = Σ order_detail.line_total`. MySQL dùng cột thường kèm `CHECK (total_amount >= 0)` và quy ước tầng ứng dụng (ghi cùng transaction với mọi thay đổi trên `order_detail`, cùng cách xử lý như `subtotal_amount` trước đây, 3.4.14); MongoDB ép đẳng thức này bằng validator. Ghi chú trong `erd.dbml` cần sửa cho khớp.

**Trạng thái triển khai:** `schema/mysql/schema.sql` và `schema/mongodb/` đều đã cập nhật theo ERD này. Phía MongoDB đồng thời bỏ luồng hoàn tiền tự động (`refund_due_at`, `payments[].refund_of`); `payment.status = refunded` vẫn còn trong enum và được đặt trực tiếp lên phần tử payment.

### 3.5 Tóm tắt ưu tiên sửa

1. **Tùy chọn, không bắt buộc**: các mục ở 3.3.1 (thiếu cột `version` cho `inventory`).
2. **Đã xong**: xem mục 3.4.
