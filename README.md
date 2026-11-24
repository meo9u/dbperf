# dbperf — So sánh hiệu năng MySQL và MongoDB

Bài tập lớn môn Hệ Quản trị CSDL: so sánh MySQL (InnoDB) và MongoDB (WiredTiger) trên cùng một bài toán thương mại điện tử. Xem [docs/PLAN.md](docs/PLAN.md) để biết kế hoạch từng giai đoạn và [CLAUDE.md](CLAUDE.md) để biết các quy ước của dự án.

## Setup

Làm lần lượt 6 bước dưới đây để có hai DB chạy và chứa dữ liệu mẫu.

### Bước 1: tạo file môi trường

Sao chép file môi trường mẫu rồi sửa giá trị nếu cần (file `.env` nằm trong `.gitignore`, không bao giờ commit):

```bash
cp .env.example .env
```

### Bước 2: copy dữ liệu vào `seed/data/`

**Dữ liệu không nằm trong git.** Thư mục `seed/data/` bị `.gitignore` chặn hoàn toàn, nên sau khi clone repo nó rỗng. **Phải tự copy dữ liệu vào `seed/data/`** (xin bộ dữ liệu từ nơi chia sẻ chung của nhóm) theo đúng cấu trúc sau:

```
seed/data/
├── mysql/          9 file CSV: category, product, sku, warehouse, inventory,
│                   customer, orders, order_detail, payment  (đuôi .csv)
├── mongodb/        6 file JSONL: categories, warehouses, customers, products,
│                   inventory, orders  (đuôi .jsonl)
└── manifest.json   số dòng kỳ vọng và checksum của từng file
```

Nếu thiếu `manifest.json` hoặc thiếu file trong `mysql/` và `mongodb/` thì bước nạp sẽ báo lỗi không đọc được file.

### Bước 3: khởi động Docker

Kiểm tra file compose rồi chạy các dịch vụ:

```bash
docker compose config -q
docker compose up -d
```

### Bước 4: kiểm tra stack đã chạy

```bash
docker compose ps
```

`mysql` và `mongodb` phải chuyển sang `healthy` trong vài chục giây. `mongodb-keyfile-init`, `mongodb-init` và `mongodb-schema-init` là các container chạy một lần (tạo keyfile cho replica set, chạy `rs.initiate()`, rồi tạo collection và index); chúng phải ở trạng thái `Exited (0)`, không được khởi động lại liên tục.

Kiểm tra tài nguyên (tùy chọn). Mức dùng bộ nhớ so với giới hạn 4 GiB mỗi container:

```bash
docker stats --no-stream
```

`docker stats` chỉ hiện CPU so với tổng CPU của máy chứ không phải so với giới hạn đã cấu hình. Để xác nhận giới hạn 2 CPU đã áp dụng, xem `NanoCpus` của container (`2000000000` tương ứng 2 CPU):

```bash
docker inspect dbperf-mysql --format '{{.HostConfig.NanoCpus}}'
docker inspect dbperf-mongodb --format '{{.HostConfig.NanoCpus}}'
```

### Bước 5: nạp dữ liệu

Mỗi lệnh xóa sạch bảng (hoặc collection), nạp lại từ file, rồi đối chiếu số lượng với `seed/data/manifest.json`. Lệnh trả mã thoát 1 nếu có chỗ lệch:

```bash
docker compose --profile seed run --rm seed-mysql
docker compose --profile seed run --rm seed-mongodb
```

Chỉ đối chiếu số lượng mà không nạp lại:

```bash
docker compose --profile seed run --rm seed-mysql /loaders/verify_mysql.sh
docker compose --profile seed run --rm seed-mongodb /loaders/verify_mongodb.sh
```

### Bước 6: kiểm tra logic dữ liệu

Bước nạp chỉ kiểm tra số lượng. Để kiểm tra dữ liệu có hợp lý hay không (tham chiếu hợp lệ, tổng tiền khớp, thứ tự thời gian, trạng thái đơn khớp trạng thái thanh toán, tồn kho giữ chỗ khớp các đơn đang chờ...), chạy **cả hai** lệnh sau. Bên chạy sau sẽ tự so kết quả với bên chạy trước:

```bash
docker compose --profile seed run --rm seed-check-mysql
docker compose --profile seed run --rm seed-check-mongodb
```

## Bắn tải trực tiếp vào DB bằng k6

Image `dbperf-k6:local` được build kèm `xk6-sql`, driver MySQL của nó và `xk6-mongo`. Container chạy trên mạng `dbperf-net` nên kịch bản kết nối thẳng tới `mysql:3306` và `mongodb:27017`, không đi qua API trung gian. Kịch bản đặt trong `benchmark/scenarios/` (mount chỉ đọc vào `/scripts`); kết quả ghi vào `benchmark/results/` (mount ghi được vào `/results`). Container k6 bị giới hạn 2 CPU và 2 GB RAM, cần ghi lại cùng với kết quả.

Build image và kiểm tra các extension đã nhúng:

```bash
docker compose --profile loadtest build k6
docker compose --profile loadtest run --rm k6 version
```

Chạy một kịch bản (ví dụ sau khi thêm `benchmark/scenarios/mysql.js`), lưu tóm tắt ra host:

```bash
docker compose --profile loadtest run --rm k6 run --summary-export=/results/baseline/mysql.json /scripts/mysql.js
```

Extension MongoDB do cộng đồng duy trì và có ít chức năng hơn extension SQL; hãy xác nhận các thao tác nó hỗ trợ trước khi thiết kế kịch bản. Mọi phiên bản (xk6, k6, các extension) được pin trong `infra/k6/Dockerfile` nên build lại ra cùng một binary; khi nâng phiên bản, build lại và kiểm tra `k6 version`. Mật khẩu chứa `@ : / %` phải được URL-encode trong `.env` vì được ghép thẳng vào `MYSQL_DSN` và `MONGO_URI`. Khi build, xk6 in cảnh báo `conflicting k6 versions` do `go.mod` của `xk6-mongo`; các extension vẫn nạp bình thường.

## Dừng

```bash
docker compose down       # dừng container, giữ lại volume dữ liệu
docker compose down -v    # xóa luôn volume dữ liệu, không khôi phục được
```

