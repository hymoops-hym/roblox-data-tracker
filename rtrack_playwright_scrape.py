import json
import sqlite3
import csv
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

def main():
    # 目标网址
    url = "https://rtrack.live/datasets"
    
    # 连接数据库
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

    # 简化的数据提取逻辑
    def extract_and_save(data):
        pts = []
        # 尝试寻找常见的图表数据结构
        # 针对 RTrack 可能的结构 1: { "data": { "points": [...] } }
        # 针对 RTrack 可能的结构 2: [ [time, value], ... ]
        
        # 递归查找列表
        def find_lists(obj):
            if isinstance(obj, list):
                # 简单的启发式判断：如果列表里的元素看起来像坐标点 [time, value]
                if len(obj) > 10 and isinstance(obj[0], (list, dict)): 
                    return [obj]
                return []
            elif isinstance(obj, dict):
                results = []
                for k, v in obj.items():
                    results.extend(find_lists(v))
                return results
            return []

        potential_lists = find_lists(data)
        
        count = 0
        now = datetime.utcnow().isoformat()

        for lst in potential_lists:
            for item in lst:
                ts = None
                val = None
                
                # 尝试解析 [timestamp, value] 格式
                if isinstance(item, list) and len(item) >= 2:
                    ts = item[0]
                    val = item[1]
                # 尝试解析字典格式 { "x": ..., "y": ... } 或 { "time": ..., "value": ... }
                elif isinstance(item, dict):
                    ts = item.get("x") or item.get("time") or item.get("AsOfHour") or item.get("timestamp")
                    val = item.get("y") or item.get("value") or item.get("PlatformConcurrent") or item.get("user_count")

                # 只有当时间和数值都存在，且数值看起来像是一个大整数时才保存
                if ts and val:
                    try:
                        val_int = int(float(val))
                        # 过滤掉显然不对的小数字（并发人数通常很大）
                        if val_int > 1000: 
                            cur.execute(
                                "INSERT OR IGNORE INTO concurrent_users(timestamp, user_count, fetched_at) VALUES (?, ?, ?)",
                                (str(ts), val_int, now),
                            )
                            count += 1
                    except:
                        pass
        return count

    def on_response(response):
        try:
            # 只过滤掉显然是图片、CSS、JS 的资源
            resource_type = response.request.resource_type
            if resource_type in ["image", "stylesheet", "font"]:
                return

            # 打印所有 JSON 类型的响应，用于调试
            if "json" in response.headers.get("content-type", "").lower():
                print(f"🔍 发现 JSON: {response.url} [Status: {response.status}]")
                
                try:
                    data = response.json()
                    saved_count = extract_and_save(data)
                    if saved_count > 0:
                        print(f"✅ 成功提取并保存了 {saved_count} 条数据！")
                except:
                    pass
        except Exception as e:
            print(f"Error processing response: {e}")

    with sync_playwright() as p:
        # 添加 User-Agent 伪装，防止被识别为机器人
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("🚀 开始访问页面...")
        page.on("response", on_response)
        
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            print("📄 页面加载完成，等待数据包...")
            page.wait_for_timeout(15000) # 多等一会儿
        except Exception as e:
            print(f"⚠️ 页面加载超时或出错: {e}")

        # 导出 CSV
        csv_path = "concurrent_users.csv"
        saved_rows = 0
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "user_count", "fetched_at"])
            for row in cur.execute("SELECT timestamp, user_count, fetched_at FROM concurrent_users ORDER BY timestamp"):
                w.writerow(row)
                saved_rows += 1
        
        print(f"📊 最终 CSV 文件包含 {saved_rows} 行数据。")
        
        browser.close()
        conn.close()

if __name__ == "__main__":
    main()
