# Kế hoạch: tạo dataset cho schema MySQL và MongoDB từ H&M

Dùng bộ **H&M Personalized Fashion Recommendations** (Kaggle) làm nguồn chính ("xương sống"): đây là nguồn duy nhất vừa có danh mục sản phẩm (~105K article), khách hàng (~1,37M) vừa có giao dịch thật (~32M dòng, 2018-09 đến 2020-09), nên dòng đơn hàng và sản phẩm cùng một danh mục. Số liệu hơi lệch nhau giữa các nguồn thứ cấp.

- H&M (Kaggle): https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations ; bản mô tả khác: https://relbench.stanford.edu/datasets/rel-hm
- Giấy phép: "Non-Commercial & Academic" theo RelBench, chưa xác minh trên Kaggle. Cần tài khoản Kaggle. Dữ liệu thô không được commit vào repo.

Phần H&M không có (trạng thái đơn, thanh toán, địa lý, tên khách) lấy phân bố hoặc dữ liệu từ các nguồn bổ trợ, hoặc sinh bù:

- Olist (CC BY-NC-SA 4.0): https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce ; bản sao https://github.com/infobarbosa/dataset-olist
- UCI Online Retail II (CC BY 4.0): https://archive.ics.uci.edu/dataset/502/online+retail+ii
- vietnamese-provinces-database (MIT): https://github.com/thanglequoc/vietnamese-provinces-database
- Faker `vi_VN`: https://faker.readthedocs.io/en/master/locales/vi_VN.html

## Ánh xạ từng bảng: nguồn nào, sinh bù chỗ nào

Ký hiệu: **[SRC]** lấy trực tiếp từ nguồn · **[DER]** suy ra bằng quy tắc xác định từ dữ liệu nguồn · **[GEN]** không có trong nguồn nên phải sinh.

Các tên cột H&M ngoài `t_dat`, `customer_id`, `article_id`, `price`, `sales_channel_id` (đã thấy trong code loader bên thứ ba) **chưa xác minh**; Bước 0 sẽ kiểm tra.

| Bảng | Cột | Cách có dữ liệu |
|---|---|---|
| category | name | [SRC] một cấp của cây phân cấp trong `articles.csv` (index group → product group → product type); category giờ là danh mục phẳng, không còn `parent` và `slug`. |
| | status, created_at | [DER] `active`; created_at = ngày giao dịch sớm nhất của category |
| product | name, description | [SRC] `prod_name`, `detail_desc` (gom theo `product_code`) |
| | category_id | [DER] theo product type |
| | status, created_at, updated_at | [DER] active nếu có bán trong N tháng cuối, ngược lại inactive; thời gian từ giao dịch đầu tiên |
| sku | sku_code | [SRC] `article_id` (đệm số 0, unique) |
| | variant_attributes (JSON) | [SRC] màu, hoa văn… từ các cột article (vd `{"color":..., "pattern":...}`) |
| | current_price | [DER] giá giao dịch gần nhất của article, nhân hệ số quy đổi tiền tệ (Bước 0) |
| | status, updated_at | [DER] như product |
| warehouse | city | [SRC] tỉnh/thành từ `vietnamese-provinces-database` (MIT), chọn ~10 tỉnh lớn |
| | address | [SRC] tên phường/xã thật + [GEN] số nhà/tên đường |
| | name, status | [GEN] "Kho {tỉnh}", `active` |
| inventory | sku_id × warehouse_id | [GEN] mỗi sku có 1–3 kho |
| | quantity_reserved | [DER] tổng quantity của các dòng thuộc đơn `pending` gán cho kho đó |
| | quantity_on_hand | [DER] tỉ lệ với số bán 90 ngày cuối của sku, luôn ≥ reserved |
| customer | customer_id (nguồn) | [SRC] `customers.csv` (hash ẩn danh) → gán id số nguyên 1..N |
| | full_name, phone | [GEN] Faker `vi_VN` + bộ tạo số di động VN (không có trong nguồn nào; ví dụ phone của Faker không đúng định dạng VN thật) |
| | email | [GEN] duy nhất, domain dành riêng (`example.com`) |
| | address | [SRC] phường/xã thật từ `vietnamese-provinces-database` + [GEN] số nhà/tên đường (cột NOT NULL) |
| | created_at | [DER] ngày mua đầu tiên trừ độ lệch xác định |
| orders | customer_id, created_at | [SRC] H&M không có khái niệm đơn: **gom giao dịch theo (customer_id, t_dat, sales_channel_id) thành một đơn** (giả định phải ghi rõ trong tài liệu) |
| | giờ trong ngày | [GEN] `t_dat` chỉ có ngày; giờ lấy từ phân bố theo giờ của Olist (`order_purchase_timestamp`) |
| | status | [DER] phân bố từ Olist (`delivered` ≈ 97%, shipped, canceled, unavailable, các trạng thái trung gian) ánh xạ về 5 giá trị; `returned` lấy từ tỉ lệ hoá đơn "C" của Online Retail II; đơn cũ bắt buộc ở trạng thái cuối, `pending/shipped` chỉ ở đơn gần ngày cuối dataset |
| | shipping_recipient_name/phone | [DER] = tên/phone của customer |
| | shipping_address | [SRC] địa chỉ của customer chọn từ phường/xã thật + [GEN] số nhà |
| | total_amount | [DER] bằng SUM(line_total) của đơn (cột thường ở MySQL, quy ước tầng ứng dụng; MongoDB ép đúng đẳng thức này bằng validator). Không còn `subtotal_amount`, `shipping_fee`, `discount_amount` |
| order_detail | sku_id, quantity | [SRC] mỗi dòng giao dịch H&M là 1 đơn vị; gộp các dòng cùng (đơn, article) thành quantity |
| | unit_price_snapshot | [SRC] `price` của giao dịch × hệ số quy đổi (giá thật tại thời điểm mua) |
| | warehouse_id | [DER] kho gần nhất theo tỉnh của khách; NULL cho đơn `cancelled` |
| | line_total | **không ghi** (GENERATED) |
| payment | payment_method | [DER] Olist `payment_type` ánh xạ (credit_card→credit_card, boleto→bank_transfer, voucher→e_wallet, debit_card→credit_card). **`cod` không có trong nguồn nào** → [GEN] tỉ lệ giả định, ghi rõ |
| | amount | [DER] = total_amount của đơn |
| | status | [DER] từ status đơn: delivered→success, cancelled→failed/pending, returned→refunded, pending→pending. Thanh toán thất bại rồi thử lại: [GEN] tỉ lệ nhỏ giả định (nguồn không có) |
| | created_at | [DER] theo mốc thời gian của đơn |

Tổng kết phần **buộc phải sinh**: thông tin định danh khách (tên, email, SĐT), số nhà/tên đường, tên kho, tồn kho gốc, giờ trong ngày, tỉ lệ `cod` và tỉ lệ thanh toán thất bại. Mọi thứ còn lại truy ngược được về nguồn.

## Các bước thực hiện

**Bước 0: Xác minh nguồn (chưa viết generator)**
- Bạn tải thủ công H&M, Olist, Online Retail II vào `seed/data/raw/` (thư mục này vào `.gitignore`); tải bộ `vietnamese-provinces-database` bản JSON/MySQL.
- Kiểm tra thực tế: tên cột `articles.csv`/`customers.csv`; **thang giá của H&M** (nghi là đã chuẩn hóa, giá trị nhỏ; nếu đúng, chọn hệ số quy đổi sang VND và ghi lại); số đơn sau khi gom (customer, ngày, kênh); giá trị thật của `order_status`, `payment_type` Olist; tỉ lệ hoá đơn "C" và `CustomerID` thiếu của Online Retail II.

**Bước 1: Phân bố tham chiếu (`seed/generators/stats.py`)**: tính một lần từ Olist và Online Retail II các bảng: tỉ lệ trạng thái, phân bố giờ trong ngày, độ trễ giữa các mốc, tỉ lệ freight/price, tỉ lệ payment_type, tỉ lệ returned. Lưu ra JSON nhỏ trong `seed/data/derived/`.

**Bước 2: Catalog (category, product, sku, warehouse)** từ `articles.csv` + provinces.

**Bước 3: Customer**: đọc `customers.csv`, gán id, sinh phần định danh bằng Faker `vi_VN` + bộ số di động VN, gán phường/xã.

**Bước 4: Order, order_detail**: đọc `transactions_train.csv` theo chunk (pandas, không thêm thư viện), gom thành đơn, gộp quantity, gán id theo thứ tự thời gian. Tham số `--customer-fraction` chọn mẫu khách bằng hash cố định của `customer_id` (để hai DB nhận đúng cùng tập, lặp lại được).

**Bước 5: Bảng phụ thuộc đơn**: status → payment → inventory (reserved/on_hand tính sau cùng từ đơn `pending`).

**Bước 6: Xuất CSV** mỗi bảng 1 file trong `seed/data/`: có sẵn id tường minh, thời gian UTC `YYYY-MM-DD HH:MM:SS`, NULL là `\N`, JSON quote đúng chuẩn, **bỏ qua** `line_total` (GENERATED); `total_amount` là cột thường nên phải ghi (bằng SUM(line_total) của đơn). Ghi `manifest.json` (số dòng, seed, tham số, checksum từng file).

**Bước 7: Kiểm chứng trên MySQL 9.7.2 thật:** nạp CSV theo thứ tự khóa ngoại rồi chạy bộ kiểm tra (số dòng khớp `manifest.json`, `orders.total_amount = SUM(order_detail.line_total)`, `quantity_reserved ≤ quantity_on_hand`, mỗi đơn có ít nhất một dòng chi tiết, `payment.amount` khớp `orders.total_amount`).

**Bước 8: Tài liệu**: `seed/README.md` (cách chạy, nguồn gốc từng cột [SRC]/[DER]/[GEN]); cập nhật `CLAUDE.md` (Commands, cấu trúc `seed/`, Open decisions đã chốt).
