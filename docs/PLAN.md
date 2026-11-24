# Kế hoạch triển khai: So sánh hiệu năng MySQL (InnoDB) vs MongoDB (WiredTiger)

Nguồn: chuyển thể và chi tiết hóa từ `plan_demo.md`. File này là kế hoạch đầy đủ, theo dõi tiến độ theo từng giai đoạn; `CLAUDE.md` ở gốc repo là nguồn quy ước/ràng buộc làm việc (phạm vi giai đoạn hiện tại, quy ước code, quyết định còn mở).

## Mục tiêu bài toán

Mô hình hóa cùng một domain thương mại điện tử trên cả MySQL và MongoDB, nạp cùng một bộ dữ liệu lớn vào cả hai, benchmark cùng một tập truy vấn nghiệp vụ trước và sau khi tối ưu (indexing), rồi so sánh latency, TPS, mức dùng tài nguyên và dung lượng đĩa. Sản phẩm bàn giao: source code, script dữ liệu, báo cáo cuối và slide bảo vệ. Đây là đồ án học thuật, **không** phải hệ thống production.

## Công nghệ sử dụng

| Hạng mục | Lựa chọn |
|---|---|
| RDBMS | MySQL (InnoDB), pinned to the 9.7 LTS line |
| NoSQL | MongoDB 6.0+ (WiredTiger) |
| Hạ tầng | Docker & Docker Compose |
| Giám sát | Prometheus, `mysqld_exporter`, `mongodb_exporter`, Grafana |
| Sinh dữ liệu | Python (Faker, Pandas, `multiprocessing`/`asyncio`) |
| Load testing | Grafana k6 (chốt ngày 2026-10-28), gọi thẳng DB qua `xk6-sql` và `xk6-mongo` |

## Chú giải trạng thái

`[ ]` chưa bắt đầu · `[~]` đang thực hiện · `[x]` hoàn thành

---

## Giai đoạn 1: Chuẩn bị hạ tầng & đào sâu lý thuyết — `[x]`

**Mục tiêu:** có một stack local chạy được kèm giám sát, cộng với các ghi chú lý thuyết mà các giai đoạn sau cần dùng tới. *(Các file ghi chú lý thuyết trong `docs/theory/` đã bị xóa khỏi repo ngày 2026-10-27, vẫn còn trong lịch sử git.)*

- [x] **Lý thuyết nền tảng**
  - CAP Theorem, ACID vs BASE.
  - Kiến trúc InnoDB: Redo log, Undo log, MVCC.
  - Kiến trúc WiredTiger: Checkpointing, Journaling.
- [x] **Lý thuyết nâng cao**
  - Cơ chế khóa: row-level lock (InnoDB) vs document-level lock (WiredTiger).
  - Transaction management ở cả hai engine.
  - ~~Replication & Sharding (chỉ lý thuyết, không triển khai)~~ — bỏ qua theo quyết định của nhóm.
- [x] **Setup hạ tầng**
  - [x] Khởi tạo khung thư mục (`infra/prometheus/`, `infra/grafana/provisioning/`).
  - [x] Viết `docker-compose.yml` cho `mysql` (9.7.2 LTS) và `mongodb` (8.0.32, single-node replica set `rs0` để hỗ trợ multi-document transaction): named volume, giới hạn 2 vCPU/4GB mỗi service, healthcheck, bind cổng vào `127.0.0.1`.
  - [x] Bổ sung `prometheus` (v3.15.0), `mysqld-exporter` (v0.19.0), `mongodb-exporter` (percona, 0.53.0), `grafana` (13.2.2) vào cùng `docker-compose.yml`.
  - [x] Cấu hình Prometheus scrape cả hai exporter (`infra/prometheus/prometheus.yml`).
  - [x] Cấu hình Grafana (provisioning datasource + 2 dashboard cộng đồng: "MySQL Overview" id 7362, "MongoDB" id 12079) hiển thị metrics MySQL và MongoDB.
  - [x] Tạo `.env.example`, đảm bảo `.env` nằm trong `.gitignore`.
  - [x] Viết `README.md` hướng dẫn chạy/kiểm tra/dừng stack (database + monitoring).

**Done when:**
- `docker compose up -d` khởi động tất cả service, không container nào restart loop.
- Cả hai exporter hiện trạng thái `UP` trong Prometheus targets.
- Grafana hiển thị metrics realtime cho cả hai database.

---

## Giai đoạn 2: Thiết kế mô hình CSDL thực tiễn — `[x]`

**Mục tiêu:** có lược đồ MySQL và MongoDB tương đương về mặt nghiệp vụ, phản ánh đúng đặc trưng từng loại CSDL.

- [x] **Xác định thực thể:** Khách hàng, Sản phẩm, Biến thể sản phẩm (SKU), Tồn kho (Inventory), Đơn hàng. Lịch sử trạng thái đơn đã bị bỏ khỏi ERD ngày 2026-10-22 (xem `docs/schema/erd.md` 3.4.22).
- [x] **Thiết kế MySQL (RDBMS)** — `schema/mysql/`
  - Lược đồ chuẩn 3NF.
  - Giải quyết bài toán lưu lịch sử giá tại thời điểm mua (snapshot pricing).
  - Quản lý quan hệ Product_ID vs SKU_ID (biến thể sản phẩm).
- [x] **Thiết kế MongoDB (NoSQL)** — `schema/mongodb/`
  - *Embedding:* nhúng chi tiết item, snapshot giá, thông tin vận chuyển thẳng vào document `Order` để giảm triệt để JOIN.
  - *Referencing:* tham chiếu tới Khách hàng, Danh mục để tránh document vượt quá giới hạn 16MB.

**Done when:** DDL MySQL và validator/schema MongoDB đã review xong, hai mô hình biểu diễn được cùng một tập nghiệp vụ.

---

## Giai đoạn 3: Sinh dữ liệu lớn — `[ ]`

**Mục tiêu:** có bộ dữ liệu lớn, thực tế, giống hệt nhau trên cả hai database để benchmark công bằng.

- [x] **Xây dựng script sinh dữ liệu (Python)** — `seed/generators/`
  - Quy mô: 500.000 user, 200.000 SKU, 10.000.000+ đơn hàng (đã nâng 10 lần so với bản đầu).
  - Dữ liệu có tính phân phối thực tế (ví dụ: đợt cao điểm lễ hội có số đơn tăng đột biến).
- [ ] **Tối ưu hóa nạp liệu** — `seed/loaders/`
  - Dùng Bulk Insert (MySQL) / `insertMany` (MongoDB) đa luồng.
  - Đối chiếu đảm bảo dữ liệu hai bên khớp nhau tuyệt đối (cùng số lượng, cùng nội dung tương ứng).

**Done when:** cả hai database chứa cùng một tập dữ liệu (về số lượng và nội dung nghiệp vụ), thời gian nạp được ghi lại.

---

## Giai đoạn 4: Baseline & phân tích Query Optimizer (lý thuyết) — `[ ]`

**Mục tiêu:** đo hiệu năng hệ thống *trước khi* tối ưu, làm mốc so sánh cho Giai đoạn 5.

- [ ] **Lý thuyết Optimizer:** Cost-Based Optimizer (CBO), đọc execution plan (`EXPLAIN ANALYZE` của MySQL, `explain("executionStats")` của MongoDB).
- [~] **Khảo sát baseline:** các truy vấn nghiệp vụ đại diện đã xác định trong `docs/benchmark-operations.md` (Loại 1) — `queries/mysql/baseline/qN_*.sql`, `queries/mongodb/baseline/qN_*.js`
  - [ ] Viết các truy vấn cho mỗi DB; kết quả hai bên phải `diff` rỗng trước khi đo.
  - [ ] Chạy `EXPLAIN ANALYZE` / `explain("executionStats")` và đo độ trễ, lưu ở `benchmark/results/baseline/{mysql,mongodb}/`.
- [ ] **Bắn tải benchmark** — `benchmark/scenarios/`, kết quả lưu ở `benchmark/results/baseline/`
  - Chạy k6 (đã chốt ngày 2026-10-28) khi chưa có index, đo TPS tối đa hệ thống chịu được.
  - Quan sát Grafana để thấy CPU/RAM bị nghẽn như thế nào.

**Done when:** có số liệu latency/TPS baseline cho toàn bộ truy vấn đã chọn, trên cả hai database.

---

## Giai đoạn 5: Tối ưu hóa truy vấn & Indexing — `[ ]`

**Mục tiêu:** áp dụng index và viết lại truy vấn để cải thiện hiệu năng, đo lại và so sánh với baseline.

- [ ] **Lý thuyết Indexing:** B-Tree, B+Tree, Clustered Index vs Secondary Index.
- [ ] **Áp dụng kỹ thuật tối ưu** — `queries/mysql/optimized/`, `queries/mongodb/optimized/`
  - *MySQL:* Compound Index, Covering Index, quy tắc Leftmost Prefix; viết lại phân trang dùng Keyset Pagination thay vì OFFSET.
  - *MongoDB:* áp dụng quy tắc **ESR** (Equality → Sort → Range) cho Compound Index; đẩy `$match`, `$limit` lên đầu pipeline.
- [ ] **Bắn tải lại** — kết quả lưu ở `benchmark/results/optimized/`
  - Chạy lại đúng kịch bản k6 của Giai đoạn 4 trên CSDL đã tối ưu.
  - Thu thập Latency, TPS mới để đối chiếu.

**Done when:** có số liệu latency/TPS "optimized" cho đúng tập truy vấn ở Giai đoạn 4, sẵn sàng để so sánh.

---

## Giai đoạn 6: Đánh giá, trực quan hóa & báo cáo — `[ ]`

**Mục tiêu:** tổng hợp toàn bộ số liệu thành báo cáo và slide bảo vệ.

- [ ] **So sánh hiệu năng:** biểu đồ thời gian phản hồi và TPS, trước/sau tối ưu, giữa hai nền tảng.
- [ ] **So sánh tài nguyên:** dung lượng lưu trữ (disk footprint) của InnoDB vs WiredTiger (có nén).
- [ ] **Kết luận thực tiễn:** khi nào nên dùng RDBMS, khi nào nên chọn Document Store cho bài toán thương mại điện tử.
- [ ] **Hạn chế & hướng phát triển** *(chỉ phân tích và đề xuất trong báo cáo — không triển khai, xem mục "Không triển khai" trong `CLAUDE.md`)*:
  - High Availability: MySQL Replication / MongoDB Replica Set, chiến lược backup.
  - Middleware: Redis cache, Connection Pooler (ProxySQL).
  - Dữ liệu siêu lớn: Table Partitioning (MySQL), Sharding (MongoDB), cơ chế archiving.
  - Bảo mật & vận hành: RBAC, mã hóa đường truyền/lưu trữ, migration tool (Flyway/Liquibase).
- [ ] **Hoàn thiện:** đóng gói source code, script dữ liệu, xuất báo cáo cuối (`report/final-report/`) và slide bảo vệ (`report/slides/`).

**Done when:** báo cáo cuối và slide đã hoàn chỉnh, source code + script dữ liệu đã đóng gói.

---

## Quyết định còn mở

Các mục này **chưa chốt** và cần quyết định của người phụ trách trước khi giai đoạn liên quan bắt đầu; theo dõi đầy đủ tại mục "Open decisions" trong `CLAUDE.md`:

- Giới hạn tài nguyên (CPU/RAM) cho container database.
- Phiên bản Python và trình quản lý dependency (pip + `requirements.txt`, Poetry, uv...).
- Test framework, linter, formatter cho Python.
- Định dạng commit message (free-form imperative vs Conventional Commits).
- Ngôn ngữ và định dạng báo cáo cuối/ghi chú lý thuyết (Việt/Anh; Markdown/Word/LaTeX).

## Phạm vi không triển khai

Các hạng mục sau **chỉ xuất hiện dưới dạng đề xuất trong báo cáo Giai đoạn 6**, không được cài đặt thật ở bất kỳ giai đoạn nào: replication/replica set cho HA, Redis, ProxySQL, table partitioning, sharding, archiving, thiết lập RBAC/mã hóa, Flyway/Liquibase.
