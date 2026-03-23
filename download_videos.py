#!/usr/bin/env python3
"""
批量下载 YouTube 视频，使用 yt-dlp。
要求：
  1. 已安装 yt-dlp：pip install yt-dlp
  2. 已安装 Deno（用于 JS 运行时）：https://deno.com/
  3. 浏览器已登录 YouTube（用于 cookies）
"""

import csv
import subprocess
import sys
import os
from pathlib import Path

# ==================== 配置区域 ====================
# 你的浏览器类型：'chrome'、'firefox'、'edge' 等（小写）
BROWSER = 'firefox'          # 改为你实际使用的浏览器

# CSV 文件名（放在脚本同一目录）
CSV_FILE = 'set/match.csv'

# 下载目录（脚本所在目录下的 downloads 文件夹）
DOWNLOAD_DIR = 'downloads'
# =================================================

def download_video(row):
    """使用 yt-dlp 下载单个视频"""
    video_id = row['id']
    video_name = row['video']
    url = row['url']

    output_filename = f"{video_id}-{video_name}.mp4"
    output_path = Path(DOWNLOAD_DIR) / output_filename

    if output_path.exists():
        print(f"[跳过] {output_filename} 已存在")
        return True

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # yt-dlp 命令参数
    cmd = [
        "yt-dlp",
        "--js-runtimes", "deno",                     # 使用 Deno 作为 JS 运行时
        "--remote-components", "ejs:github",         # 从 GitHub 下载远程 JS 挑战组件
        "--cookies-from-browser", BROWSER,           # 从浏览器读取 cookies
        "-o", str(output_path),
        "--no-overwrites",                           # 不覆盖已有文件
        "--restrict-filenames",                      # 避免文件名特殊字符问题
        url
    ]

    print(f"[下载] {output_filename} ...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"[成功] {output_filename}")
            return True
        else:
            print(f"[失败] {output_filename}")
            # 打印更详细的错误信息，但避免过长
            stderr = result.stderr.strip()
            if stderr:
                print(f"错误信息：{stderr[:500]}")  # 截取前500字符
            return False
    except Exception as e:
        print(f"[异常] {output_filename}：{e}")
        return False

def main():
    if not os.path.isfile(CSV_FILE):
        print(f"错误：CSV 文件 {CSV_FILE} 不存在")
        sys.exit(1)

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"找到 {len(rows)} 条视频记录，开始下载...")
    success = 0
    fail = 0

    for row in rows:
        if download_video(row):
            success += 1
        else:
            fail += 1

    print(f"\n下载完成！成功：{success}，失败：{fail}")

if __name__ == "__main__":
    main()

