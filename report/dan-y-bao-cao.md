# Dàn ý báo cáo bài tập lớn: thiết kế và so sánh MySQL và MongoDB cho bài toán quản lý bán hàng

Tài liệu này là dàn ý của báo cáo bài tập lớn (Hệ quản trị cơ sở dữ liệu). Báo cáo gồm hai phần chính: **Phần I** thiết kế MySQL và MongoDB cho bài toán quản lý bán hàng, **Phần II** so sánh MySQL và MongoDB; kèm các phần cần có của một báo cáo hoàn chỉnh (bìa, tóm tắt, cơ sở lý thuyết, kết luận, tài liệu tham khảo, phụ lục).

Quy ước: "Nguồn" là nơi trong kho mã đã có sẵn nội dung để biên tập lại; mục **[viết mới]** chưa có nội dung; **[điền]** cần bạn cung cấp thông tin. Số trang là ước lượng cho thân bài (~62 trang).

---

## Phần mở đầu (không đánh số chương)

| Mục | Nội dung | Ghi chú |
|---|---|---|
| Trang bìa | trường, khoa, môn học, tên đề tài, giảng viên, nhóm và thành viên (MSSV), ngày nộp | **[điền]** |
| Lời cam đoan, lời cảm ơn | ngắn | tùy yêu cầu của khoa |
| Phân công công việc | bảng thành viên, nhiệm vụ, mức đóng góp | **[điền]** |
| Tóm tắt (Abstract) | 200–300 từ: bài toán, phương pháp, 3–4 kết quả chính, kết luận; có thể kèm bản tiếng Anh | lấy từ phần "Tóm tắt" của `report/bao-cao-tong-hop.md` |
| Mục lục, danh mục hình, danh mục bảng, danh mục từ viết tắt | tự sinh khi xuất | viết tắt: RDBMS, 3NF, ACID, BASE, CAP, TPS, VU, p50/p95/p99, CBO, ESR, SKU, FK, PK |

---

## Chương 1. Mở đầu (~3 trang)

1.1 Lý do chọn đề tài (hai mô hình dữ liệu; thương mại điện tử là bài toán điển hình).
1.2 Mục tiêu và câu hỏi nghiên cứu: mô hình nào hợp với nghiệp vụ nào; tối ưu bằng index và viết lại truy vấn có tác dụng gì; cái giá phải trả là gì.
1.3 Phạm vi và đối tượng: MySQL 9.7 (InnoDB), MongoDB 8.0 (WiredTiger), một máy, một nút; không triển khai HA, sharding.
1.4 Phương pháp tiếp cận: thiết kế, nạp dữ liệu, đo trước và sau tối ưu, so sánh.
1.5 Đóng góp và kết quả chính (4 bài học).
1.6 Bố cục báo cáo.

## Chương 2. Cơ sở lý thuyết (~6 trang) **[viết mới]**

2.1 Mô hình quan hệ và mô hình tài liệu; chuẩn hóa 3NF so với nhúng và tham chiếu.
2.2 ACID, BASE, CAP (chỉ phần cần dùng).
2.3 Kiến trúc InnoDB: clustered index (B+Tree), redo và undo log, MVCC, khóa dòng.
2.4 Kiến trúc WiredTiger: cây B+, journal và checkpoint, đồng thời ở mức document, snapshot isolation, nén.
2.5 Index: secondary, covering, composite, multikey, quy tắc ESR.
2.6 Bộ tối ưu truy vấn: CBO của MySQL (`EXPLAIN ANALYZE`, thống kê), chọn plan của MongoDB (`explain("executionStats")`).
2.7 Giao dịch và kiểm soát đồng thời: khóa bi quan (InnoDB) so với lạc quan (`WriteConflict`).

Nguồn khung: mục 3.1–3.3 của `docs/bao-cao-ket-qua-class1.md` đã giải thích cơ chế. Các ghi chú lý thuyết gốc ở Giai đoạn 1 đã bị xóa khỏi kho (còn trong lịch sử git, thư mục `docs/theory/`).

---

# PHẦN I. THIẾT KẾ CƠ SỞ DỮ LIỆU CHO BÀI TOÁN QUẢN LÝ BÁN HÀNG

## Chương 3. Phân tích bài toán (~4 trang)

3.1 Mô tả nghiệp vụ: danh mục, sản phẩm và biến thể (SKU), kho và tồn kho đa kho, khách hàng, đơn hàng, thanh toán.
3.2 Yêu cầu chức năng: danh sách thao tác W1–W23 (đọc: liệt kê theo danh mục, chi tiết sản phẩm, lịch sử đơn…; ghi: checkout, thanh toán, hủy, nhập kho…).
3.3 Phân tích tải: tỉ lệ đọc/ghi (~85/15), quy mô giả định (500K khách, 200K SKU, 10M đơn) và quy mô thực nghiệm (1M đơn), mục tiêu độ trễ giả định (đọc p95 ≤ 50 ms).
3.4 Giả định và ràng buộc: doanh thu chỉ tính đơn `delivered` (giả định của đồ án), xóa mềm, giá chốt tại thời điểm mua.

Nguồn: `docs/schema/mongodb-design-summary.md` (Bước 1), `docs/PLAN.md`, `docs/benchmark-operations.md`.

## Chương 4. Thiết kế cơ sở dữ liệu quan hệ (MySQL) (~8 trang)

4.1 Sơ đồ thực thể–quan hệ (ERD) và cardinality. **Hình: ERD** (xuất từ `docs/schema/erd.dbml`).
4.2 Từ điển dữ liệu: 9 bảng, mỗi bảng thuộc tính, kiểu, khóa, ràng buộc. **Bảng.**
4.3 Chuẩn hóa: kiểm tra 3NF từng bảng; một ngoại lệ có chủ đích (`sku.variant_attributes` kiểu JSON) và lý do.
4.4 Ràng buộc toàn vẹn: PK, FK (`ON DELETE RESTRICT`), CHECK, ENUM, cột sinh `line_total`, quy ước `total_amount`.
4.5 Giao dịch và ACID trong luồng đặt hàng: các bảng bị chạm, rủi ro tranh chấp ở `inventory`.
4.6 Nhật ký quyết định thiết kế (bảng: vấn đề, lựa chọn, lý do): ENUM so với bảng tra cứu, bỏ `order_status_history`, snapshot giá `unit_price_snapshot`, xóa mềm.
4.7 Chỉ mục mặc định (PK, FK, UNIQUE) và những gì cố ý chưa có (để dành cho tối ưu).

Nguồn: `docs/schema/erd.md` (mục 1–3.4), `schema/mysql/schema.sql`. DDL đầy đủ đưa vào Phụ lục A.

## Chương 5. Thiết kế cơ sở dữ liệu tài liệu (MongoDB) (~8 trang)

5.1 Quy trình thiết kế 4 bước: xác định workload, ánh xạ quan hệ, áp dụng pattern, tạo index.
5.2 Quyết định nhúng và tham chiếu: bảng 9 quan hệ (N trung bình và tối đa, quyết định, lý do); kết quả 6 collection. **Hình: sơ đồ collection (nhúng so với tham chiếu).**
5.3 Cấu trúc từng collection và kích thước document điển hình, tối đa. **Bảng field.**
5.4 Design pattern đã dùng (Extended Reference cho snapshot giá, Computed cho `line_total` và `total_amount`, Schema Versioning) và các pattern đã cân nhắc nhưng không dùng.
5.5 Kiểm soát toàn vẹn bằng validator `$jsonSchema` và `$expr`: các đẳng thức được ép.
5.6 Chiến lược index: 4 index unique bắt buộc; các index tối ưu thiết kế theo ESR.
5.7 Giao dịch đa document (single-node replica set), khóa idempotency cho checkout, kiểu dữ liệu (`Decimal128`, ObjectId).

Nguồn: `docs/schema/mongodb-design-summary.md`, `schema/mongodb/01-collections.js`, `02-indexes.js`.

## Chương 6. Đối chiếu hai thiết kế và hiện thực hóa (~5 trang)

6.1 Bảng ánh xạ 9 bảng sang 6 collection.
6.2 Những khác biệt có chủ đích: FK so với ràng buộc ứng dụng, `total_amount`, trường chỉ có ở MongoDB (`last_receipt_id`, `payment_due_at`).
6.3 So sánh định tính về thiết kế: số join cần cho các thao tác chính, chi phí nhất quán, mức độ dễ thay đổi schema.
6.4 Dữ liệu thực nghiệm: bộ `bigdata-final` (số lượng từng bảng, 96% đơn `delivered`), quy trình nạp, các kiểm tra tính hợp lý (31 kiểm tra; aggregate giống nhau ở hai CSDL), các vấn đề dữ liệu đã biết (562 thanh toán lệch trạng thái đơn…) và hạn chế quy mô.

Nguồn: `docs/schema/mongodb-design-summary.md` (mục cuối), `README.md`, `seed/checks/`, mục 2 của `report/bao-cao-tong-hop.md`.

---

# PHẦN II. SO SÁNH MYSQL VÀ MONGODB

## Chương 7. Phương pháp so sánh và môi trường thực nghiệm (~4 trang)

7.1 Hạ tầng: Docker Compose, giới hạn 2 CPU và 4 GB mỗi CSDL, cache 1536 MB cân bằng, phiên bản. **Hình: kiến trúc môi trường thực nghiệm.**
7.2 Hai nhóm nghiệp vụ: nhóm 1 truy vấn quét dữ liệu (5 truy vấn); nhóm 2 luồng dưới tải (tìm kiếm, đặt hàng).
7.3 Thước đo: p50, p95, p99, TPS, kế hoạch thực thi, CPU, dung lượng.
7.4 Quy trình đo: baseline, thêm index, viết lại truy vấn; lặp 11 lần; k6 vòng kín 4–64 VU.
7.5 Nguyên tắc công bằng: kết quả giống hệt trước khi đo, cùng chuỗi tham số, làm mới thống kê, kiểm tra điểm nghẽn, nạp lại dữ liệu và kiểm tra toàn vẹn khi ghi, độ bền mặc định.
7.6 Công cụ và giới hạn công cụ.

Nguồn: mục 3 của `report/bao-cao-tong-hop.md`, mục 2 của ba báo cáo thành phần.

## Chương 8. So sánh về mô hình và tính năng (định tính) (~3 trang)

Bảng so sánh: mô hình dữ liệu; schema và validation; toàn vẹn tham chiếu; join và `$lookup`; giao dịch và cô lập; kiểu index; ngôn ngữ truy vấn (SQL so với aggregation pipeline); nén và lưu trữ; khả năng mở rộng (replication, sharding); hệ sinh thái và công cụ. Mỗi dòng dẫn chiếu tới bằng chứng thực nghiệm ở các chương sau.

Nguồn: chương 2 và tổng hợp từ các báo cáo.

## Chương 9. Kết quả nhóm 1: truy vấn quét dữ liệu (~6 trang)

9.1 Năm truy vấn (doanh thu theo tháng, top SKU, doanh thu theo danh mục, top khách, tồn kho thấp) và tham số.
9.2 Baseline: bảng và **biểu đồ cột độ trễ** MySQL, MongoDB; vì sao MongoDB nhanh hơn ở q2–q4 (gom nhóm trước, join sau).
9.3 Tối ưu đã áp dụng: index phủ, cột sinh, trường lưu sẵn, viết lại truy vấn.
9.4 Kết quả sau tối ưu và cơ chế (bảng baseline, chỉ index, tối ưu đầy đủ).
9.5 Khi index làm chậm: độ chọn lọc 96%, plan sai, thí nghiệm histogram.
9.6 Bài học về thống kê (`ANALYZE`).

Nguồn: `docs/bao-cao-ket-qua-class1.md` (gần như nguyên vẹn, rút gọn).

## Chương 10. Kết quả nhóm 2: hiệu năng dưới tải đồng thời (~6 trang)

10.1 Tìm kiếm sản phẩm (đọc): thiết kế yêu cầu; **biểu đồ đường TPS và p95 theo VU**; tối ưu cho từng CSDL và cơ chế (cột sinh và index phủ cho MySQL, `$elemMatch` trước `$unwind` cho MongoDB); thí nghiệm hint thất bại.
10.2 Đặt hàng (ghi, giao dịch): thiết kế giao dịch ở hai CSDL (**hình: sơ đồ tuần tự checkout**); kết quả theo mức tải; tranh chấp khóa bi quan so với lạc quan (thử lại 0,0–0,7%); tối ưu thứ tự khóa không có tác dụng; chi phí ghi của index (**biểu đồ**).
10.3 Độ nhiễu và độ tin cậy.

Nguồn: `docs/bao-cao-ket-qua-class2-search.md`, `docs/bao-cao-ket-qua-class2-checkout.md`.

## Chương 11. So sánh tài nguyên và dung lượng (~3 trang)

11.1 Dung lượng sau khi nạp (dữ liệu, index) và hiệu quả nén. **Biểu đồ.**
11.2 CPU khi tải, bộ nhớ đệm và ảnh hưởng của cấu hình mặc định không cân bằng.
11.3 Chi phí của index: dung lượng, thời gian nạp, chi phí ghi.

Nguồn: mục 7 của `report/bao-cao-tong-hop.md`.

## Chương 12. Thảo luận và đánh giá (~3 trang)

12.1 Tổng hợp theo nhóm nghiệp vụ: bảng "khi nào chọn MySQL, khi nào chọn MongoDB" có dẫn chứng.
12.2 Bài học phương pháp.
12.3 Mối đe dọa với tính hợp lệ: quy mô, một máy, tải tổng hợp, độ nhiễu, giới hạn công cụ, độ bền mặc định, các giải thích nguyên nhân chưa được kiểm chứng riêng.

---

## Chương 13. Kết luận và hướng phát triển (~3 trang)

13.1 Kết luận: trả lời lần lượt các câu hỏi ở mục 1.2.
13.2 Hạn chế.
13.3 Hướng phát triển (chỉ đề xuất, chưa triển khai và chưa đo): tiền tổng hợp báo cáo, Redis cache, phân vùng và sharding, lưu trữ lạnh, replication và HA, ProxySQL, phân quyền và mã hóa, công cụ migration, mở rộng quy mô dữ liệu tới mức bộ nhớ đệm nhỏ hơn dữ liệu.

## Tài liệu tham khảo

MySQL 9.x Reference Manual (InnoDB, optimizer, `EXPLAIN ANALYZE`); MongoDB Manual (data modeling, transactions, indexes, `explain`, WiredTiger); tài liệu Grafana k6 và các extension `xk6-sql`, `xk6-mongo`; giáo trình hệ quản trị CSDL của môn học; tài liệu về mẫu thiết kế schema MongoDB. **[viết mới]** Cần bổ sung URL, phiên bản và ngày truy cập khi viết.

## Phụ lục

A. DDL MySQL (`schema/mysql/schema.sql`) và script tối ưu.
B. Validator và index MongoDB (`schema/mongodb/`).
C. ERD và các sơ đồ ở kích thước đầy đủ.
D. Năm truy vấn class 1 (SQL và pipeline, baseline và tối ưu).
E. Tóm tắt kịch bản k6 (tìm kiếm, đặt hàng) và tham số.
F. Bảng số liệu đầy đủ từng mức tải và từng lần chạy.
G. Hướng dẫn tái lập thực nghiệm (lệnh).
H. Cấu trúc kho mã nguồn và vị trí kết quả.
I. Nhật ký quyết định và giả định.
J. Nhật ký làm việc của nhóm (tùy yêu cầu).

---

## Ước lượng độ dài

Thân bài khoảng 62 trang (chương 1–13), cộng phần mở đầu và phụ lục. Nếu khoa yêu cầu ngắn hơn: gộp chương 8 vào chương 12, rút chương 2 còn 3 trang, đưa chi tiết cơ chế vào phụ lục.

## Tận dụng tư liệu hiện có

| Phần của dàn ý | Dùng lại từ |
|---|---|
| Chương 3–6 (Phần I) | `docs/schema/erd.md`, `docs/schema/mongodb-design-summary.md`, `schema/`, `README.md`: **đã đủ nội dung, cần biên tập và vẽ hình**; chưa có trong báo cáo hiện tại |
| Chương 7 | mục 3 của `report/bao-cao-tong-hop.md` |
| Chương 9, 10, 11 | ba báo cáo trong `docs/` và mục 4–7 của `report/bao-cao-tong-hop.md` |
| Chương 12, 13 | mục 8–11 của `report/bao-cao-tong-hop.md` |
| Chương 1, 2, bìa, tóm tắt | **viết mới** (tóm tắt lấy từ báo cáo hiện tại) |

`report/bao-cao-tong-hop.md` được giữ làm nguồn; khi viết đầy đủ sẽ tái cấu trúc thành `report/bao-cao-bai-tap-lon.md` theo dàn ý này.

## Hình và bảng cần chuẩn bị

Chưa có hình nào trong kho (Giai đoạn 6 yêu cầu biểu đồ):

1. ERD MySQL.
2. Sơ đồ collection MongoDB (nhúng và tham chiếu).
3. Kiến trúc môi trường thực nghiệm.
4. Sơ đồ tuần tự checkout ở hai CSDL.
5. Biểu đồ cột độ trễ class 1 (baseline và sau tối ưu).
6. Biểu đồ đường TPS và p95 theo VU cho tìm kiếm.
7. Biểu đồ đường TPS và p95 theo VU cho đặt hàng.
8. Biểu đồ chi phí ghi của index.
9. Biểu đồ dung lượng.

Số liệu để vẽ (5–9) đã có trong `benchmark/results/*/` và các file `comparison*.tsv`.

## Thông tin còn thiếu

- Thông tin trang bìa và phân công nhóm; quy định trình bày của khoa (khổ giấy, font, số trang tối đa, có cần bản tiếng Anh của tóm tắt không).
- Có giữ chương 2 (cơ sở lý thuyết) không, hay chỉ tham chiếu giáo trình.

## Bước tiếp theo

Viết nội dung từng chương theo thứ tự: Phần I (chương 3–6) trước vì chưa có trong báo cáo hiện tại, rồi chương 7 và các chương kết quả, cuối cùng chương 1, 2, 13 và phần mở đầu; vẽ hình sau cùng.
