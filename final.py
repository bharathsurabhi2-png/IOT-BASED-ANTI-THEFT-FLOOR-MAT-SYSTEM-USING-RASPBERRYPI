#!/usr/bin/env python3
import os, time, datetime, ssl, smtplib, mimetypes
import RPi.GPIO as GPIO
from email.message import EmailMessage
from picamera2 import Picamera2

# ========= CONFIG =========
# Piezo mode
COMBINED_MAT = True                    # True = all piezos tied together, False = separate pins
COMBINED_PIN = 17                      # BCM input if using combined 2-wire mat
PIEZO_PINS   = [17, 27, 22, 23, 24, 25, 5, 6]  # if COMBINED_MAT=False

# Outputs
BUZZER_PIN = 18                        # GPIO pin for buzzer (via transistor driver)
LED_RED    = 19                        # GPIO pin for red LED (intrusion alert)
LED_GREEN  = 26                        # GPIO pin for green LED (system armed)

# Behavior
DEBOUNCE_S    = 0.20                   # Ignore repeated triggers within 0.2 sec  
ALARM_BEEPS   = 2                      # Number of buzzer beeps when intruder detected
WARMUP_S      = 0.7                    # Camera warm-up time before capture
CAPTURE_DIR   = "/home/bharath/antitheft"  # Directory to save captured images

# Email (Gmail SMTP)
EMAIL_USER = os.environ.get("EMAIL_USER")   # export EMAIL_USER="your@gmail.com"
EMAIL_PASS = os.environ.get("EMAIL_PASS")   # export EMAIL_PASS="app_password"
EMAIL_TO   = os.environ.get("EMAIL_TO", EMAIL_USER) # Recipient email (defaults to sender)
SMTP_HOST  = "smtp.gmail.com"               # Gmail SMTP server
SMTP_PORT  = 465  # SSL                     # Port for SSL connection
EMAIL_COOLDOWN_S = 8.0                      # Minimum time between emails
_last_email_ts = 0.0                        # Last email sent timestamp
# =========================

os.makedirs(CAPTURE_DIR, exist_ok=True)      # Create capture directory if it doesn’t exist
GPIO.setmode(GPIO.BCM)                        # Use Broadcom GPIO numbering
GPIO.setwarnings(False)                      # Suppress GPIO warnings
GPIO.cleanup()  # clean any previous run state   # Reset any previous GPIO state

def setup_inputs():
    if COMBINED_MAT:
        GPIO.setup(COMBINED_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Pull-down resistor
    else:
        for p in PIEZO_PINS:
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def setup_outputs():
    for pin in (BUZZER_PIN, LED_RED, LED_GREEN):
        GPIO.setup(pin, GPIO.OUT)           # Set as output
        GPIO.output(pin, GPIO.LOW)         # Start with outputs OFF

def beep(times=1, on=0.18, off=0.15):
    for _ in range(times):
        GPIO.output(BUZZER_PIN, GPIO.HIGH); time.sleep(on)   # Buzzer ON
        GPIO.output(BUZZER_PIN, GPIO.LOW);  time.sleep(off)   # Buzzer OFF

def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def send_email_with_image(image_path, subject="⚠️ Intruder detected!", body="Motion detected. See attached image."):
    """Send an email with image attached (rate-limited)."""
    global _last_email_ts
    now = time.time()
    if now - _last_email_ts < EMAIL_COOLDOWN_S:     # Skip if still in cooldown
        print("Email skipped (cooldown).")
        return
    _last_email_ts = now

    if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):    # Ensure credentials are set
        print("Email creds missing: set EMAIL_USER and EMAIL_PASS.")
        return

    msg = EmailMessage()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

 # Attach image file
   ctype, _ = mimetypes.guess_type(image_path)
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    with open(image_path, "rb") as f:
        msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                           filename=os.path.basename(image_path))
        
 # Connect to Gmail SMTP and send
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
    print("Email sent to:", EMAIL_TO)

def capture_image(tag="event"):
    """Capture a photo with retry if camera is busy."""
    global cam
    fname = f"{tag}_{timestamp()}.jpg"
    path = os.path.join(CAPTURE_DIR, fname)

    def _try_capture():
        cam.start()            # Start camera
        time.sleep(WARMUP_S)    # Warm up
        cam.capture_file(path)  # Capture image
        cam.stop()               # Stop camera

    try:
        _try_capture()
    except Exception as e:
        print("Camera error, retrying:", e)
        try: cam.stop()
        except Exception: pass
        try:
            cam = Picamera2()    # Reinitialize camera
            time.sleep(0.2)      
            _try_capture()
        except Exception as e2:
            print("Camera failed again, giving up:", e2)
            raise
    return path

def combined_loop():
    print("Mode: COMBINED mat input on GPIO", COMBINED_PIN)
    last = 0.0
    while True:
        if GPIO.input(COMBINED_PIN):      # Detect footstep
            now = time.time()
            if now - last > DEBOUNCE_S:    # Debounce check
                print("⚠️ Intrusion detected (combined)!")
                GPIO.output(LED_RED, GPIO.HIGH)   # Red LED ON
                beep(ALARM_BEEPS)                 # Buzzer alert

                img = capture_image("intruder")    # Capture photo
                send_email_with_image(             # Send email with photo
                    img,
                    subject=f"⚠️ Intruder @ {timestamp()}",
                    body="Anti-theft floor mat detected movement. See attached image."
                )
                print("Saved:", img)

                GPIO.output(LED_RED, GPIO.LOW)   # Red LED OFF
                last = now
        time.sleep(0.01)            # Small delay to reduce CPU use

def individual_loop():
    print("Mode: INDIVIDUAL sensors on GPIOs", PIEZO_PINS)
    last = {p: 0.0 for p in PIEZO_PINS}    # Track last trigger per sensor
    while True:
        for p in PIEZO_PINS:
            if GPIO.input(p):             # Check each piezo
                now = time.time()
                if now - last[p] > DEBOUNCE_S:    # Debounce check
                    idx = PIEZO_PINS.index(p) + 1
                    print(f"⚠️ Intrusion on Piezo {idx} (GPIO {p})!")
                    GPIO.output(LED_RED, GPIO.HIGH)
                    beep(ALARM_BEEPS)

                    img = capture_image(f"intruder_s{idx}")
                    send_email_with_image(
                        img,
                        subject=f"⚠️ Intruder (S{idx}) @ {timestamp()}",
                        body=f"Movement on sensor S{idx}. Image attached."
                    )
                    print("Saved:", img)

                    GPIO.output(LED_RED, GPIO.LOW)
                    last[p] = now
        time.sleep(0.01)

# ---------- Main ----------
try:
    setup_inputs()        # Setup piezo inputs
    setup_outputs()       # Setup LEDs and buzzer

    GPIO.output(LED_GREEN, GPIO.HIGH)  # Green LED ON = system armed
    print("System armed. Images ->", CAPTURE_DIR)

    cam = Picamera2()                  # single shared camera

    if COMBINED_MAT:
        combined_loop()                 # Run combined mat loop
    else:
        individual_loop()                # Run individual mat loop

except KeyboardInterrupt:
    pass                     # Graceful exit when Ctrl+C pressed
finally: 
    GPIO.output(LED_GREEN, GPIO.LOW)      # Turn off green LED
    GPIO.output(LED_RED, GPIO.LOW)        # Turn off red LED
    GPIO.output(BUZZER_PIN, GPIO.LOW)      # Turn off buzzer
    GPIO.cleanup()                         # Reset all GPIO pins
    print("\nClean exit.")
