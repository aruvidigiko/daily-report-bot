import pyautogui
import time

print("Move your mouse over any spot. Press Ctrl+C to stop.")
try:
    while True:
        x, y = pyautogui.position()
        print(f"X: {x:4}   Y: {y:4}", end="\r")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopped.")