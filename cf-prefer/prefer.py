#!/usr/bin/env python3
"""Run locally: CloudflareSpeedTest -> latest.csv + edgetunnel all.txt."""
import argparse
import csv
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
REGIONS = {
    "HKG": "香港", "TPE": "台湾台北", "KHH": "台湾高雄",
    "NRT": "日本东京", "KIX": "日本大阪", "ICN": "韩国首尔",
    "SIN": "新加坡", "LAX": "美国洛杉矶", "SJC": "美国圣何塞",
    "SEA": "美国西雅图", "FRA": "德国法兰克福",
}
FIELDS = ["IP 地址", "已发送", "已接收", "丢包率", "平均延迟", "下载速度(MB/s)"]


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate(c):
    for key, low, high in [
        ("top_n", 1, 1000), ("port", 1, 65535), ("threads", 1, 1000),
        ("ping_count", 1, 100), ("download_count", 1, 1000),
        ("download_seconds", 5, 120), ("timeout_seconds", 1, 86400),
    ]:
        if type(c[key]) is not int or not low <= c[key] <= high:
            raise ValueError(f"{key} 必须是 {low} 至 {high} 之间的整数")
    for key, low, high in [
        ("max_latency_ms", 1, 9999), ("max_loss", 0, 1),
        ("min_speed_mb_s", 0, 1000000),
    ]:
        if not math.isfinite(float(c[key])) or not low <= float(c[key]) <= high:
            raise ValueError(f"{key} 超出有效范围")
    if c["test_url"] and not c["test_url"].startswith("https://"):
        raise ValueError("test_url 请填写 HTTPS 测速文件地址")


def select(text, c):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not set(FIELDS).issubset(reader.fieldnames or []):
        raise ValueError("CSV 缺少必要列，请使用 CloudflareSpeedTest 的原始 CSV")
    candidates = []
    for row in reader:
        try:
            ip = ipaddress.ip_address(row["IP 地址"].strip())
            sent, received = int(row["已发送"]), int(row["已接收"])
            loss, delay, speed = [float(row[key]) for key in FIELDS[3:]]
            if not all(math.isfinite(x) for x in (loss, delay, speed)):
                continue
            if not (sent > 0 and 0 < received <= sent and 0 <= loss <= 1):
                continue
            actual_loss = (sent - received) / sent
            if max(loss, actual_loss) > c["max_loss"]:
                continue
            if not (0 < delay <= c["max_latency_ms"] and speed > 0 and speed >= c["min_speed_mb_s"]):
                continue
            colo = (row.get("地区码") or "").strip().upper()
            label = REGIONS.get(colo, colo if re.fullmatch(r"[A-Z]{3}", colo) else "地区未知")
            candidates.append((speed, delay, str(ip), label, ip.version))
        except (ValueError, TypeError, AttributeError):
            continue
    candidates.sort(key=lambda r: (-r[0], r[1], r[2]))
    lines, seen = [], set()
    for speed, delay, ip, label, version in candidates:
        if ip in seen:
            continue
        seen.add(ip)
        host = f"[{ip}]" if version == 6 else ip
        lines.append(f"{host}:{c['port']}#{label}|{delay:.0f}ms|{speed:.2f}MB/s")
        if len(lines) >= c["top_n"]:
            break
    if not lines:
        raise ValueError("没有符合条件的 IP；保留上一次结果。请检查测速地址、网络或调整筛选条件")
    return "\n".join(lines) + "\n"


def run(c, base):
    binary = (base / c["binary"]).resolve()
    if os.name == "nt" and not binary.is_file():
        binary = binary.with_suffix(".exe")
    if not binary.is_file():
        raise ValueError(f"找不到测速程序 {binary}，请先下载对应系统的 cfst")
    ip_file = (base / c["ip_file"]).resolve()
    if not ip_file.is_file():
        raise ValueError("缺少 IP 段文件，请先执行 update-ips")
    with tempfile.TemporaryDirectory(prefix="cf-prefer-") as work:
        result = Path(work) / "result.csv"
        args = [str(binary), "-f", str(ip_file), "-o", str(result), "-p", "0", "-sl", "0"]
        for flag, key in [("-n", "threads"), ("-t", "ping_count"),
                          ("-dn", "download_count"), ("-dt", "download_seconds"),
                          ("-tp", "port"), ("-tl", "max_latency_ms"), ("-tlr", "max_loss")]:
            args.extend([flag, str(c[key])])
        if c["test_url"]:
            args.extend(["-url", c["test_url"]])
        subprocess.run(args, cwd=base, check=True, timeout=c["timeout_seconds"], stdin=subprocess.DEVNULL)
        if not result.is_file():
            raise ValueError("测速没有产生结果；保留上一次结果")
        return result.read_text(encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser(description="为自己的网络生成 CF 优选列表")
    parser.add_argument("command", choices=["update-ips", "run", "convert"])
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--csv", type=Path, help="convert：已有的测速 CSV")
    args = parser.parse_args()
    try:
        c = json.loads(args.config.read_text(encoding="utf-8-sig"))
        validate(c)
        base = args.config.resolve().parent
        if args.command == "update-ips":
            url = "https://www.cloudflare.com/ips-v4"
            with urllib.request.urlopen(url, timeout=30) as response:
                text = response.read(65536).decode("utf-8")
            networks = [ipaddress.IPv4Network(line.strip()) for line in text.splitlines() if line.strip()]
            if not networks:
                raise ValueError("Cloudflare 官方返回了空的 IP 段列表")
            atomic_write(base / c["ip_file"], "\n".join(map(str, networks)) + "\n")
            print(f"已从 Cloudflare 官方更新 {len(networks)} 个 IPv4 网段")
            return 0
        if args.command == "convert":
            if args.csv is None:
                parser.error("convert 需要 --csv 文件路径")
            text = args.csv.read_text(encoding="utf-8-sig")
        else:
            text = run(c, base)
        selected = select(text, c)
        output = base / c["output_dir"]
        atomic_write(output / "latest.csv", text)
        atomic_write(output / "all.txt", selected)
        print(f"已生成 {len(selected.splitlines())} 条优选 IP：{output.resolve()}")
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
