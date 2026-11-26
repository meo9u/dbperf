# So sánh hiệu năng MySQL (InnoDB) và MongoDB (WiredTiger) trên một bài toán thương mại điện tử

Bài tập lớn môn Hệ quản trị cơ sở dữ liệu. Thực nghiệm chạy ngày 2026-11-25 trên một máy, mỗi cơ sở dữ liệu (CSDL) được giới hạn 2 CPU, 4 GB RAM và bộ nhớ đệm 1536 MB.

Báo cáo này tổng hợp ba báo cáo thành phần, nơi có thêm chi tiết về cơ chế và số liệu từng lần chạy: `docs/bao-cao-ket-qua-class1.md` (truy vấn quét dữ liệu), `docs/bao-cao-ket-qua-class2-search.md` (tìm kiếm sản phẩm dưới tải), `docs/bao-cao-ket-qua-class2-checkout.md` (đặt hàng dưới tải). Số liệu gốc nằm trong `benchmark/results/`.

---

## Tóm tắt

Hai CSDL được mô hình hóa cho cùng một nghiệp vụ, nạp cùng 1.000.000 đơn hàng, rồi đo ở hai nhóm nghiệp vụ trước và sau khi tối ưu. Kết quả giống nhau giữa hai CSDL được kiểm tra trước khi ghi bất kỳ số liệu nào.

| Nhóm nghiệp vụ | Kết quả chính |
|---|---|
| **Truy vấn quét dữ liệu** (5 truy vấn báo cáo) | Ở baseline MongoDB nhanh hơn ở 3/5 truy vấn (không phải join). Sau tối ưu MySQL tăng 1,2x–10x ở cả 5 truy vấn, MongoDB chỉ tăng ở q5 (1,6x) và q4 (1,2x); kết quả là MySQL nhanh hơn ở 3/5 (q1, q4, q5), MongoDB nhỉnh hơn ở q2, q3 (1,1x và 1,3x). |
| **Tìm kiếm sản phẩm** (đọc, 16 VU) | Sau khi làm mới thống kê hai bên ngang nhau (320 và 325 TPS). Tối ưu: MySQL 2,2x (688 TPS), MongoDB 1,55x (505 TPS). |
| **Đặt hàng** (ghi, giao dịch, 32 VU) | MongoDB cao hơn khoảng 3,4 lần (2.680 và 790–800 checkout/giây); các index tối ưu làm MongoDB chậm đi 18–30% khi bão hòa, MySQL không bị ảnh hưởng đo được. |

Bốn bài học phương pháp quan trọng hơn bất kỳ con số đơn lẻ nào:

1. **Index có thể làm chậm.** Với `status = 'delivered'` chiếm 96% đơn hàng, index bắt đầu bằng `status` không loại được dòng nào; MongoDB q3 chậm gần gấp đôi và MySQL chọn nhầm plan.
2. **Thống kê của MySQL quyết định kết luận.** Chạy `ANALYZE TABLE` làm baseline thay đổi 1,7–2,4x ở hai nơi (q5 và tìm kiếm); mọi mức tăng tốc phải tính trên baseline đã làm mới thống kê.
3. **Phải đo trên toàn bộ phân phối tải, không chọn vài trường hợp tay.** Một gợi ý `JOIN_ORDER` nhanh hơn trên 7 trường hợp mẫu nhưng chậm hơn 25% trên toàn bộ tải.
4. **Tối ưu đọc có chi phí ghi** và chi phí này khác nhau giữa hai CSDL: ghi thêm trường dẫn xuất và index làm MongoDB mất 18–30% thông lượng ghi, còn MySQL tự duy trì cột sinh.

---

## 1. Mục tiêu và phạm vi

Mô hình hóa cùng một miền thương mại điện tử trên MySQL và MongoDB, nạp cùng một bộ dữ liệu lớn, đo cùng một tập nghiệp vụ trước và sau khi tối ưu, và báo cáo độ trễ, thông lượng (TPS), mức dùng tài nguyên và dung lượng. Đây là đồ án học tập, không phải hệ thống sản xuất.

Phạm vi đã thực hiện: thiết kế hai schema tương đương; nạp và kiểm tra dữ liệu; 5 truy vấn quét dữ liệu (class 1); 2 luồng nghiệp vụ dưới tải đồng thời (class 2: tìm kiếm và đặt hàng); tối ưu bằng index và viết lại truy vấn; đo lại. Không thực hiện (chỉ khuyến nghị ở mục 9): sao chép/HA, bộ nhớ đệm ngoài, phân vùng, sharding, lưu trữ lạnh, phân quyền.

## 2. Mô hình dữ liệu và dữ liệu thực nghiệm

Hai mô hình biểu diễn cùng 9 thực thể nghiệp vụ (khách hàng, danh mục, sản phẩm, SKU, kho, tồn kho, đơn hàng, dòng hàng, thanh toán):

| | MySQL (quan hệ) | MongoDB (tài liệu) |
|---|---|---|
| Cấu trúc | 9 bảng, chuẩn 3NF, khóa ngoại | 6 collection: `products` nhúng `skus[]`; `orders` nhúng `lines[]`, `payments[]`, `shipping` |
| Toàn vẹn | khóa ngoại, CHECK, cột sinh `line_total` | validator `$jsonSchema` + biểu thức; toàn vẹn tham chiếu do ứng dụng giữ |
| Thuộc tính biến thể | cột JSON `sku.variant_attributes` | đối tượng nhúng |
| Chênh lệch có chủ đích | CSDL chỉ ép `line_total`; `orders.total_amount` (tổng các dòng) là quy ước ứng dụng | validator `$expr` ép cả `line_total` lẫn tổng đơn; `_id` là ObjectId do máy khách sinh |

Dữ liệu (bộ `bigdata-final`, nạp giống hệt ở hai CSDL): 50.000 khách, 19 danh mục, 4.000 sản phẩm, 20.000 SKU, 20 kho, 321.410 dòng tồn kho, **1.000.000 đơn**, 3.117.170 dòng hàng, 1.038.361 thanh toán. 96,05% đơn ở trạng thái `delivered`, điều này quyết định nhiều kết quả ở class 1. Bộ kiểm tra logic của dữ liệu (31 kiểm tra) cho kết quả giống hệt ở hai CSDL; có 562 thanh toán có trạng thái không khớp trạng thái đơn, sẵn có trong dữ liệu và giống nhau ở hai bên.

## 3. Phương pháp và môi trường

| Mục | Giá trị |
|---|---|
| Phiên bản | MySQL 9.7.2 (LTS), MongoDB 8.0.32 chạy single-node replica set `rs0` (để có giao dịch đa document) |
| Tài nguyên mỗi CSDL | 2 CPU, 4 GB RAM; bộ nhớ đệm **1536 MB mỗi bên** (InnoDB buffer pool và WiredTiger cache), đặt tường minh |
| Công cụ tải | Grafana k6 với `xk6-sql` và `xk6-mongo`, gọi thẳng CSDL; container k6 giới hạn 2 CPU, 2 GB |
| Độ bền ghi, cô lập | mặc định của từng CSDL: MySQL fsync mỗi commit (`flush_log_at_trx_commit=1`, `sync_binlog=1`), REPEATABLE READ; MongoDB write concern `majority`, snapshot isolation trong giao dịch |
| Class 1 | mỗi truy vấn chạy riêng, 1 lần đầu ghi riêng + 11 lần đo, lấy p50 và p95; thời gian đo trong phiên CSDL |
| Class 2 | k6 vòng kín, 45 giây mỗi mức, 4–64 VU (tìm kiếm) và 4–32 VU (đặt hàng); độ trễ là thời gian một yêu cầu (một lượt tìm kiếm hoặc một checkout) |

Các quy tắc giữ cho phép so sánh công bằng:

- **Kết quả giống hệt trước khi đo:** mỗi cặp truy vấn phải cho cùng kết quả ở hai CSDL (`diff` rỗng); tìm kiếm so 60 yêu cầu cố định; checkout so nội dung đơn sau 40 yêu cầu cố định và các aggregate nghiệp vụ. Các bước tối ưu còn phải giống kết quả baseline.
- **Cùng chuỗi tham số cho hai CSDL** (bộ sinh số giả ngẫu nhiên theo `(VU, lần lặp)`).
- **Baseline đã làm mới thống kê** (`ANALYZE TABLE`) vì thống kê cũ làm thay đổi plan (mục 8).
- **Điểm nghẽn được kiểm tra:** khi tải, CPU của CSDL chạm trần (175–197% trên 200%) còn k6 chỉ dùng 5–88%, nên số đo phản ánh CSDL, không phải công cụ tải.
- **Mỗi phép đo được tách theo bước** (`baseline`, chỉ thêm index, thêm viết lại) để biết phần cải thiện đến từ đâu.
- **Ghi (checkout):** nạp lại dữ liệu trước mỗi mức tải, rồi kiểm tra toàn vẹn (số đơn mới đúng bằng số checkout thành công, các bất biến tồn kho và thanh toán của bộ kiểm tra seed).

## 4. Class 1: năm truy vấn quét dữ liệu

Năm truy vấn báo cáo trên toàn bộ đơn hàng: q1 doanh thu theo tháng, q2 top 20 SKU bán chạy năm 2019, q3 doanh thu theo danh mục, q4 top 20 khách hàng, q5 báo cáo tồn kho thấp theo kho ("doanh thu" chỉ tính đơn `delivered`, giả định của nhóm chưa được giảng viên xác nhận).

Độ trễ p50 (ms), baseline sau `ANALYZE` → sau tối ưu:

| Truy vấn | MySQL | MongoDB | Nhanh hơn sau tối ưu |
|---|---|---|---|
| q1 | 412 → 342 (1,2x) | 539 → 560 (1,0x) | MySQL 1,6x |
| q2 | 4.194 → 1.608 (2,6x) | 1.456 → 1.486 (1,0x) | MongoDB 1,08x |
| q3 | 9.079 → 2.744 (3,3x) | 2.201 → 2.150 (1,0x) | MongoDB 1,28x |
| q4 | 1.833 → 197 (9,3x) | 1.306 → 1.099 (1,2x) | MySQL 5,6x |
| q5 | 197 → 19 (10x) | 272 → 173 (1,6x) | MySQL 9x |

**Vì sao baseline khác nhau.** MongoDB nhanh hơn ở q2, q3, q4 vì đơn và dòng hàng nằm chung một document: không có join. MySQL phải join `orders` với `order_detail` rồi tra `sku`, `product`, `category` cho từng dòng, tức khoảng 10 triệu lần tra index ở q3, và gom nhóm *sau* join. MongoDB gom nhóm theo SKU hoặc khách *trước* rồi mới `$lookup` (19.000 hoặc 50.000 lần thay vì hàng triệu). MySQL chỉ nhanh hơn ở q1 (một bảng, không join, dòng `orders` hẹp hơn document MongoDB).

**Vì sao tối ưu có hiệu quả khác nhau.** MySQL được lợi vì chi phí nằm ở số lần tra và thứ tự join, cả hai đều can thiệp được:
- index phủ `(status, customer_id, total_amount)` cho q4 cho phép gom nhóm theo luồng, không cần bảng tạm (10x);
- cột sinh `quantity_available` có index biến điều kiện biểu thức của q5 thành quét khoảng 4.037 mục (10x);
- viết lại q2, q3 để gom `order_detail` theo SKU trước rồi mới join giảm số lần tra khoảng 100–150 lần (2,6x và 3,3x).

MongoDB gần như không được lợi từ index ở q1–q3 vì chi phí nằm ở việc `$unwind` và gom nhóm 1,5–3 triệu dòng hàng, không phải ở việc tìm. Cái giúp được là trường lưu sẵn `quantity_available` cho q5 và covered query cho q4. Biện pháp còn lại là tiền tổng hợp (khuyến nghị ở mục 9).

**Index làm chậm.** Ở bước chỉ thêm index (truy vấn chưa đổi): MongoDB q1/q2/q3 chậm 1,3x/1,4x/1,8x vì planner chọn index `status` rồi `FETCH` gần một triệu document ngẫu nhiên, đắt hơn quét tuần tự (đo lại riêng: ép quét collection `$natural` cho q3 1.950 ms so với 3.723 ms). MySQL q2, q3 chậm 1,26x vì optimizer chọn sai index và đổi thứ tự join; ước lượng của nó là 496 nghìn dòng cho điều kiện thực tế khớp 960.500 dòng, và histogram không sửa được điều này (thí nghiệm riêng). Cách xử lý thực tế là viết lại truy vấn và gợi ý optimizer.

## 5. Class 2: tìm kiếm sản phẩm (đọc dưới tải)

Mỗi yêu cầu chọn một danh mục (có trọng số theo kích thước), tùy chọn lọc theo màu (50%), khoảng giá (60%), từ khóa tên (30%), rồi phân trang. Thông lượng (TPS) ở 16 VU:

| | Baseline đã làm mới thống kê | Chỉ thêm index | Sau tối ưu | Tăng |
|---|---|---|---|---|
| MySQL | 320 (p95 190 ms) | 711 | 688 (p95 92 ms) | **2,2x** |
| MongoDB | 325 (p95 101 ms) | 346 | 505 (p95 99 ms) | **1,55x** |

Ở 64 VU: MySQL 299 → 659 TPS (p95 603 → 204 ms), MongoDB 286 → 479 TPS (p95 596 → 400 ms).

- **MySQL:** tối ưu là index, không cần viết lại. Cột sinh `color` (cùng biểu thức nên truy vấn cũ tự dùng) bỏ việc phân tích JSON cho từng SKU, và index phủ `(product_id, status, color, current_price, sku_code)` tránh đọc dòng gốc. Yêu cầu lọc nhanh từ 16,4 ms xuống 3,5 ms. Gợi ý `JOIN_ORDER` làm giảm 25% thông lượng.
- **MongoDB:** index một mình không đủ (đọc 1.456 thay vì 4.000 document nhưng thời gian không đổi), vì điều kiện màu và giá nằm sau `$unwind`. Thêm `$match` với `$elemMatch` *trước* `$unwind` cho phép index multikey lọc đúng từng phần tử mảng: yêu cầu lọc chỉ đọc 29 document.
- **Thống kê:** lần đo baseline đầu của MySQL thấp hơn lần sau tới 1,7x chỉ vì `ANALYZE TABLE` làm đổi plan (từ "product trước, bảng tạm, sắp xếp" sang "quét SKU theo thứ tự, dừng sau 20 dòng"). Nếu lấy baseline đầu làm mốc, mức tăng của MySQL bị thổi phồng thành 3,8x.
- Không dùng: phân trang keyset (chỉ tới trang 7, `OFFSET` gần như không tốn) và `FULLTEXT`/`$text` (khớp theo từ nên cho kết quả khác).

## 6. Class 2: đặt hàng (ghi, giao dịch đa bảng / đa document)

Mỗi checkout đặt một đơn `pending` kèm một thanh toán `pending` với 1–3 dòng hàng lấy từ đơn mẫu thật, tăng `quantity_reserved` của từng (SKU, kho) trong cùng một giao dịch. 50% yêu cầu dùng các đơn "nóng" chứa SKU bán nhiều nhất để tạo tranh chấp khóa. Thông lượng (checkout/giây, hai lần đo baseline) và p95 (ms):

| VU | MySQL TPS | MySQL p95 | MongoDB TPS | MongoDB p95 |
|---|---|---|---|---|
| 4 | 513 / 643 | 9,7 / 8,4 | 1.751 / 1.930 | 3,0 / 2,8 |
| 8 | 576 / 758 | 18,0 / 12,6 | 2.691 / 2.624 | 3,8 / 5,0 |
| 16 | 691 / 772 | 32,0 / 31,2 | 2.700 / 2.688 | 46,8 / 49,4 |
| 32 | 790 / 800 | 58,8 / 69,6 | 2.680 / 2.672 | 67,7 / 70,2 |

- **MongoDB cao hơn khoảng 3,4 lần ở 32 VU** và bão hòa từ 8 VU (CPU 195%); MySQL còn tăng dần (CPU 175–200%). Một checkout MongoDB là một `insert` (đơn, dòng hàng, thanh toán chung một document) cộng một `updateOne` mỗi dòng; một checkout MySQL là 7–10 câu lệnh qua mạng cộng một commit bền (hai lần đồng bộ đĩa). Độ trễ p95 ở 32 VU của hai bên gần nhau (~60–70 ms) dù p50 khác xa (MongoDB ~4 ms, MySQL ~35 ms).
- **Tranh chấp khác bản chất.** MySQL dùng khóa bi quan: giao dịch tới sau chờ và không bị hủy (0 deadlock, 0 thử lại). MongoDB dùng khóa lạc quan: giao dịch ghi trùng document bị hủy ngay bằng `WriteConflict` và ứng dụng phải thử lại. Tỉ lệ thử lại tăng theo tải, từ 0,0% (4 VU) lên 0,7% (32 VU), và 1–2 checkout mỗi lần chạy ở 32 VU hết 3 lượt thử.
- **Tối ưu thứ tự khóa và gộp lệnh `INSERT`: không có tác dụng đo được** ở cả hai CSDL; ở MongoDB xung đột là hủy ngay chứ không chờ nên thứ tự lấy khóa không ngăn được, ở MySQL không có deadlock nào để ngăn.
- **Chi phí ghi của index:** áp dụng cả hai bộ index tối ưu, MongoDB giảm 18% (8 VU), 22% (16 VU), 30% (32 VU) thông lượng, p95 ở 32 VU tăng từ ~68 lên 82 ms. Nguồn gồm hai index ba trường trên `orders` và việc phải ghi thêm `quantity_available` (cùng index của nó) ở mỗi dòng hàng; chưa tách phần nào lớn hơn. MySQL không thay đổi đo được vì cột sinh được tự duy trì và chi phí index nhỏ so với chi phí commit.
- **Độ nhiễu:** hai lần baseline của MySQL chênh tới 25–32% ở 4–8 VU và 1% ở 32 VU; MongoDB chênh ≤ 2% từ 8 VU. Chỉ các chênh lệch vượt khoảng này được xem là thật.

Công cụ cũng đặt ra giới hạn cần biết (mục 10): `xk6-sql` không có API giao dịch, phiên MongoDB của `xk6-mongo` không trả kết quả cập nhật và không tạo được Decimal128 hay ObjectId mới từ JavaScript. Hai điều chỉnh để đo được: cộng 100.000 vào tồn kho mỗi lần nạp lại (nếu không, CSDL nhanh hơn làm cạn các hàng ít tồn kho sớm hơn, nên hai bên không còn làm cùng khối lượng việc) và nới tạm validator `orders.schema_version` từ `int` sang `int` hoặc `long`.

## 7. Tài nguyên và dung lượng

**CPU dưới tải.** Cả hai CSDL chạm trần CPU được cấp (175–197% trên 200%) ở mọi luồng nghiệp vụ; nút thắt là CPU của CSDL, không phải đĩa hay bộ nhớ, vì dữ liệu nóng nằm gọn trong bộ nhớ đệm 1536 MB.

**Bộ nhớ.** Với cấu hình mặc định ban đầu, bộ nhớ đệm không bằng nhau (InnoDB 128 MB, WiredTiger 1536 MB), nên MySQL chỉ giữ khoảng một phần tư dữ liệu trong bộ nhớ trong khi MongoDB giữ gần hết; đã đặt cả hai bằng 1536 MB trước khi đo. Container dùng ~3,1–3,3 GB trên 4 GB sau nhiều lần chạy (con số cgroup, gồm cả bộ đệm tệp của hệ điều hành nên không dùng để so sánh trực tiếp).

**Dung lượng dữ liệu sau khi nạp (1.000.000 đơn).**

| | Dữ liệu | Index | Tổng |
|---|---|---|---|
| MySQL (InnoDB, không nén) | 349 MB | 215 MB | **564 MB** |
| MongoDB (WiredTiger, nén snappy) | 259 MB trên đĩa (876 MB chưa nén) | 58 MB | **~317 MB** |

Mô hình nhúng làm dữ liệu chưa nén của MongoDB lớn hơn (876 MB so với 349 MB) nhưng nén tốt, nên dung lượng trên đĩa nhỏ hơn. (Kích thước hiện tại của collection MongoDB trên đĩa lớn hơn số trên vì các lần xóa và nạp lại nhiều lần chưa được nén gọn; số trong bảng là của lần nạp mới.)

**Chi phí của index tối ưu.**

| | Trước | Sau | Tăng |
|---|---|---|---|
| MySQL index (`orders`, `order_detail`, `inventory`) | 19,5 + 172,8 + 12,0 MB | 66,6 + 213,9 + 20,5 MB | +97 MB |
| MongoDB index (`orders`, `inventory`) | 25,8 + 24,2 MB | 72,6 + 25,9 MB | +48 MB |

Nạp lại dữ liệu khi đã có index chậm hơn: MySQL 47 → 58 giây, MongoDB 32 → 85 giây (mỗi trường hợp đo một lần).

## 8. Thảo luận

**Khi nào mô hình nào hợp.**

| Đặc điểm của nghiệp vụ | Phù hợp hơn | Bằng chứng trong thực nghiệm |
|---|---|---|
| Đọc cả đơn cùng dòng hàng, thanh toán, địa chỉ (không join) | MongoDB (nhúng) | q2, q3, q4 baseline; checkout 3,4x |
| Gom nhóm trên khóa có thứ tự sẵn, phục vụ hoàn toàn từ index phủ | MySQL | q4 197 ms so với 1.099 ms; q5 19 so với 173 ms |
| Tìm kiếm có lọc nhiều thuộc tính trên catalog nhỏ | MySQL nhỉnh hơn sau tối ưu | 688 so với 505 TPS ở 16 VU |
| Ghi đồng thời lên cùng hàng tồn kho | MongoDB về thông lượng; MySQL về độ đơn giản (chờ thay vì thử lại) | 2.680 so với 790 checkout/giây; retry 0,7% so với 0 |
| Báo cáo quét hàng triệu dòng hàng | cả hai cần tiền tổng hợp | chi phí còn lại ở q2/q3 là đọc và gom 1,5–3 triệu dòng |

**Bài học phương pháp.**
1. **Độ chọn lọc quyết định giá trị của index.** Điều kiện chiếm 96% dữ liệu không đáng đưa vào đầu một index; index chỉ có ích khi phủ cột hoặc cho thứ tự sẵn có.
2. **Optimizer cần được kiểm tra bằng số liệu thực** (`EXPLAIN ANALYZE`, `explain("executionStats")`): MySQL ước lượng sai gấp đôi số dòng và chọn nhầm index; MongoDB không có thống kê phân phối nên không thấy chi phí `FETCH` tích lũy.
3. **Thống kê là một biến thí nghiệm.** Hai lần thống kê cũ làm baseline MySQL sai (q5: 475 ms so với 197 ms; tìm kiếm: 189 so với 320 TPS).
4. **Gom nhóm trước, join sau** là thao tác then chốt ở cả hai CSDL (MongoDB làm tự nhiên, MySQL phải viết lại truy vấn).
5. **Đo cả chi phí ghi của tối ưu đọc**; chi phí này bất đối xứng giữa hai CSDL.

## 9. Khuyến nghị (chưa triển khai, chưa đo)

Các mục dưới đây là gợi ý cho hệ thống thật, rút ra từ kết quả nhưng **không** được thực nghiệm kiểm chứng trong đồ án.

- **Tiền tổng hợp báo cáo (bảng tóm tắt, hoặc `$merge` trong MongoDB)** cho q1, q3: chi phí còn lại của chúng là đọc và gom hàng triệu dòng, thứ mà index không giảm được; đổi lại dữ liệu có thể cũ và cần quy trình cập nhật.
- **Bộ nhớ đệm ngoài (ví dụ Redis) cho trang danh mục và kết quả tìm kiếm phổ biến:** tìm kiếm bị giới hạn bởi CPU của CSDL ở 16 VU, nên giảm số yêu cầu tới CSDL sẽ giảm tải trực tiếp.
- **Phân vùng (MySQL) hoặc sharding (MongoDB) theo thời gian hoặc khách hàng, và lưu trữ lạnh đơn cũ:** các truy vấn báo cáo quét toàn bộ `orders`; với quy mô 10 triệu đơn trở lên, chi phí quét tăng tuyến tính.
- **Sao chép và chuyển đổi dự phòng (HA), kèm ProxySQL cho MySQL:** thực nghiệm chạy một nút nên `w: majority` tầm thường; với nhiều nút, chi phí đồng bộ của checkout chưa biết và cần đo lại.
- **Phân quyền và mã hóa:** thực nghiệm dùng tài khoản gốc trong môi trường cô lập; hệ thống thật cần vai trò tối thiểu và mã hóa đường truyền, lưu trữ.

## 10. Hạn chế

1. **Quy mô:** 1 triệu đơn, nhỏ hơn mục tiêu 10 triệu của đề; dữ liệu nóng nằm trong bộ nhớ đệm nên chênh lệch do đọc đĩa chưa lộ ra.
2. **Một máy, một nút:** hai CSDL chạy lần lượt trên cùng một máy với k6; không có sao chép, độ trễ mạng, hay nhiều nút.
3. **Tải tổng hợp:** phân phối yêu cầu (danh mục, bộ lọc, đơn mẫu, khoảng 43% yêu cầu tìm kiếm cho kết quả rỗng) do nhóm tự dựng; checkout đo thông lượng và tranh chấp khóa, không đo hành vi hết hàng (đã cộng tồn kho) và không có luồng đọc song song.
4. **Độ nhiễu:** mỗi cấu hình đo một đến hai đợt; chênh lệch dưới ~25% ở MySQL mức tải thấp hoặc dưới ~10% ở MongoDB không kết luận được.
5. **Công cụ:** `xk6-sql` không có API giao dịch (chạy `START TRANSACTION` và `COMMIT` trên cùng một kết nối, đã kiểm tra); `xk6-mongo` không trả kết quả cập nhật trong phiên và gửi mọi số nguyên thành `int64`. Bật `interpolateParams` chỉ cải thiện MySQL tối đa ~7%, nên không quyết định kết quả.
6. **Độ bền theo mặc định của từng CSDL**, nên so sánh TPS ghi phản ánh cấu hình an toàn mặc định chứ không phải cùng một mức bền tuyệt đối.
7. **Giải thích nguyên nhân là suy luận từ plan và số đo;** chỉ một số giả thuyết được kiểm chứng riêng (`$natural` so với index, histogram, `interpolateParams`). Ví dụ nguyên nhân chính xác của đuôi p95 của MongoDB ở 16–32 VU và việc hint làm chậm MySQL chưa được tách bạch.
8. **Giả định "doanh thu = đơn `delivered`"** là giả định của đồ án; dữ liệu có sẵn 562 thanh toán không khớp trạng thái đơn.

## 11. Kết luận

Không có CSDL nào thắng tuyệt đối. MongoDB có lợi thế rõ khi nghiệp vụ đọc và ghi trọn một thực thể tổng hợp (đơn hàng cùng dòng hàng): ít join hơn ở baseline và thông lượng ghi cao hơn khoảng 3,4 lần. MySQL được lợi nhiều nhất từ tối ưu vì optimizer, index phủ, cột sinh và việc viết lại truy vấn cho phép can thiệp vào chính chi phí chủ yếu của nó, và đạt thông lượng tìm kiếm cao hơn sau khi tối ưu. Điều quyết định hơn cả lựa chọn công nghệ là phương pháp: kiểm tra kết quả giống nhau, làm mới thống kê, tách từng bước tối ưu, đo trên toàn bộ phân phối tải, và tính cả chi phí ghi của mỗi index.

---

## Phụ lục A. Tái lập thực nghiệm

Điều kiện: Docker, Docker Compose, tệp `.env` (xem `.env.example`) và dữ liệu trong `seed/data/`. Chi tiết lệnh ở `CLAUDE.md`.

```
docker compose up -d
docker compose --profile seed run --rm seed-mysql && docker compose --profile seed run --rm seed-mongodb
docker compose --profile seed run --rm seed-check-mysql && docker compose --profile seed run --rm seed-check-mongodb
docker compose --profile loadtest build k6

# Class 1 (xem docs/bao-cao-ket-qua-class1.md, mục 10)
python3 benchmark/run_class1.py --phase baseline_analyzed --query-phase baseline --db both
python3 benchmark/optimization.py apply
python3 benchmark/run_class1.py --phase optimized --db both
python3 benchmark/compare.py

# Class 2 tìm kiếm (xem docs/bao-cao-ket-qua-class2-search.md, mục 8)
python3 benchmark/run_class2.py --scenario search_products --phase baseline_r2 --db both
python3 benchmark/optimization.py apply --set search
python3 benchmark/run_class2.py --scenario search_products --phase optimized --variant optimized --db both

# Class 2 đặt hàng (xem docs/bao-cao-ket-qua-class2-checkout.md, mục 7)
python3 benchmark/run_checkout.py --phase baseline_checkout --db both --levels 4,8,16,32 --duration 45s
```

## Phụ lục B. Cấu trúc kết quả

| Đường dẫn | Nội dung |
|---|---|
| `benchmark/results/{baseline,baseline_analyzed,idx,optimized,...}/` | class 1: `result.tsv`, `explain.*`, `timing.json`, `meta.json` |
| `benchmark/results/<phase>/load/` | class 2: `summary.json` từng mức VU, `summary.tsv`, `meta.json`, plan mẫu |
| `benchmark/results/comparison.tsv`, `load_comparison.*.tsv` | bảng so sánh các phase |
| `queries/{mysql,mongodb}/{baseline,optimized}/` | truy vấn class 1 |
| `benchmark/scenarios/` | kịch bản k6 (`search_products`, `checkout`) và tham số dùng chung |
| `schema/{mysql,mongodb}/optimization/` | index, cột dẫn xuất và script hoàn nguyên |
| `docs/bao-cao-ket-qua-*.md` | ba báo cáo thành phần |
