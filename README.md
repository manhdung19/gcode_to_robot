# Draw Robot — Từ ảnh chụp đến nét vẽ của robot

**Biến một bức ảnh thành bản phác thảo và để cánh tay robot Fairino FR5 vẽ lại trên giấy.**

Draw Robot kết hợp xử lý ảnh, mô hình ONNX, công cụ tạo G-code và điều khiển robot bằng Python. Đây là hành trình triển khai dự án, từ thao tác chụp hoặc tải ảnh lên đến khi robot thực hiện từng nét vẽ.

## 🏆 Dấu ấn của dự án

Một cột mốc đáng tự hào: dự án đã có cơ hội xuất hiện trên báo và trên trang **FPT University Quy Nhơn**, đưa những nét vẽ của robot đến gần hơn với người xem và các bạn học sinh yêu công nghệ.

- **Trên báo:** Bài [Hơn 1.300 học sinh Gia Lai trải nghiệm các dự án ứng dụng công nghệ](https://baogialai.com.vn/hon-1300-hoc-sinh-gia-lai-trai-nghiem-cac-du-an-ung-dung-cong-nghe-post577725.html), đăng ngày **18/01/2026** trên **Báo Gia Lai điện tử**, đưa tin về sự kiện tại Trường Đại học FPT cơ sở Quy Nhơn. Bài viết có nhắc đến hoạt động **vẽ tranh bằng cánh tay robot** cùng các trải nghiệm công nghệ dành cho học sinh.
- **Trên trang trường:** [Xem bài đăng của FPT University Quy Nhơn trên Facebook](https://www.facebook.com/share/p/19dhcPDEpa/).

Từ những lần thử nghiệm đường đi của bút đến việc giới thiệu sản phẩm trước mọi người, đây là một dấu mốc đáng nhớ trong hành trình thực hiện Draw Robot.

## Sơ đồ luồng hoạt động

![Sơ đồ Draw Robot: tiếp nhận ảnh, xử lý bằng ONNX, tạo sketch, xuất G-code và điều khiển robot vẽ](docs/images/draw-robot-workflow.jpg)

*Sơ đồ tổng thể gồm hai giai đoạn: xử lý ảnh đầu vào (Data Input Processing) và thực thi trên robot (Robotic Execution).*

**Ảnh đầu vào → Bản phác thảo → G-code → Lệnh di chuyển → Robot vẽ trên giấy.**

## 1. Từ ảnh đầu vào đến file G-code

Các bước dưới đây mô tả quy trình xử lý ảnh trong sơ đồ dự án:

| Bước | Thành phần | Công việc thực hiện |
| --- | --- | --- |
| 1 | Camera / Upload | Người dùng chụp ảnh hoặc tải ảnh có sẵn lên hệ thống. |
| 2 | Web UI | Giao diện web tiếp nhận ảnh đầu vào. |
| 3 | Preprocessing | Cắt ảnh về kích thước 300 × 300 và chuẩn hóa dữ liệu cho mô hình. |
| 4 | ONNX Model | Xử lý ảnh bằng mô hình `v3/model.onnx`. |
| 5 | Postprocessing | Hậu xử lý kết quả thành bản phác thảo thang xám (grayscale sketch). |
| 6 | Web Result | Hiển thị kết quả để người dùng xem và tải ảnh PNG. |
| 7 | DrawingBotV3 | Chuyển bản phác thảo thành các đường vẽ và xuất tọa độ dưới dạng file G-code. |

File G-code là đầu vào cho chương trình điều khiển robot. Phần web, mô hình ONNX và DrawingBotV3 là các thành phần trong luồng tổng thể; script `gcode_to_robot(2.2).py` đảm nhiệm giai đoạn đọc G-code và điều khiển FR5.

## 2. Từ G-code đến chuyển động của robot

Luồng thực thi trong [`gcode_to_robot(2.2).py`](gcode_to_robot%282.2%29.py):

1. **Chuẩn bị thực thi:** Sau khi kết nối và cấu hình robot, hàm `execute_gcode()` khởi chạy luồng giám sát torque, đọc file G-code, tạo canvas OpenCV và gửi lệnh đưa robot về vị trí Home đã đặt trong mã.
2. **Phân tích từng dòng:** `parse_gcode_line()` tách mã lệnh cùng các giá trị `X`, `Y`, `Z`, `F`, bỏ qua dòng trống và chú thích trong ngoặc. Các trục không được ghi trong lệnh di chuyển giữ giá trị trước đó.
3. **Chuyển đổi vị trí đầu bút:** `gcode_to_robot_pos()` giữ tọa độ `X`, `Y` theo G-code, gán hướng đầu công tác cố định và chuyển `Z` thành hai mức: `Z <= 0` để hạ bút xuống `DRAWING_Z`, `Z > 0` để nhấc bút lên `LIFT_Z`.
4. **Hiển thị đường vẽ:** `gcode_to_canvas()` đổi tọa độ sang pixel. Cửa sổ OpenCV cập nhật đường đi được ra lệnh, trạng thái bút, số đoạn vẽ, tiến độ và torque. Đây là hình dung từ G-code, không phải ảnh phản hồi từ giấy vẽ.
5. **Robot thực hiện nét vẽ:** Với `G0` và `G1`, chương trình gửi `robot.MoveL()` đến vị trí đích. Tốc độ được chọn theo trạng thái đang vẽ, di chuyển khi nhấc bút hoặc chuyển trạng thái bút.
6. **Theo dõi trong khi chạy:** `monitor_torque()` đọc mô-men xoắn của sáu khớp qua `GetJointTorques(1)`, với khoảng nghỉ 0,1 giây giữa các lần đọc. Dữ liệu được hiển thị trên canvas và ghi ra console.
7. **Kết thúc lượt vẽ:** Chương trình dừng giám sát torque, giữ cửa sổ kết quả để xem. Sau khi nhấn phím trong cửa sổ OpenCV, chương trình gửi lệnh về Home, đóng kết nối RPC và đóng cửa sổ.

### Các lệnh G-code được xử lý

| Lệnh | Hành vi trong script hiện tại |
| --- | --- |
| `G0`, `G1` | Cập nhật vị trí và gửi chuyển động tuyến tính bằng `MoveL`. |
| `G28` | Gửi lệnh về vị trí Home được đặt sẵn trong chương trình. |
| `G21`, `G90` | Ghi nhận trên console; chương trình sử dụng tọa độ tuyệt đối theo mm. |
| `F` | Được phân tích nhưng chưa dùng để đặt tốc độ robot; tốc độ lấy từ cấu hình trong mã. |

## Công nghệ sử dụng

- **Fairino FR5 & Fairino Python SDK:** thực thi chuyển động và đọc torque của robot.
- **Python 3:** phân tích G-code và điều phối quá trình vẽ.
- **OpenCV & NumPy:** tạo canvas, biểu diễn đường vẽ và hiển thị trạng thái.
- **ONNX Model & Web UI:** xử lý ảnh và hiển thị bản phác thảo trong luồng tổng thể.
- **DrawingBotV3:** chuyển bản phác thảo thành G-code.

## Chạy chương trình điều khiển robot

### Chuẩn bị

- Cài Python 3, OpenCV, NumPy và Fairino Python SDK phù hợp với robot.
- Chuẩn bị file G-code từ DrawingBotV3.
- Kết nối máy tính với bộ điều khiển FR5 và cấu hình hệ tọa độ dụng cụ, hệ tọa độ làm việc phù hợp với bộ gá bút và mặt giấy thực tế.

```bash
python -m pip install opencv-python numpy
```

### Cấu hình trong mã

Trong `gcode_to_robot(2.2).py`, cần kiểm tra các mục sau trước khi chạy:

| Mục | Nội dung cần thiết lập |
| --- | --- |
| `robot = Robot.RPC(...)` | Bật dòng khởi tạo kết nối và thay bằng IP thực tế của robot. Dòng này hiện đang bị comment nên biến `robot` chưa được khởi tạo. |
| `gcode_file` | Thay đường dẫn trong khối `if __name__ == "__main__":` bằng file G-code cần vẽ. |
| `tool`, `user` | Chọn đúng hệ tọa độ dụng cụ và hệ tọa độ làm việc đã hiệu chuẩn. |
| `DRAWING_Z`, `LIFT_Z` | Đặt độ cao tiếp xúc giấy và độ cao nhấc bút. |
| `WP_RX`, `WP_RY`, `WP_RZ`, `p_home` | Kiểm tra hướng đầu bút và vị trí Home theo bố trí thực tế. |
| `vel`, `robot.SetSpeed(...)` | Chọn tốc độ phù hợp cho quá trình chạy thử và vẽ. |
| `GCODE_MIN_*`, `GCODE_MAX_*` | Đặt phạm vi G-code để hiển thị đúng trên canvas; các giá trị này không giới hạn chuyển động vật lý của robot. |

### Khởi chạy

```bash
python "gcode_to_robot(2.2).py"
```

Khi chạy, cửa sổ **Robot Drawing Animation** hiển thị tiến độ và đường vẽ, còn robot thực hiện các lệnh chuyển động trên giấy. Script này gửi lệnh đến robot thật; cần hoàn tất cấu hình kết nối, tọa độ và độ cao bút trước khi khởi chạy.
