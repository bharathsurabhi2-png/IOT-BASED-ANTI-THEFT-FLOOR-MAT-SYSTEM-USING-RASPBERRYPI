Title: **IoT Anti-Theft Floor Mat System using Raspberry Pi**
A simple, quiet, and inexpensive intrusion-detection system comprising Raspberry Pi. As soon as someone puts his foot on the mat, the red light turns on, the image captured by the Pi Camera is emailed to you (Gmail).
**Overview:**
•	Input: Piezoelectric floor mat → Raspberry Pi GPIO
•	Output: Red LED (intrusion indicator) + Photo captured by Pi Camera
•	Alerting: Email with image attachment via Gmail SMTP (App Password)
•	Noise control: Debounce + optional cooldown to prevent false triggers/spam
**Features:**
•	Silent detection (LED only)
•	Timestamped image capture
•	Secure Gmail email alerts (SSL)
•	Debounce and cooldown logic
•	Lightweight Python code; no cloud dependency
**Hardware:**
•	Raspberry Pi 4B with a 64bit Raspberry pi OS using Raspberry Pi Imager.
•	Raspberry Pi Camera Module (the camera is connected (CSI ribbon is connected) and picamera2).
•	A piezoelectric disc (or multiple of this) in a floor mat.
•	LEDs:
o	Green (system armed) → GPIO 26 (with 330 Ω resistor)
o	Red (intrusion alert) → GPIO 19 (with 330 Ω resistor)
•	Piezo signal → GPIO 17 (use your RC network as per your circuit)
Recommended input conditioning (example): 100 kΩ series resistor, 1 MΩ pull-down, 0.1 µF to ground.
**Project Structure:**
anti-theft-floor-mat/
├─ final.py                 # Main app (LED + Capture + Gmail)
├─ README.md                # This file
└─ /home/pi/antitheft/      # Images saved here (auto-created)
**Wiring (BCM numbering):**
•	Piezo → GPIO 17, GND to Pi GND
•	Green LED (armed): Anode → resistor → GPIO 26, Cathode → GND
•	Red LED (alert): Anode → resistor → GPIO 19, Cathode → GND
•	Camera ribbon → CSI port (securely latched)
**Software Setup:**
**1. Update OS & camera stack**
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3-pip python3-libcamera python3-picamera2 python3-rpi.gpio
2. Enable camera (if not already)
sudo raspi-config  # Interfacing Options → Camera → Enable → reboot
3. Clone / copy code
mkdir -p ~/anti-theft-floor-mat && cd ~/anti-theft-floor-mat
# place final.py here
4.Environment variables (Gmail App Password required)
Create/edit ~/.bashrc (or a .env file you export before running):
echo 'export EMAIL_USER="youraddress@gmail.com"' >> ~/.bashrc
echo 'export EMAIL_PASS="your_app_password_here"' >> ~/.bashrc
echo 'export EMAIL_TO="recipient@gmail.com"'     >> ~/.bashrc
source ~/.bashrc
Create an App Password in Google Account → Security → 2-Step Verification → App Passwords.
Run
python3 final.py
**You should see:**
•	Green LED ON = system armed
•	Stepping on mat → Red LED ON, image saved under /home/pi/antitheft, email sent with attachment.
Key Code Snippets (for documentation)
 GPIO & camera init
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(26, GPIO.OUT, initial=GPIO.HIGH)  # green (armed)
GPIO.setup(19, GPIO.OUT, initial=GPIO.LOW)   # red (alert)
cam = Picamera2()

Capture image
def capture_image():
    name = f"intruder_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    path = os.path.join("/home/pi/antitheft", name)
    cam.start(); time.sleep(0.7); cam.capture_file(path); cam.stop()
    return path
Send Gmail alert
def send_email(image_path):
    msg = EmailMessage()
    msg["From"], msg["To"] = EMAIL_USER, EMAIL_TO
    msg["Subject"] = "Intruder detected"
    msg.set_content("Movement detected. See attached image.")
    with open(image_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="image", subtype="jpeg",
                           filename=os.path.basename(image_path))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg)
Main loop
while True:
    if GPIO.input(17):                 # debounce in your code
        GPIO.output(19, GPIO.HIGH)
        img = capture_image()
        send_email(img)
        GPIO.output(19, GPIO.LOW)
    time.sleep(0.1)

**Run as a Service**
Create a systemd unit so it starts on boot:
sudo tee /etc/systemd/system/antitheft.service > /dev/null << 'UNIT'
[Unit]
Description=Anti-Theft Floor Mat (LED + Photo + Gmail)
After=network-online.target

[Service]
User=pi
Environment=EMAIL_USER=youraddress@gmail.com
Environment=EMAIL_PASS=your_app_password_here
Environment=EMAIL_TO=recipient@gmail.com
WorkingDirectory=/home/pi/anti-theft-floor-mat
ExecStart=/usr/bin/python3 /home/pi/anti-theft-floor-mat/final.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
Enable & start:
sudo systemctl daemon-reload
sudo systemctl enable antitheft
sudo systemctl start antitheft
sudo systemctl status antitheft
**Testing Checklist**
•	Camera preview / capture works (use libcamera-still -o test.jpg)
•	LEDs light as expected (quick Python one-liners with RPi.GPIO)
•	Stepping on mat produces one email per event 
•	Images appear in /home/pi/antitheft with timestamps
•	Gmail receives emails (check spam the first time)
**Troubleshooting**
•	No image / camera busy: Ensure ribbon seated; reboot; verify picamera2 installed; check other processes using camera.
•	No email sent: Confirm App Password, network up, environment vars exported; try from Python REPL.
•	Too many emails: Increase cooldown window in code (e.g., EMAIL_COOLDOWN_S = 10.0).
•	False triggers: Tune RC values, add software debounce (DEBOUNCE_S), physically isolate the mat from vibrations.
