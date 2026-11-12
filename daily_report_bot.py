import os
import re
import time
from datetime import datetime
import pyautogui
import pyperclip

# ---- Safety settings ----
pyautogui.FAILSAFE = True    # slam mouse into a screen corner to stop the bot
pyautogui.PAUSE = 0.5        # half-second pause after every action

# ---- Screen positions (x, y) measured on my screen with find_position.py ----
LOCATION_SEARCH_BOX = (445, 316)
FIRST_SUGGESTION = (306, 401)
EXCEL_BLANK_WORKBOOK = (208, 205)
# ---- Bournvita listings to track ----
PRODUCT_URLS = [
    "https://blinkit.com/prn/bournvita-chocolate-nutrition-drink-mix/prid/18646",
    "https://blinkit.com/prn/bournvita-chocolate-nutrition-drink-mix/prid/442222",
    "https://blinkit.com/prn/bournvita-chocolate-nutrition-drink-mix-500-g/prid/91212",
    "https://blinkit.com/prn/bournvita-chocolate-nutrition-drink-mix/prid/103273",
]

# ---- Cities to check ----
CITIES = [
    ("Delhi", "110001"),
    ("Mumbai", "400050"),
    ("Lucknow", "226010"),
]

def open_incognito(url):
    pyautogui.hotkey("win", "r")                         # open the Windows Run box
    time.sleep(1)
    pyautogui.write(f"chrome --incognito --start-maximized {url}", interval=0.03)
    pyautogui.press("enter")
    time.sleep(6)                                        # wait for Chrome + page to load
    pyautogui.hotkey("win", "up")                        # maximize the window
    time.sleep(1)


def copy_page_text():
    pyperclip.copy("")                                   # empty the clipboard first
    pyautogui.hotkey("ctrl", "a")                        # select everything on the page
    pyautogui.hotkey("ctrl", "c")                        # copy it
    time.sleep(1)
    return pyperclip.paste()                             # hand the text to Python


def set_location(pin):
    pyautogui.click(*LOCATION_SEARCH_BOX)
    pyautogui.write(pin, interval=0.1)
    time.sleep(3)                                        # wait for suggestions
    pyautogui.click(*FIRST_SUGGESTION)
    time.sleep(5)                                        # wait for the page to refresh

    # Safety check: did the location really change?
    page_text = copy_page_text()
    if pin in page_text:
        print(f"Location set to {pin}")
        return True
    else:
        print(f"Could not set location to {pin}")
        return False
def go_to(url):
    pyautogui.hotkey("ctrl", "l")                        # jump to the address bar
    pyautogui.write(url, interval=0.02)
    pyautogui.press("enter")
    time.sleep(6)                                        # wait for the page to load


def parse_product_page(page_text):
    """Pick out every pack size on a Blinkit product page (one size or many)."""
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]

    # Find the breadcrumb "Home / ..." line, the product name sits right below it
    crumb = None
    for i, line in enumerate(lines):
        if line.startswith("Home /"):
            crumb = i
            break

    if crumb is None:
        return []                                        # page didn't load properly

    name = lines[crumb + 1]
    start = crumb + 2
    if start < len(lines) and lines[start] == "Select Unit":
        start += 1                                       # multi-size page: skip the label                      
        
    stop_markers = ("(Inclusive", "Add to cart", "Why shop from blinkit", "Similar products")
    end = start
    while end < len(lines) and not lines[end].startswith(stop_markers):
        end += 1
    block = lines[start:end]

    packs = []
    seen = []
    i = 0
    while i < len(block):
        line = block[i]
        if re.fullmatch(r"(\d+ x )?[\d.]+ ?(g|kg|ml|l|ltr)", line, re.IGNORECASE):
            # collect the ₹ prices that follow this pack size
            prices = []
            j = i + 1
            while j < len(block) and block[j].startswith("₹"):
                prices.append(int(block[j].replace("₹", "").replace(",", "")))
                j += 1

            if j < len(block) and block[j] == "Out of stock":
                mrp, ecp, status = None, None, "Out of stock"
            elif prices:
                ecp = prices[0]
                mrp = prices[1] if len(prices) > 1 else prices[0]
                status = "Available"
            else:
                i += 1
                continue

            if line not in seen:                         # skip the repeat at the bottom
                seen.append(line)
                packs.append({"name": name, "grammage": line,
                              "mrp": mrp, "ecp": ecp, "status": status})
            i = j
        else:
            i += 1
    return packs


def collect_prices(pin):
    all_packs = []
    for n, url in enumerate(PRODUCT_URLS, start=1):
        go_to(url)
        page_text = copy_page_text()

        # Save what the bot copied, for checking
        with open(f"debug_{pin}page_{n}.txt", "w", encoding="utf-8") as f:
            f.write(page_text)

        packs = parse_product_page(page_text)
        if packs:
            all_packs.extend(packs)
        else:
            print(f"Skipped (page not readable): {url}")
    return all_packs

def remove_duplicates(packs):
    """Keep one row per (product name, pack size): in-stock first, then lowest ECP."""
    best = {}
    for p in packs:
        key = (p["name"], p["grammage"])
        if key not in best:
            best[key] = p
        else:
            old = best[key]
            if old["status"] == "Out of stock" and p["status"] == "Available":
                best[key] = p
            elif old["status"] == "Available" and p["status"] == "Available" and p["ecp"] < old["ecp"]:
                best[key] = p
    return list(best.values())


def collect_city(city, pin):
    """Open a fresh Incognito window, set the pin code, and collect all prices."""
    print(f"--- {city} ({pin}) ---")
    open_incognito("https://blinkit.com")
    rows = []
    if set_location(pin):
        for p in remove_duplicates(collect_prices(pin)):
            p["city"] = city
            p["pin"] = pin
            rows.append(p)
    else:
        rows.append({"city": city, "pin": pin, "name": "-", "grammage": "-",
                     "mrp": None, "ecp": None, "status": "Location not set"})
    pyautogui.hotkey("ctrl", "shift", "w")          # close the Incognito window
    time.sleep(2)
    return rows

def make_comment(row, all_rows):
    """Compare this row with the same pack in the other cities."""
    if row["status"] != "Available":
        return f"{row['status']} in {row['city']}"

    same_pack = [r for r in all_rows
                 if r["name"] == row["name"] and r["grammage"] == row["grammage"]
                 and r["status"] == "Available"]
    lowest = min(r["ecp"] for r in same_pack)

    if len(same_pack) == 1:
        return f"Only available in {row['city']}"
    if all(r["ecp"] == lowest for r in same_pack):
        return "Same ECP in all available cities"
    if row["ecp"] == lowest:
        return "Lowest ECP across cities"
    return f"₹{row['ecp'] - lowest} above lowest ECP"


def build_report_table(all_rows):
    """Turn the collected rows into a table: header + one list per row."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    table = [["Date & Time", "City", "Pin", "Product", "Grammage",
              "MRP", "ECP", "Disc %", "Comment"]]
    for r in all_rows:
        if r["status"] == "Available":
            mrp, ecp = r["mrp"], r["ecp"]
            disc = f"{(mrp - ecp) / mrp * 100:.1f}%"
        else:
            mrp, ecp, disc = "", "", ""
        table.append([now, r["city"], r["pin"], r["name"], r["grammage"],
                      mrp, ecp, disc, make_comment(r, all_rows)])
    return table

def open_excel_new_workbook():
    pyautogui.hotkey("win", "r")
    time.sleep(1)
    pyautogui.write("excel", interval=0.05)
    pyautogui.press("enter")
    time.sleep(8)                                   # Excel is slow to start
    pyautogui.hotkey("win", "up")                   # maximize FIRST, so the tile is where we measured it
    time.sleep(2)
    pyautogui.click(*EXCEL_BLANK_WORKBOOK)          # click "Blank workbook" on the Start screen
    time.sleep(4)
    pyautogui.hotkey("win", "up")                   # maximize the new workbook window
    time.sleep(1)


def paste_table(table):
    # Tabs between columns, new lines between rows: Excel splits them on paste
    text = "\n".join("\t".join(str(cell) for cell in row) for row in table)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "home")                # go to cell A1
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2)
    pyautogui.hotkey("ctrl", "a")                   # select the table
    pyautogui.press(["alt", "h", "o", "i"], interval=0.3)   # Home > Format > AutoFit Column Width
    time.sleep(1)
    pyautogui.hotkey("ctrl", "home")


def save_workbook(path):
    if os.path.exists(path):
        os.remove(path)                             # avoid the "replace file?" pop-up
    pyautogui.press("f12")                          # Save As dialog
    time.sleep(3)
    pyperclip.copy(path)
    pyautogui.hotkey("ctrl", "v")                   # paste the full file path
    pyautogui.press("enter")
    time.sleep(4)

# ================= MAIN =================
print("Starting in 5 seconds... hands off the mouse!")
time.sleep(5)

# 1. Collect prices from every city
all_rows = []
for city, pin in CITIES:
    all_rows.extend(collect_city(city, pin))

# 2. Build the report table
table = build_report_table(all_rows)

# 3. Write it into Excel, save it, take the screenshot
today = datetime.now().strftime("%Y-%m-%d")
excel_path = os.path.abspath(f"daily_report_{today}.xlsx")
screenshot_path = os.path.abspath(f"daily_report_{today}.png")

open_excel_new_workbook()
paste_table(table)
save_workbook(excel_path)
pyautogui.screenshot(screenshot_path)

print(f"Saved: {excel_path}")
print(f"Saved: {screenshot_path}")
print("Daily report complete!")