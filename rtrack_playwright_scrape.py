import json
import sqlite3
import csv
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

def main():
    url = "https://rtrack.live/datasets"
    keywords = ["concurrent", "graph", "chart", "api/graph"]
    printed = set()
    conn = sqlite3.connect("roblox_data.db")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS concurrent_users (
            timestamp TEXT PRIMARY KEY,
            user_count INTEGER,
            fetched_at TEXT
        )
        """
    )

    def extract_points(payload):
        pts = []
        def add(ts, val):
            if ts is None or val is None:
                return
            try:
                v = int(float(val))
            except Exception:
                return
            ts_str = str(ts)
            pts.append((ts_str, v))
        def parse_item(item):
            if isinstance(item, dict):
                ts = item.get("AsOfHour") or item.get("timestamp") or item.get("time") or item.get("x")
                val = item.get("PlatformConcurrent") or item.get("user_count") or item.get("value") or item.get("y")
                add(ts, val)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                add(item[0], item[1])
        if isinstance(payload, dict):
            for k in ("Response", "data", "points", "series", "values"):
                v = payload.get(k)
                if isinstance(v, list) and v:
                    for it in v:
                        parse_item(it)
            parse_item(payload)
        elif isinstance(payload, list):
            for it in payload:
                parse_item(it)
        return pts

    def on_response(response):
        try:
            u = response.url
            ul = u.lower()
            ct = (response.headers.get("content-type") or "").lower()
            if any(k in ul for k in keywords):
                if "json" in ct:
                    try:
                        data = response.json()
                    except Exception:
                        try:
                            data = json.loads(response.text())
                        except Exception:
                            data = None
                else:
                    try:
                        data = json.loads(response.text())
                    except Exception:
                        data = None
                if data is not None and u not in printed:
                    printed.add(u)
                    print("==== JSON captured from:", u)
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    pts = extract_points(data)
                    if pts:
                        now = datetime.utcnow().isoformat()
                        for ts, val in pts:
                            cur.execute(
                                "INSERT OR IGNORE INTO concurrent_users(timestamp, user_count, fetched_at) VALUES (?, ?, ?)",
                                (ts, val, now),
                            )
                        conn.commit()
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("response", on_response)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(10000)
        csv_path = os.path.join(os.getcwd(), "concurrent_users.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "user_count", "fetched_at"])
            for row in cur.execute("SELECT timestamp, user_count, fetched_at FROM concurrent_users ORDER BY timestamp"):
                w.writerow(row)
        browser.close()
        conn.close()

if __name__ == "__main__":
    main()
