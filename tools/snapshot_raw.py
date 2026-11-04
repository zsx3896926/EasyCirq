"""用 Python 直接拿原始字节写文件，绕开 PowerShell 的文本编码处理。

上一版用 Start-Job + Out-File 捕获，非 ASCII 被当 GBK 重解释成乱码
（`-55℃~+155℃` 变成 `-55℃傈+155℃?`），结果 JSON 解析失败，
而失败信息说的是 "Invalid control character" —— 误导性很强。

结论先验：问题在我的捕获管道，不是 CLI。用字节级捕获验证。
"""
import pathlib
import subprocess

SNAP = pathlib.Path("deliverables/fan-controller/snapshot")
PROJECT = "Fan-Controller-12V"
PAGE = "664436e68d969739"

JOBS = {
    "list.json": ["--project", PROJECT, "--doc", PAGE, "sch", "list",
                  "--page", PAGE, "--include-pins", "--include-bbox",
                  "--include-wires", "--include-page-primitives"],
    "connectivity.json": ["--project", PROJECT, "--doc", PAGE, "sch",
                          "connectivity", "--page", PAGE],
    "drc.json": ["--project", PROJECT, "--doc", PAGE, "sch", "drc", "--json"],
}

for name, args in JOBS.items():
    proc = subprocess.run(["easycirq", *args], capture_output=True, timeout=180)
    data = proc.stdout or b""
    (SNAP / name).write_bytes(data)
    print(f"{name:20} {len(data):>8} 字节  rc={proc.returncode}  "
          f"前 3 字节={data[:3]}")

# 验证：能不能严格解析
import json

for name in JOBS:
    raw = (SNAP / name).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    start = text.find("{")
    try:
        json.JSONDecoder().raw_decode(text[start:])
        print(f"{name:20} 严格解析 OK")
    except json.JSONDecodeError as exc:
        print(f"{name:20} 解析失败: {exc}")
        line = text[start:].splitlines()[exc.lineno - 1]
        print(f"    第 {exc.lineno} 行: {line[:100]}")
