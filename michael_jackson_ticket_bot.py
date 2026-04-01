#!/usr/bin/env python3
"""
Movie ticket monitor + pre-booking helper for rush releases.

What this script does:
- Opens a ticketing page in Chrome with a persistent user profile (stay logged in).
- Uses selenium-stealth + rotating user-agents.
- Polls every 3 minutes until a booking CTA appears.
- Applies language/format filters (e.g., English / IMAX), when available.
- Advances to seat selection and then to payment page (best effort, site-dependent).
- Triggers desktop audio + optional Pushbullet/Telegram alert on payment step.
- Keeps session alive so you can complete payment manually.

IMPORTANT:
- You must adjust CSS selectors for your target page.
- Respect platform Terms of Service and local laws.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_UAS = [
    # Keep this list fresh over time.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


@dataclass
class Selectors:
    book_button: str
    english_filter: str
    imax_filter: str
    seat_map_ready: str
    continue_to_payment: str
    payment_page_anchor: str

    @staticmethod
    def from_json(path: Path) -> "Selectors":
        data = json.loads(path.read_text(encoding="utf-8"))
        return Selectors(**data)


def build_driver(user_data_dir: str, profile_directory: str, user_agent: str) -> Chrome:
    options = Options()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_directory}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-agent={user_agent}")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32" if platform.system() == "Windows" else "MacIntel",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def wait_and_click(wait: WebDriverWait, css_selector: str, label: str, timeout_note: str = "") -> bool:
    try:
        elem = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
        elem.click()
        print(f"[+] Clicked: {label}")
        return True
    except TimeoutException:
        msg = f"[-] Timeout waiting for {label}."
        if timeout_note:
            msg += f" {timeout_note}"
        print(msg)
        return False


def notify_sound() -> None:
    system = platform.system()
    if system == "Windows":
        try:
            import winsound

            winsound.Beep(2000, 500)
            winsound.Beep(1500, 700)
        except Exception as exc:
            print(f"[!] winsound failed: {exc}")
    elif system == "Darwin":
        try:
            subprocess.run(["osascript", "-e", "beep 3"], check=False)
        except Exception as exc:
            print(f"[!] macOS beep failed: {exc}")
    else:
        # Terminal bell fallback for Linux/other systems.
        print("\a\a\a", end="", flush=True)


def notify_pushbullet(token: str, title: str, body: str) -> bool:
    try:
        response = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            headers={"Access-Token": token, "Content-Type": "application/json"},
            json={"type": "note", "title": title, "body": body},
            timeout=10,
        )
        ok = response.ok
        print(f"[{'+' if ok else '!'}] Pushbullet status: {response.status_code}")
        return ok
    except Exception as exc:
        print(f"[!] Pushbullet notification error: {exc}")
        return False


def notify_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        ok = response.ok
        print(f"[{'+' if ok else '!'}] Telegram status: {response.status_code}")
        return ok
    except Exception as exc:
        print(f"[!] Telegram notification error: {exc}")
        return False


def send_mobile_notifications(args: argparse.Namespace, message: str) -> None:
    if args.pushbullet_token:
        notify_pushbullet(args.pushbullet_token, "Ticket Bot Alert", message)

    if args.telegram_bot_token and args.telegram_chat_id:
        notify_telegram(args.telegram_bot_token, args.telegram_chat_id, message)


def keep_session_alive(driver: Chrome, interval_seconds: int = 25) -> None:
    print("[i] Session parked at payment page. Complete payment manually.")
    print("[i] Press Ctrl+C to quit when done.")
    try:
        while True:
            driver.execute_script("window.focus();")
            driver.execute_script("void(0);")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n[i] Stopping session by user request.")


def foreground_browser(driver: Chrome) -> None:
    """Best-effort focus; exact behavior depends on OS/window manager."""
    try:
        driver.switch_to.window(driver.current_window_handle)
        driver.maximize_window()
        driver.execute_script("window.focus();")
    except Exception as exc:
        print(f"[!] Could not force foreground focus: {exc}")


def monitor_and_book(driver: Chrome, args: argparse.Namespace, selectors: Selectors) -> None:
    poll_every = args.poll_seconds
    wait = WebDriverWait(driver, args.wait_timeout)

    while True:
        print(f"[i] Checking URL: {args.url}")
        driver.get(args.url)

        if not wait_and_click(
            wait,
            selectors.book_button,
            "Book Now",
            "Verify selector or ensure showtimes are live.",
        ):
            print(f"[i] Book button not found. Rechecking in {poll_every} sec...")
            time.sleep(poll_every)
            continue

        # Optional filters
        if selectors.english_filter:
            wait_and_click(wait, selectors.english_filter, "English filter")

        if args.prefer_imax and selectors.imax_filter:
            wait_and_click(wait, selectors.imax_filter, "IMAX filter")

        # Move toward seat screen
        if selectors.seat_map_ready:
            wait_and_click(wait, selectors.seat_map_ready, "Seat map/showtime selection")

        # Pause point (seat selection screen)
        print("[+] Reached seat selection stage (or closest available step).")

        # Try going to payment if configured.
        if selectors.continue_to_payment:
            wait_and_click(wait, selectors.continue_to_payment, "Continue to payment")

        if selectors.payment_page_anchor:
            wait_and_click(wait, selectors.payment_page_anchor, "Payment page marker")

        alert_text = "Ticket bot reached payment page. Open browser now for manual payment authorization."
        notify_sound()
        send_mobile_notifications(args, alert_text)
        foreground_browser(driver)
        keep_session_alive(driver)
        break


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Movie ticket monitor + pre-booking helper")
    parser.add_argument("--url", required=True, help="Target booking page URL")
    parser.add_argument(
        "--selectors-file",
        default="selectors.json",
        help="Path to JSON file containing CSS selectors",
    )
    parser.add_argument(
        "--user-data-dir",
        required=True,
        help="Chrome user data dir, e.g. C:/Users/<you>/AppData/Local/Google/Chrome/User Data",
    )
    parser.add_argument(
        "--profile-directory",
        default="Default",
        help="Chrome profile directory (Default, Profile 1, etc.)",
    )
    parser.add_argument("--wait-timeout", type=int, default=20, help="WebDriverWait timeout per step")
    parser.add_argument("--poll-seconds", type=int, default=180, help="Check interval (3 min = 180s)")
    parser.add_argument("--prefer-imax", action="store_true", help="Attempt IMAX filter click")

    # Mobile alerts
    parser.add_argument("--pushbullet-token", default=os.getenv("PUSHBULLET_TOKEN"))
    parser.add_argument("--telegram-bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID"))

    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    selectors_path = Path(args.selectors_file)

    if not selectors_path.exists():
        print(f"[!] selectors file not found: {selectors_path}")
        print("[i] Create it first. Use sample_selectors.json as template.")
        return 1

    selectors = Selectors.from_json(selectors_path)
    user_agent = random.choice(DEFAULT_UAS)
    print(f"[i] Using User-Agent: {user_agent}")

    driver = build_driver(args.user_data_dir, args.profile_directory, user_agent)

    try:
        monitor_and_book(driver, args, selectors)
    finally:
        print("[i] Closing browser...")
        driver.quit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
