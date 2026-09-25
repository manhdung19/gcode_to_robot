import re
import cv2
import numpy as np
# from fairino_Bao import Robot
from fairino import Robot 
# from fairino_Bao import Robot
import threading
import time

# --- KẾT NỐI ROBOT ---

# robot = Robot.RPC('172.20.10.7') ip wifi

print("Robot Fairino FR5 connected.")

# --- BIẾN TOÀN CỤC CHO TORQUE MONITORING ---
torque_monitoring = True
latest_torques = [0.0] * 6
torque_lock = threading.Lock()

# --- HÀM MONITOR TORQUE (CHẠY TRONG THREAD RIÊNG) ---
def monitor_torque():
    """Thread để đo torque liên tục"""
    global latest_torques, torque_monitoring
    
    print("🔧 Torque Monitoring Started...")
    
    while torque_monitoring:
        try:
            ret = robot.GetJointTorques(1)
            
            if ret[0] == 0:
                with torque_lock:
                    latest_torques = ret[1]
                
                # In torque (có thể bật/tắt)
                # print(f"[Torque] {time.strftime('%H:%M:%S')} - Joints: {[f'{t:.2f}' for t in latest_torques]}")
            else:
                print(f"⚠️ Torque read error: {ret[0]}")
                
        except Exception as e:
            print(f"⚠️ Torque monitoring error: {e}")
        
        time.sleep(0.1)  # Đọc mỗi 100ms
    
    print("🔧 Torque Monitoring Stopped")

# --- CẤU HÌNH WORKPIECE ---
WP_X = 4
WP_Y = 613.633
WP_Z = 0
WP_RX = 177
WP_RY = -1.993
WP_RZ = -2.885

# Cấu hình Z
# DRAWING_Z = WP_Z + 12.5
DRAWING_Z = WP_Z + 19
# Z=0 trong G-code
# DRAWING_Z = WP_Z + 12
# DRAWING_Z = WP_Z + 20      # Z=0 trong G-code
LIFT_Z = WP_Z + 80     # Z=1 trong G-code

# Thông số robot
tool = 1  # Tool 0 là Flange center
user = 6  # User 2 là Workpiece Frame (Vì ta đã cấu hình User Frame số 2)
vel = 50.0 # Giảm tốc độ để test an toàn trước
blendR = -1 # Blend radius: giúp robot đi mượt hơn ở các góc cua (quan trọng cho Polygon)
gripper_id = 1
gripper_max_time = 30000
gripper_block = 1
robot.SetSpeed(5)       

# --- THÔNG SỐ G-CODE (từ file truong-gia-binh.gcode) ---
GCODE_MIN_X = 0.0
GCODE_MAX_X = 598.0
GCODE_MIN_Y = 1.0
GCODE_MAX_Y = 600.0

GCODE_WIDTH = GCODE_MAX_X - GCODE_MIN_X    # 598mm
GCODE_HEIGHT = GCODE_MAX_Y - GCODE_MIN_Y   # 599mm

# --- CẤU HÌNH CANVAS (ĐIỀU CHỈNH ĐỂ FIT TOÀN BỘ) ---
CANVAS_WIDTH = 800
CANVAS_HEIGHT = 800
MARGIN = 50  # Lề xung quanh

# Tính SCALE để fit vào canvas
SCALE_X = (CANVAS_WIDTH - 2*MARGIN) / GCODE_WIDTH
SCALE_Y = (CANVAS_HEIGHT - 2*MARGIN) / GCODE_HEIGHT
CANVAS_SCALE = min(SCALE_X, SCALE_Y)  # Chọn nhỏ hơn để giữ tỷ lệ

# Tính OFFSET để căn giữa
OFFSET_X = MARGIN - GCODE_MIN_X * CANVAS_SCALE
OFFSET_Y = MARGIN - GCODE_MIN_Y * CANVAS_SCALE

print(f"\n{'='*60}")
print(f"📏 G-CODE SIZE:")
print(f"   X: {GCODE_MIN_X:.1f} -> {GCODE_MAX_X:.1f} (width: {GCODE_WIDTH:.1f}mm)")
print(f"   Y: {GCODE_MIN_Y:.1f} -> {GCODE_MAX_Y:.1f} (height: {GCODE_HEIGHT:.1f}mm)")
print(f"\n🖼️  CANVAS CONFIG:")
print(f"   Size: {CANVAS_WIDTH}x{CANVAS_HEIGHT} pixels")
print(f"   Scale: {CANVAS_SCALE:.4f} (1mm = {CANVAS_SCALE:.2f} pixels)")
print(f"   Offset: X={OFFSET_X:.1f}, Y={OFFSET_Y:.1f}")
print(f"{'='*60}\n")

# --- HÀM PARSE G-CODE ---
def parse_gcode_line(line):
    """Parse một dòng G-code và trích xuất lệnh + tọa độ"""
    line = line.strip()
    
    # Bỏ qua comment và dòng trống
    if line.startswith('(') or not line:
        return None
    
    # Loại bỏ comment inline
    if '(' in line:
        line = line[:line.index('(')].strip()
    
    # Tìm command (G0, G1, G28, etc.)
    command_match = re.match(r'^([GM]\d+)', line)
    if not command_match:
        return None
    
    command = command_match.group(1)

    # Trích xuất X, Y, Z, F
    x_match = re.search(r'X([-+]?\d*\.?\d+)', line)
    y_match = re.search(r'Y([-+]?\d*\.?\d+)', line)
    z_match = re.search(r'Z([-+]?\d*\.?\d+)', line)
    f_match = re.search(r'F([-+]?\d*\.?\d+)', line)
    
    return {
        'command': command,
        'X': float(x_match.group(1)) if x_match else None,
        'Y': float(y_match.group(1)) if y_match else None,
        'Z': float(z_match.group(1)) if z_match else None,
        'F': float(f_match.group(1)) if f_match else None
    }

# --- HÀM CHUYỂN ĐỔI TỌA ĐỘ G-CODE -> ROBOT ---
def gcode_to_robot_pos(x, y, z):
    """
    Chuyển đổi tọa độ G-code sang tọa độ robot
    """
    # Chuyển Z
    if z is not None:
        if z <= 0:
            robot_z = DRAWING_Z
        else:
            robot_z = LIFT_Z
    else:
        robot_z = None
    
    return [x, y, robot_z, WP_RX, WP_RY, WP_RZ]

# --- HÀM CHUYỂN ĐỔI TỌA ĐỘ CHO CANVAS ---
def gcode_to_canvas(x, y):
    """Chuyển đổi tọa độ G-code sang pixel trên canvas"""
    canvas_x = int(x * CANVAS_SCALE + OFFSET_X)
    canvas_y = int(y * CANVAS_SCALE + OFFSET_Y)
    
    # Đảm bảo trong bounds
    canvas_x = max(0, min(CANVAS_WIDTH - 1, canvas_x))
    canvas_y = max(0, min(CANVAS_HEIGHT - 1, canvas_y))
    
    return (canvas_x, canvas_y)

# --- ĐỌC VÀ THỰC THI G-CODE ---
def execute_gcode(gcode_file):
    """Đọc file G-code và điều khiển robot"""
    global torque_monitoring, latest_torques
    
    # Khởi động thread monitor torque
    torque_thread = threading.Thread(target=monitor_torque, daemon=True)
    torque_thread.start()
    
    with open(gcode_file, 'r') as f:
        lines = f.readlines()
    
    print(f"Đọc {len(lines)} dòng G-code\n")
    
    current_pos = {'X': GCODE_MIN_X, 'Y': GCODE_MIN_Y, 'Z': 1}
    pen_down = False
    
    # Tạo canvas
    canvas = np.ones((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8) * 255
    cv2.namedWindow("Robot Drawing Animation", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Robot Drawing Animation", CANVAS_WIDTH, CANVAS_HEIGHT)
    
    # Vẽ grid (mỗi 50mm)
    grid_size = 50
    for i in range(0, int(GCODE_MAX_X) + grid_size, grid_size):
        x_pixel = int(i * CANVAS_SCALE + OFFSET_X)
        if 0 <= x_pixel < CANVAS_WIDTH:
            cv2.line(canvas, (x_pixel, 0), (x_pixel, CANVAS_HEIGHT), (230, 230, 230), 1)
            cv2.putText(canvas, f"{i}", (x_pixel + 2, 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    
    for i in range(0, int(GCODE_MAX_Y) + grid_size, grid_size):
        y_pixel = int(i * CANVAS_SCALE + OFFSET_Y)
        if 0 <= y_pixel < CANVAS_HEIGHT:
            cv2.line(canvas, (0, y_pixel), (CANVAS_WIDTH, y_pixel), (230, 230, 230), 1)
            cv2.putText(canvas, f"{i}", (5, y_pixel - 2), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    
    # Vẽ khung boundary
    top_left = gcode_to_canvas(GCODE_MIN_X, GCODE_MIN_Y)
    bottom_right = gcode_to_canvas(GCODE_MAX_X, GCODE_MAX_Y)
    cv2.rectangle(canvas, top_left, bottom_right, (100, 100, 255), 2)
    cv2.putText(canvas, f"Drawing Area: {GCODE_WIDTH:.0f}x{GCODE_HEIGHT:.0f}mm", 
               (top_left[0] + 5, top_left[1] + 20),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1)
    
    drawing_canvas = canvas.copy()
    
    # Home position
    p_home = [295, 219, 325, WP_RX, WP_RY, WP_RZ]
    print("Di chuyển về Home...")
    robot.MoveL(desc_pos=p_home, tool=tool, user=user, vel=100.0, blendR=0)
    
    prev_canvas_pos = None
    line_count = 0
    processed_lines = 0  # ✅ THÊM: Đếm số dòng đã xử lý
    
    try:
        for i, line in enumerate(lines):
            parsed = parse_gcode_line(line)
            
            if parsed is None:
                continue
            
            cmd = parsed['command']
            
            # === G28: Auto Homing ===
            if cmd == 'G28':
                print(f"Line {i+1}: G28 - Auto Homing")
                robot.MoveL(desc_pos=p_home, tool=tool, user=user, vel=100.0, blendR=0)
                current_pos = {'X': GCODE_MIN_X, 'Y': GCODE_MIN_Y, 'Z': 1}
                pen_down = False
                prev_canvas_pos = None
                continue
            
            # === G21/G90: Chỉ thông báo ===
            if cmd in ['G21', 'G90']:
                print(f"Line {i+1}: {cmd}")
                continue
            
            # === G1: Set speed ===
            if cmd == 'G1' and parsed['F'] is not None and parsed['X'] is None:
                continue
            
            # === G0/G1: Move ===
            if cmd in ['G0', 'G1']:
                # Cập nhật tọa độ
                if parsed['X'] is not None:
                    current_pos['X'] = parsed['X']
                if parsed['Y'] is not None:
                    current_pos['Y'] = parsed['Y']
                if parsed['Z'] is not None:
                    current_pos['Z'] = parsed['Z']
                
                # Tạo vị trí robot
                target_pos = gcode_to_robot_pos(
                    current_pos['X'], 
                    current_pos['Y'], 
                    current_pos['Z']
                )
                
                is_pen_down = current_pos['Z'] <= 0
                
                # Vẽ lên canvas
                current_canvas_pos = gcode_to_canvas(current_pos['X'], current_pos['Y'])
                display = drawing_canvas.copy()
                
                if prev_canvas_pos is not None and pen_down and is_pen_down:
                    cv2.line(drawing_canvas, prev_canvas_pos, current_canvas_pos, (0, 0, 255), 2)
                    cv2.line(display, prev_canvas_pos, current_canvas_pos, (0, 0, 255), 2)
                    line_count += 1
                
                pen_color = (0, 255, 0) if is_pen_down else (255, 0, 0)
                cv2.circle(display, current_canvas_pos, 5, pen_color, -1)
                
                # Hiển thị thông tin
                info_text = f"Line {i+1}/{len(lines)} | G-code: X:{current_pos['X']:.1f} Y:{current_pos['Y']:.1f} | {'PEN DOWN' if is_pen_down else 'PEN UP'}"
                cv2.putText(display, info_text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                
                # ✅ THÊM: In ra console mỗi 5 dòng
                processed_lines += 1
                if processed_lines % 1 == 0:
                    print(f"📊 {info_text}")
                    with torque_lock:
                        print(f"   Torque: J1:{latest_torques[0]:.2f} J2:{latest_torques[1]:.2f} J3:{latest_torques[2]:.2f}")
                
                stats_text = f"Strokes: {line_count}"
                cv2.putText(display, stats_text, (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 0), 2)
                
                # Hiển thị TORQUE real-time
                with torque_lock:
                    torque_text = f"Torque (Nm): J1:{latest_torques[0]:.2f} J2:{latest_torques[1]:.2f} J3:{latest_torques[2]:.2f}"
                    torque_text2 = f"            J4:{latest_torques[3]:.2f} J5:{latest_torques[4]:.2f} J6:{latest_torques[5]:.2f}"
                
                cv2.putText(display, torque_text, (10, 90), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                cv2.putText(display, torque_text2, (10, 115), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
     

                # Progress bar
                progress = i / len(lines)
                bar_width = CANVAS_WIDTH - 100
                bar_x = 50
                bar_y = CANVAS_HEIGHT - 30
                cv2.rectangle(display, (bar_x, bar_y), 
                            (bar_x + int(bar_width * progress), bar_y + 20), 
                            (0, 200, 0), -1)
                cv2.rectangle(display, (bar_x, bar_y), 
                            (bar_x + bar_width, bar_y + 20), 
                            (0, 0, 0), 2)
                cv2.putText(display, f"{progress*100:.1f}%", 
                           (bar_x + bar_width + 10, bar_y + 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                
                cv2.imshow("Robot Drawing Animation", display)
                cv2.waitKey(1)
                
                prev_canvas_pos = current_canvas_pos
                
                # Di chuyển robot
                if is_pen_down != pen_down:
                    move_vel = 20.0
                    pen_down = is_pen_down
                    action = "PEN DOWN" if pen_down else "PEN UP"
                    # In kèm torque khi thay đổi trạng thái
                    with torque_lock:
                        print(f"Line {i+1}: {action} at X{current_pos['X']:.1f} Y{current_pos['Y']:.1f} | Torque: {[f'{t:.2f}' for t in latest_torques]}")
                else:
                    move_vel = vel if pen_down else 100.0
                
                rtn = robot.MoveL(
                    desc_pos=target_pos, 
                    tool=tool, 
                    user=user, 
                    vel=move_vel, 
                    blendR=blendR if pen_down else 0
                )
                
                if rtn != 0:
                    print(f"Line {i+1}: ERROR - Return code {rtn}")
    
    except Exception as e:
        print(f"LỖI: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Dừng torque monitoring
        torque_monitoring = False
        time.sleep(0.2)  # Đợi thread kết thúc

        cv2.putText(drawing_canvas, "COMPLETE - Press any key to close", 
                   (50, CANVAS_HEIGHT - 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 128, 0), 2)
        cv2.imshow("Robot Drawing Animation", drawing_canvas)
        cv2.waitKey(0)
        
        print(f"\n✅ Drawing complete! Total strokes: {line_count}")
        print("\nVề Home...")
        robot.MoveL(desc_pos=p_home, tool=tool, user=user, vel=100.0, blendR=0)
        robot.CloseRPC()
        cv2.destroyAllWindows()
        print("Done!")

# --- CHẠY CHƯƠNG TRÌNH --- 
if __name__ == "__main__":
    
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\eintein12345.gcode"
    #gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ronaldo123.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ronaldo345.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\shin123_optimizedv3.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\messi123.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\newton.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\RM.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Rose.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\anhstanh.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Doraemon_optimizedv3.gcode"
    # gcode_file="C:\\Users\MANH DUNG\\Downloads\\sketch (25)_plotted_1.gcode";
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\sketch (38)_plotted_1.gcode"
    

 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\anhstanh_optimized.gcode" 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\newton123_optimized.gcode" 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\messi123_optimized.gcode"  
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\RM_optimized.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Rose_optimizedv1.gcode" 
    gcode_file="C:\\Users\\MANH DUNG\\Downloads\\chan_dung_ronaldo_optimizedv1.gcode" 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\shin123_optimizedv2.gcode" 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\mp32_optimizedv3.gcode" xong
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Doraemon_optimizedv3.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\mauanh.gcode" 
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\sketch (6)_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\sketch (20)_plotted_2_optimized.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\sketch (21)_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\e2de53208f406da593ef1938e57d5677_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\drawing1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\gcode_to_sketchline.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468472575_plotted_2.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468768145_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468768145_plotted_2.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468768145 (1)_plotted_2.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468768145 (1)_plotted_3.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468044908_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779468044908 (1)_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\vanceai_1779467075053 (1)_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\vanceai_1779467075053 (1)_plotted_2.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-23 221120_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-23 222425_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-23 224016_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-23 225347_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779583979445_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779583979445_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 080110_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779585596574_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\ai_filter1779585596574_plotted_2.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 084242_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 091421_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 092759_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 101158_plotted_1.gcode"
    # gcode_file="C:\\Users\\MANH DUNG\\Downloads\\Screenshot 2026-05-24 101158_plotted_1.gcode"
    # gcode_file=r"C:\Users\MANH DUNG\Downloads\images_edge_plotted_1.gcode"
    # gcode_file=r"C:\Users\MANH DUNG\Downloads\face_sketch_robot\output\output.gcode"

    execute_gcode(gcode_file)