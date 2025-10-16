# Dual IP Camera Viewer

A Python application using tkinter to display video feeds from two IP cameras and capture images simultaneously.

## Features

- Display live video feeds from two IP cameras side by side
- Real-time video streaming with OpenCV
- Capture images from both cameras with a single button click
- **Weighbridge weight display via USB Modbus**
- Configurable camera URLs and weighbridge settings
- Error handling for connection issues
- Automatic image saving with timestamps

## Requirements

- Python 3.7+
- OpenCV
- Pillow (PIL)
- tkinter (usually included with Python)
- pymodbus (for weighbridge communication)

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your camera credentials:
```bash
# Copy the environment template
cp env_template.txt .env

# Edit the .env file with your actual camera credentials
nano .env
```

## Usage

1. Run the application:
```bash
python camera_viewer.py
```

2. The application will automatically load camera URLs from your `.env` file. You can still modify them in the GUI if needed.

3. Click "Connect Cameras" to establish connections

4. Click "Connect Weight" to connect to the weighbridge (optional)

5. Once connected, click "Capture Images" to save images from both cameras

## Environment Configuration

The application reads camera credentials from a `.env` file for security. You can configure cameras in two ways:

### Method 1: Individual Components
```env
CAMERA1_IP=192.168.1.100
CAMERA1_USERNAME=admin
CAMERA1_PASSWORD=your_password
CAMERA1_PORT=554
CAMERA1_STREAM_PATH=stream1

CAMERA2_IP=192.168.1.101
CAMERA2_USERNAME=admin
CAMERA2_PASSWORD=your_password
CAMERA2_PORT=554
CAMERA2_STREAM_PATH=stream1
```

### Method 2: Full RTSP URLs
```env
CAMERA1_RTSP_URL=rtsp://admin:password@192.168.1.100:554/stream1
CAMERA2_RTSP_URL=rtsp://admin:password@192.168.1.101:554/stream1
```

### Weighbridge Configuration
```env
WEIGHBRIDGE_PORT=/dev/ttyUSB0
WEIGHBRIDGE_BAUDRATE=9600
WEIGHBRIDGE_SLAVE_ID=1
WEIGHBRIDGE_ADDRESS=0
```

## Camera URL Formats

The application supports various camera URL formats:

- **RTSP**: `rtsp://username:password@ip_address:port/stream`
- **HTTP**: `http://ip_address:port/video_feed`
- **Local webcam**: `0` (for default camera)

## File Structure

- `camera_viewer.py` - Main application file
- `requirements.txt` - Python dependencies
- `captures/` - Directory where captured images are saved (auto-created)

## Captured Images

Images are automatically saved in the `captures/` directory with the following naming convention:
- `camera1_YYYYMMDD_HHMMSS.jpg`
- `camera2_YYYYMMDD_HHMMSS.jpg`

## Troubleshooting

1. **Connection Issues**: 
   - Verify camera IP addresses and credentials
   - Check network connectivity
   - Ensure cameras support the specified protocol (RTSP/HTTP)

2. **Performance Issues**:
   - Reduce video resolution in camera settings
   - Check network bandwidth
   - Close other applications using network resources

3. **Permission Errors**:
   - Ensure the application has write permissions for the captures directory
