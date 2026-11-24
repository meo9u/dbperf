# Hướng dẫn build k6 với xk6-sql và xk6-mongo

Tài liệu này hướng dẫn build image Docker `dbperf-k6:local` để chạy k6 test trực tiếp vào MySQL và MongoDB, không đi qua API. Các lệnh bên dưới dùng shell (bash/zsh); trên Windows PowerShell, thay `cp` bằng `Copy-Item`.

## 1. Yêu cầu

- Git.
- Docker Desktop đang chạy với Linux containers.
- Docker Compose plugin (lệnh `docker compose`).
- Kết nối Internet trong lần build đầu để tải base image và Go modules.

Không cần cài Go hay xk6 trên máy. Dockerfile dùng `grafana/xk6` để build binary và `grafana/k6` làm image chạy.

## 2. Lấy mã nguồn và cấu hình môi trường

Clone repo rồi mở terminal tại thư mục dự án:

```bash
git clone <URL_REPOSITORY>
cd dbperf
```

Tạo `.env` từ file mẫu nếu repo chưa có file này:

```bash
cp .env.example .env
```

Mở `.env`, thay các giá trị mẫu bằng mật khẩu riêng. Ít nhất phải đặt `MYSQL_ROOT_PASSWORD`, `MONGO_ROOT_USERNAME` và `MONGO_ROOT_PASSWORD`; Compose cần các giá trị này để cấu hình kết nối nội bộ. Không commit hoặc gửi file `.env` lên Git.

## 3. Build image k6

Từ thư mục gốc của repo, chạy:

```bash
docker compose --profile loadtest build k6
```

Build lần đầu có thể mất vài phút do Go tải và biên dịch k6 cùng các extension. Image được tạo với tên `dbperf-k6:local`. Dockerfile tại `infra/k6/Dockerfile` hiện thêm các module:

- `github.com/grafana/xk6-sql`
- `github.com/grafana/xk6-sql-driver-mysql`
- `github.com/GhMartingit/xk6-mongo`

## 4. Xác nhận các extension đã được build

Lệnh này chạy trực tiếp image, không cần khởi động MySQL hay MongoDB:

```bash
docker run --rm --entrypoint /usr/bin/k6 dbperf-k6:local version
```

Kết quả cần liệt kê các module `k6/x/mongo`, `k6/x/sql` và `k6/x/sql/driver/mysql` trong phần `Extensions`.

Có thể kiểm tra image đã xuất hiện trong Docker Desktop ở mục **Images**, hoặc bằng lệnh:

```bash
docker image ls dbperf-k6
```

## 5. Chạy k6 test từ container

Các kịch bản đặt trong `benchmark/scenarios/`. Compose mount thư mục này vào container tại `/scripts` (chỉ đọc), và mount `benchmark/results/` tại `/results` (ghi được) để lưu kết quả, ví dụ `--summary-export=/results/baseline/mysql.json`. Container k6 bị giới hạn 2 CPU và 2 GB RAM.

Khởi động hai database và các bước khởi tạo schema:

```bash
docker compose up -d
docker compose ps
```

Sau khi MySQL và MongoDB sẵn sàng, chạy script. Ví dụ:

```bash
docker compose --profile loadtest run --rm k6 run /scripts/mysql.js
docker compose --profile loadtest run --rm k6 run /scripts/mongodb.js
```

Thay tên file ví dụ bằng script có thật trong `benchmark/scenarios/`. Có thể truyền thêm cờ k6 sau tên script, ví dụ `--vus 10 --duration 30s`.

## 6. Kết nối trong script

Service k6 cùng mạng Docker `dbperf-net` với hai database, do đó dùng tên service làm hostname:

- MySQL: `mysql:3306`; DSN được truyền vào biến môi trường `MYSQL_DSN`.
- MongoDB: `mongodb:27017`; URI được truyền vào biến môi trường `MONGO_URI`.

Ví dụ MySQL dùng `xk6-sql`:

```javascript
import sql from "k6/x/sql";
import mysql from "k6/x/sql/driver/mysql";

const db = sql.open(mysql, __ENV.MYSQL_DSN);

export default function () {
  db.query("SELECT 1");
}

export function teardown() {
  db.close();
}
```

Ví dụ MongoDB dùng API `xk6-mongo`:

```javascript
import mongo from "k6/x/mongo";

const client = mongo.newClient(__ENV.MONGO_URI);

export default function () {
  // Thay bằng thao tác trên database/collection và dữ liệu test của dự án.
  client.find("dbperf", "products", {});
}
```

API của `xk6-mongo` không tương đương đầy đủ với MongoDB driver thông thường. Hãy kiểm tra README/API của phiên bản được build trước khi viết workload. `xk6-mongo` hỗ trợ transaction qua `client.startSession()` (`startTransaction`, `commitTransaction`, `abortTransaction`), nhưng Session chỉ có `insert`, `findOne`, `updateOne`, `deleteOne`. Mật khẩu chứa `@ : / %` phải được URL-encode trong `.env` vì được ghép thẳng vào `MYSQL_DSN` và `MONGO_URI`. Dùng thao tác đọc/ghi có chủ đích và dữ liệu thử nghiệm; các lệnh ghi/xóa có thể thay đổi dữ liệu trong database.

## 7. Build lại sau khi thay Dockerfile

```bash
docker compose --profile loadtest build --no-cache k6
```

Sau đó chạy lại lệnh kiểm tra ở mục 4. Mọi phiên bản (xk6, k6, các extension) đã được pin trong Dockerfile nên build lại cho cùng một binary. Khi nâng phiên bản, sửa `ARG` và các `--with ...@vX` trong Dockerfile rồi commit. Lúc build, xk6 in cảnh báo `conflicting k6 versions` do `go.mod` của `xk6-mongo`; các extension vẫn nạp bình thường nên có thể bỏ qua, nhưng nên kiểm tra lại bằng mục 4 sau mỗi lần nâng phiên bản.

## 8. Tham khảo

- [Grafana k6: build custom binary với Docker](https://grafana.com/docs/k6/latest/extensions/run/build-k6-binary-using-docker/)
- [Grafana xk6-sql](https://github.com/grafana/xk6-sql)
- [Grafana xk6-sql MySQL driver](https://github.com/grafana/xk6-sql-driver-mysql)
- [GhMartingit xk6-mongo](https://github.com/GhMartingit/xk6-mongo)
