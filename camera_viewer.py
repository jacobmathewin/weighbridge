import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import threading
import os
from datetime import datetime
from dotenv import load_dotenv
from pymodbus.client import ModbusSerialClient
import serial
import re
import time

class CameraViewer:
    def __init__(self, root):
        # Load environment variables
        load_dotenv()
        
        self.root = root
        self.root.title("Dual IP Camera Viewer")
        self.root.geometry("1200x800")
        
        # Camera variables
        self.camera1 = None
        self.camera2 = None
        self.is_running = False
        
        # Video capture objects
        self.cap1 = None
        self.cap2 = None
        # Latest frames and locks for safe capture
        self.latest_frame1 = None
        self.latest_frame2 = None
        self.frame_lock1 = threading.Lock()
        self.frame_lock2 = threading.Lock()
        
        # Weighbridge connections
        self.modbus_client = None
        self.serial_conn = None
        self.weighbridge_protocol = os.getenv("WEIGHBRIDGE_PROTOCOL", "modbus").strip().lower()
        self.weight_value = "0.00"
        self.weight_unit = "kg"
        self.is_weight_connected = False
        
        # Setup GUI
        self.setup_gui()
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Bind window resize event to recalculate display sizes
        self.root.bind("<Configure>", self.on_window_resize)
    
    def build_camera_url(self, camera_num):
        """Build camera URL from environment variables"""
        # Check if full RTSP URL is provided
        rtsp_url = os.getenv(f"CAMERA{camera_num}_RTSP_URL")
        if rtsp_url:
            return rtsp_url
        
        # Build URL from individual components
        ip = os.getenv(f"CAMERA{camera_num}_IP", "192.168.1.100" if camera_num == 1 else "192.168.1.101")
        username = os.getenv(f"CAMERA{camera_num}_USERNAME", "admin")
        password = os.getenv(f"CAMERA{camera_num}_PASSWORD", "password")
        port = os.getenv(f"CAMERA{camera_num}_PORT", "554")
        stream_path = os.getenv(f"CAMERA{camera_num}_STREAM_PATH", "stream1")
        
        return f"rtsp://{username}:{password}@{ip}:{port}/{stream_path}"
    
    def connect_weighbridge(self):
        """Connect to weighbridge via Modbus or ASCII serial"""
        try:
            # Disconnect existing connection
            if self.modbus_client:
                self.modbus_client.close()
                self.modbus_client = None
            if self.serial_conn:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
            
            port = self.weight_port.get().strip()
            baudrate = int(self.weight_baudrate.get().strip())
            
            if not port:
                messagebox.showerror("Error", "Please enter weighbridge port")
                return
            
            self.weight_status.config(text="Status: Connecting...", foreground="orange")
            self.root.update()
            
            if self.weighbridge_protocol == "ascii":
                # Serial ASCII mode (e.g., many scales)
                parity = os.getenv("WEIGHBRIDGE_PARITY", "E").strip().upper()
                bytesize = int(os.getenv("WEIGHBRIDGE_BYTESIZE", "7").strip())
                stopbits = float(os.getenv("WEIGHBRIDGE_STOPBITS", "1").strip())
                timeout = float(os.getenv("WEIGHBRIDGE_TIMEOUT", "0.5").strip())

                parity_map = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}
                bytesize_map = {7: serial.SEVENBITS, 8: serial.EIGHTBITS}
                stopbits_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}

                self.serial_conn = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=bytesize_map.get(bytesize, serial.SEVENBITS),
                    parity=parity_map.get(parity, serial.PARITY_EVEN),
                    stopbits=stopbits_map.get(stopbits, serial.STOPBITS_ONE),
                    timeout=timeout,
                )

                self.is_weight_connected = True
                self.weight_status.config(text="Status: Connected (ASCII)", foreground="green")
                threading.Thread(target=self.read_weight_ascii_loop, daemon=True).start()
            else:
                # Modbus RTU mode
                parity = os.getenv("WEIGHBRIDGE_PARITY", "N").strip().upper()
                bytesize = int(os.getenv("WEIGHBRIDGE_BYTESIZE", "8").strip())
                stopbits = int(float(os.getenv("WEIGHBRIDGE_STOPBITS", "1").strip()))
                timeout = float(os.getenv("WEIGHBRIDGE_TIMEOUT", "1").strip())

                self.modbus_client = ModbusSerialClient(
                    method='rtu',
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    parity=parity,
                    stopbits=stopbits,
                    bytesize=bytesize
                )
                
                # Connect to device
                if self.modbus_client.connect():
                    self.is_weight_connected = True
                    self.weight_status.config(text="Status: Connected (Modbus)", foreground="green")
                    
                    # Start weight reading thread
                    threading.Thread(target=self.read_weight_loop, daemon=True).start()
                else:
                    self.weight_status.config(text="Status: Connection Failed", foreground="red")
                    messagebox.showerror("Error", f"Failed to connect to weighbridge on {port}")
                
        except Exception as e:
            self.weight_status.config(text="Status: Error", foreground="red")
            messagebox.showerror("Error", f"Failed to connect to weighbridge: {str(e)}")
    
    def read_weight_loop(self):
        """Continuously read weight from weighbridge"""
        while self.is_weight_connected and self.modbus_client:
            try:
                # Read holding registers (address 0, count 2) - adjust as needed for your device
                # Common addresses for weight scales: 0, 1, or 40001, 40002
                address = int(os.getenv("WEIGHBRIDGE_ADDRESS", "0").strip())
                count = int(os.getenv("WEIGHBRIDGE_COUNT", "2").strip())
                unit = int(os.getenv("WEIGHBRIDGE_SLAVE_ID", "1").strip())
                kind = os.getenv("WEIGHBRIDGE_KIND", "holding").strip().lower()

                if kind == "input":
                    result = self.modbus_client.read_input_registers(address=address, count=count, unit=unit)
                else:
                    result = self.modbus_client.read_holding_registers(address=address, count=count, unit=unit)
                
                if result.isError():
                    print(f"Modbus error: {result}")
                    time.sleep(1)
                    continue
                
                # Basic conversion: assume integer value; apply optional scale divisor
                raw = result.registers[0] if len(result.registers) > 0 else 0
                divisor = float(os.getenv("WEIGHBRIDGE_SCALE_DIVISOR", "1").strip())
                weight_value = float(raw) / (divisor if divisor != 0 else 1)
                
                # Update weight display in main thread
                self.root.after(0, lambda: self.update_weight_display(weight_value))
                
                time.sleep(0.5)  # Read every 500ms
                
            except Exception as e:
                print(f"Weight reading error: {e}")
                time.sleep(1)
        
        # Connection lost
        self.root.after(0, lambda: self.weight_status.config(text="Status: Disconnected", foreground="red"))

    def read_weight_ascii_loop(self):
        """Continuously read weight lines from ASCII serial device"""
        line_regex = os.getenv("WEIGHBRIDGE_REGEX", r"([-+]?\d+(?:\.\d+)?)")
        unit = os.getenv("WEIGHBRIDGE_UNIT", self.weight_unit)
        decimals_env = os.getenv("WEIGHBRIDGE_DECIMALS", "auto").strip().lower()
        divisor = float(os.getenv("WEIGHBRIDGE_SCALE_DIVISOR", "1").strip())

        pattern = re.compile(line_regex)
        while self.is_weight_connected and self.serial_conn:
            try:
                data = self.serial_conn.readline()
                if not data:
                    continue
                try:
                    text = data.decode(errors='ignore').strip()
                except Exception:
                    continue
                m = pattern.search(text)
                if not m:
                    continue
                value_str = m.group(1)
                try:
                    value = float(value_str)
                except ValueError:
                    continue
                if divisor and divisor != 1:
                    value = value / divisor
                if decimals_env == "auto":
                    display = f"{value:.2f}"
                else:
                    try:
                        decimals = int(decimals_env)
                        display = f"{value:.{decimals}f}"
                    except Exception:
                        display = f"{value:.2f}"
                self.root.after(0, lambda d=display, u=unit: self.weight_display.config(text=f"Weight: {d} {u}"))
            except Exception:
                time.sleep(0.2)
                continue
        self.root.after(0, lambda: self.weight_status.config(text="Status: Disconnected", foreground="red"))
    
    def update_weight_display(self, weight):
        """Update weight display in main thread"""
        self.weight_value = f"{weight:.2f}"
        self.weight_display.config(text=f"Weight: {self.weight_value} {self.weight_unit}")
    
    def setup_gui(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Camera input frame
        input_frame = ttk.LabelFrame(main_frame, text="Camera Settings", padding=10)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Camera 1 URL input
        ttk.Label(input_frame, text="Camera 1 URL:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.camera1_url = tk.StringVar(value=self.build_camera_url(1))
        ttk.Entry(input_frame, textvariable=self.camera1_url, width=40).grid(row=0, column=1, padx=(0, 10))
        
        # Camera 2 URL input
        ttk.Label(input_frame, text="Camera 2 URL:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.camera2_url = tk.StringVar(value=self.build_camera_url(2))
        ttk.Entry(input_frame, textvariable=self.camera2_url, width=40).grid(row=0, column=3, padx=(0, 10))
        
        # Connect button
        self.connect_btn = ttk.Button(input_frame, text="Connect Cameras", command=self.connect_cameras)
        self.connect_btn.grid(row=0, column=4, padx=(10, 0))
        
        # Weighbridge settings
        ttk.Label(input_frame, text="Weighbridge:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(10, 0))
        self.weight_port = tk.StringVar(value=os.getenv("WEIGHBRIDGE_PORT", "/dev/ttyUSB0"))
        ttk.Entry(input_frame, textvariable=self.weight_port, width=15).grid(row=1, column=1, padx=(0, 10), pady=(10, 0))
        
        self.weight_baudrate = tk.StringVar(value=os.getenv("WEIGHBRIDGE_BAUDRATE", "9600"))
        ttk.Label(input_frame, text="Baud:").grid(row=1, column=2, sticky=tk.W, padx=(0, 5), pady=(10, 0))
        ttk.Entry(input_frame, textvariable=self.weight_baudrate, width=8).grid(row=1, column=3, padx=(0, 10), pady=(10, 0))
        
        self.connect_weight_btn = ttk.Button(input_frame, text="Connect Weight", command=self.connect_weighbridge)
        self.connect_weight_btn.grid(row=1, column=4, padx=(10, 0), pady=(10, 0))
        
        # Video display frame
        video_frame = ttk.Frame(main_frame)
        video_frame.pack(fill=tk.BOTH, expand=True)
        
        # Camera 1 display
        camera1_frame = ttk.LabelFrame(video_frame, text="Camera 1", padding=5)
        camera1_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.camera1_label = tk.Label(camera1_frame, text="Camera 1\nNot Connected", 
                                    background="black", foreground="white", 
                                    font=("Arial", 12))
        self.camera1_label.pack(fill=tk.BOTH, expand=True)
        
        # Camera 2 display
        camera2_frame = ttk.LabelFrame(video_frame, text="Camera 2", padding=5)
        camera2_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.camera2_label = tk.Label(camera2_frame, text="Camera 2\nNot Connected", 
                                    background="black", foreground="white", 
                                    font=("Arial", 12))
        self.camera2_label.pack(fill=tk.BOTH, expand=True)
        
        # Weight display frame (small overlay at bottom right)
        weight_frame = ttk.LabelFrame(main_frame, text="Weight Display", padding=10)
        weight_frame.pack(side=tk.BOTTOM, anchor=tk.SE, pady=(10, 0))
        
        # Weight display
        self.weight_display = tk.Label(weight_frame, text="Weight: 0.00 kg", 
                                     background="lightblue", foreground="black", 
                                     font=("Arial", 14, "bold"), relief=tk.RAISED, bd=2)
        self.weight_display.pack()
        
        # Weight status
        self.weight_status = tk.Label(weight_frame, text="Status: Disconnected", 
                                    font=("Arial", 10), foreground="red")
        self.weight_status.pack()
        
        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Capture button
        self.capture_btn = ttk.Button(control_frame, text="Capture Images", 
                                    command=self.capture_images, state=tk.DISABLED)
        self.capture_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(control_frame, text="Status: Disconnected")
        self.status_label.pack(side=tk.LEFT)
        
        # Create captures directory
        self.captures_dir = "captures"
        if not os.path.exists(self.captures_dir):
            os.makedirs(self.captures_dir)
    
    def connect_cameras(self):
        """Connect to IP cameras"""
        try:
            # Disconnect existing cameras
            self.disconnect_cameras()
            
            # Get camera URLs
            url1 = self.camera1_url.get().strip()
            url2 = self.camera2_url.get().strip()
            
            if not url1 or not url2:
                messagebox.showerror("Error", "Please enter both camera URLs")
                return
            
            self.status_label.config(text="Status: Connecting...")
            self.root.update()
            
            # Try to connect to cameras
            self.cap1 = cv2.VideoCapture(url1)
            self.cap2 = cv2.VideoCapture(url2)
            
            # Test camera connections
            ret1, frame1 = self.cap1.read()
            ret2, frame2 = self.cap2.read()
            
            if not ret1:
                messagebox.showerror("Error", f"Failed to connect to Camera 1: {url1}")
                self.disconnect_cameras()
                return
            
            if not ret2:
                messagebox.showerror("Error", f"Failed to connect to Camera 2: {url2}")
                self.disconnect_cameras()
                return
            
            # Set camera properties
            self.cap1.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap2.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Start video streams
            self.is_running = True
            self.capture_btn.config(state=tk.NORMAL)
            self.status_label.config(text="Status: Connected")
            
            # Start video update threads
            threading.Thread(target=self.update_camera1, daemon=True).start()
            threading.Thread(target=self.update_camera2, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to cameras: {str(e)}")
            self.disconnect_cameras()
    
    def disconnect_cameras(self):
        """Disconnect from cameras"""
        self.is_running = False
        
        if self.cap1:
            self.cap1.release()
            self.cap1 = None
        
        if self.cap2:
            self.cap2.release()
            self.cap2 = None
        
        self.capture_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Disconnected")
        
        # Clear video displays
        self.camera1_label.config(text="Camera 1\nNot Connected", image="")
        self.camera2_label.config(text="Camera 2\nNot Connected", image="")
        # Clear stored frames
        try:
            with self.frame_lock1:
                self.latest_frame1 = None
            with self.frame_lock2:
                self.latest_frame2 = None
        except Exception:
            pass
    
    def disconnect_weighbridge(self):
        """Disconnect from weighbridge"""
        self.is_weight_connected = False
        
        if self.modbus_client:
            self.modbus_client.close()
            self.modbus_client = None
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
        
        self.weight_status.config(text="Status: Disconnected", foreground="red")
        self.weight_display.config(text="Weight: 0.00 kg")
    
    def get_display_size(self):
        """Get the available display size for video feeds"""
        # Get the window size and calculate available space for video
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        
        # Account for other UI elements (approximate)
        # Input frame: ~60px, control frame: ~40px, padding: ~40px
        available_height = max(400, window_height - 140)
        available_width = max(600, window_width - 40)
        
        # Each camera gets half the width
        camera_width = available_width // 2 - 20  # Account for padding between cameras
        camera_height = available_height - 40  # Account for label frame padding
        
        return camera_width, camera_height
    
    def update_camera1(self):
        """Update camera 1 video feed"""
        while self.is_running and self.cap1:
            try:
                ret, frame = self.cap1.read()
                if ret:
                    # Store original frame for capture
                    try:
                        with self.frame_lock1:
                            self.latest_frame1 = frame.copy()
                    except Exception:
                        pass
                    # Get display size
                    display_width, display_height = self.get_display_size()
                    
                    # Resize frame to fit display while maintaining aspect ratio
                    frame_height, frame_width = frame.shape[:2]
                    
                    # Calculate scaling factor
                    scale_w = display_width / frame_width
                    scale_h = display_height / frame_height
                    scale = min(scale_w, scale_h)
                    
                    # Resize frame
                    new_width = int(frame_width * scale)
                    new_height = int(frame_height * scale)
                    frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Convert to PIL Image and then to PhotoImage
                    image = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image)
                    
                    # Update label in main thread
                    self.root.after(0, lambda: self.update_camera1_display(photo))
                else:
                    break
            except Exception as e:
                print(f"Camera 1 error: {e}")
                break
        
        self.root.after(0, lambda: self.camera1_label.config(text="Camera 1\nConnection Lost"))
    
    def update_camera2(self):
        """Update camera 2 video feed"""
        while self.is_running and self.cap2:
            try:
                ret, frame = self.cap2.read()
                if ret:
                    # Store original frame for capture
                    try:
                        with self.frame_lock2:
                            self.latest_frame2 = frame.copy()
                    except Exception:
                        pass
                    # Get display size
                    display_width, display_height = self.get_display_size()
                    
                    # Resize frame to fit display while maintaining aspect ratio
                    frame_height, frame_width = frame.shape[:2]
                    
                    # Calculate scaling factor
                    scale_w = display_width / frame_width
                    scale_h = display_height / frame_height
                    scale = min(scale_w, scale_h)
                    
                    # Resize frame
                    new_width = int(frame_width * scale)
                    new_height = int(frame_height * scale)
                    frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Convert to PIL Image and then to PhotoImage
                    image = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image)
                    
                    # Update label in main thread
                    self.root.after(0, lambda: self.update_camera2_display(photo))
                else:
                    break
            except Exception as e:
                print(f"Camera 2 error: {e}")
                break
        
        self.root.after(0, lambda: self.camera2_label.config(text="Camera 2\nConnection Lost"))
    
    def update_camera1_display(self, photo):
        """Update camera 1 display in main thread"""
        self.camera1_label.config(image=photo, text="")
        self.camera1_label.image = photo  # Keep a reference
    
    def update_camera2_display(self, photo):
        """Update camera 2 display in main thread"""
        self.camera2_label.config(image=photo, text="")
        self.camera2_label.image = photo  # Keep a reference
    
    def capture_images(self):
        """Capture images from both cameras using last safe frames"""
        if not self.is_running:
            messagebox.showerror("Error", "Cameras not connected")
            return
        
        try:
            # Use frames stored by streaming threads to avoid concurrent reads
            with self.frame_lock1:
                frame1 = None if self.latest_frame1 is None else self.latest_frame1.copy()
            with self.frame_lock2:
                frame2 = None if self.latest_frame2 is None else self.latest_frame2.copy()
            
            if frame1 is None or frame2 is None:
                messagebox.showerror("Error", "No frames available to capture yet. Please try again.")
                return
            
            # Generate timestamp for filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save images
            filename1 = f"{self.captures_dir}/camera1_{timestamp}.jpg"
            filename2 = f"{self.captures_dir}/camera2_{timestamp}.jpg"
            
            cv2.imwrite(filename1, frame1)
            cv2.imwrite(filename2, frame2)
            
            messagebox.showinfo("Success", f"Images captured successfully!\nCamera 1: {filename1}\nCamera 2: {filename2}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture images: {str(e)}")
    
    def on_window_resize(self, event):
        """Handle window resize events"""
        # Only handle resize events for the main window
        if event.widget == self.root:
            # Trigger a recalculation of display sizes by updating the display size cache
            pass
    
    def on_closing(self):
        """Handle application closing"""
        self.disconnect_cameras()
        self.disconnect_weighbridge()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = CameraViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main()
