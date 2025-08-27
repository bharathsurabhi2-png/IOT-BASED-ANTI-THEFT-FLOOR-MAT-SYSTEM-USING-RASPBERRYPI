#!/usr/bin/env python3
import os, time, datetime, ssl, smtplib, mimetypes
import RPi.GPIO as GPIO
from email.message import EmailMessage
from picamera2 import Picamera2

# ========= CONFIG =========
# Piezo mode
COMBINED_MAT = True
COMBINED_PIN = 17                      # BCM input if using combined 2-wire mat
PIEZO_PINS   = [17, 27, 22, 23, 24, 25, 5, 6]  # if COMBINED_MAT=False

# Outputs
BUZZER_PIN = 18
LED_RED    = 19
LED_GREEN  = 26

# Behavior
DEBOUNCE_S    = 0.20
ALARM_BEEPS   = 2
WARMUP_S      = 0.7
CAPTURE_DIR   = "/home/bharath/antitheft"

# Email (Gmail SMTP)
EMAIL_USER = os.environ.get("EMAIL_USER")   # export EMAIL_USER="your@gmail.com"
EMAIL_PASS = os.environ.get("EMAIL_PASS")   # export EMAIL_PASS="app_password"
EMAIL_TO   = os.environ.get("EMAIL_TO", EMAIL_USER)
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 465  # SSL
EMAIL_COOLDOWN_S = 8.0
_last_email_ts = 0.0
# =========================

os.makedirs(CAPTURE_DIR, exist_ok=True)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.cleanup()  # clean any previous run state

def setup_inputs():
    if COMBINED_MAT:
        GPIO.setup(COMBINED_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    else:
        for p in PIEZO_PINS:
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def setup_outputs():
    for pin in (BUZZER_PIN, LED_RED, LED_GREEN):
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

def beep(times=1, on=0.18, off=0.15):
    for _ in range(times):
        GPIO.output(BUZZER_PIN, GPIO.HIGH); time.sleep(on)
        GPIO.output(BUZZER_PIN, GPIO.LOW);  time.sleep(off)

def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def send_email_with_image(image_path, subject="⚠️ Intruder detected!", body="Motion detected. See attached image."):
    """Send an email with image attached (rate-limited)."""
    global _last_email_ts
    now = time.time()
    if now - _last_email_ts < EMAIL_COOLDOWN_S:
        print("Email skipped (cooldown).")
        return
    _last_email_ts = now

    if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("Email creds missing: set EMAIL_USER and EMAIL_PASS.")
        return

    msg = EmailMessage()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

    ctype, _ = mimetypes.guess_type(image_path)
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    with open(image_path, "rb") as f:
        msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                           filename=os.path.basename(image_path))

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
        cam.start()
        time.sleep(WARMUP_S)
        cam.capture_file(path)
        cam.stop()

    try:
        _try_capture()
    except Exception as e:
        print("Camera error, retrying:", e)
        try: cam.stop()
        except Exception: pass
        try:
            cam = Picamera2()
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
        if GPIO.input(COMBINED_PIN):
            now = time.time()
            if now - last > DEBOUNCE_S:
                print("⚠️ Intrusion detected (combined)!")
                GPIO.output(LED_RED, GPIO.HIGH)
                beep(ALARM_BEEPS)

                img = capture_image("intruder")
                send_email_with_image(
                    img,
                    subject=f"⚠️ Intruder @ {timestamp()}",
                    body="Anti-theft floor mat detected movement. See attached image."
                )
                print("Saved:", img)

                GPIO.output(LED_RED, GPIO.LOW)
                last = now
        time.sleep(0.01)

def individual_loop():
    print("Mode: INDIVIDUAL sensors on GPIOs", PIEZO_PINS)
    last = {p: 0.0 for p in PIEZO_PINS}
    while True:
        for p in PIEZO_PINS:
            if GPIO.input(p):
                now = time.time()
                if now - last[p] > DEBOUNCE_S:
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
    setup_inputs()
    setup_outputs()

    GPIO.output(LED_GREEN, GPIO.HIGH)  # armed
    print("System armed. Images ->", CAPTURE_DIR)

    cam = Picamera2()                  # single shared camera

    if COMBINED_MAT:
        combined_loop()
    else:
        individual_loop()

except KeyboardInterrupt:
    pass
finally:
    GPIO.output(LED_GREEN, GPIO.LOW)
    GPIO.output(LED_RED, GPIO.LOW)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("\nClean exit.")
