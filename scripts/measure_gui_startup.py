"""Measure GUI startup time (window hidden, until first update) and peak memory in fresh processes (Issue #67)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# 子プロセスで実行する計測コード。窓を作って初回描画を済ませ、経過時間と最大メモリを出力する。
CHILD = r"""
import json, sys, time
t0 = time.perf_counter()
sys.path.insert(0, sys.argv[1])
import tkinter as tk
import dot_editor
root = tk.Tk()
root.withdraw()
dot_editor.PixelEditor(root)
root.update()
elapsed = time.perf_counter() - t0
peak = 0
try:
    import ctypes
    from ctypes import wintypes
    class C(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = C(); c.cb = ctypes.sizeof(C)
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(C), wintypes.DWORD]
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    peak = c.PeakWorkingSetSize if ok else 0
except Exception:
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = rss if sys.platform == "darwin" else rss * 1024
    except Exception:
        peak = 0
print(json.dumps({"seconds": elapsed, "peak_bytes": peak}))
root.destroy()
"""


# {
#   責務: [run_once: 新しいプロセスでGUIを1回起動し、時間とメモリを測る]
#   処理: [
#     1: CHILDコードをpython -Iで実行する
#     2: 最後の行のJSONを読む
#   ]
#   引数: [timeout: 秒数の上限]
#   戻り値: [seconds/peak_bytesの辞書、失敗時はNone（表示環境がない場合など）]
# }
def run_once(timeout: float) -> dict | None:
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-c", CHILD, str(ROOT / "src")],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0 or not done.stdout.strip():
        print(
            f"[measure] child failed (exit {done.returncode}): {done.stderr.strip()[-300:]}",
            file=sys.stderr,
        )
        return None
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        print("[measure] child output was not JSON", file=sys.stderr)
        return None


# {
#   責務: [main: 指定回数だけ起動を測り、中央値と最大値を表示する]
#   処理: [
#     1: 回数分run_onceを呼ぶ
#     2: 1回も測れなければ未実行として終了コード2を返す
#     3: 秒とMiBの中央値・最大値をJSONで出す
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [測定できれば0、測定できなければ2]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    results = []
    for _ in range(max(1, args.runs)):
        measured = run_once(args.timeout)
        if measured is None:
            if results:
                continue  # 測定済みなら一時的な失敗として飛ばす
            break  # 最初の1回が起動できなければ表示環境がないとみなし、残りを待たない
        results.append(measured)
    if not results:
        print("[measure] not run: GUI could not start (no display?)", file=sys.stderr)
        return 2
    seconds = [r["seconds"] for r in results]
    mib = [
        r["peak_bytes"] / 1048576 for r in results if r["peak_bytes"] > 0
    ]  # 0は計測不能として除く
    print(
        json.dumps(
            {
                "runs": len(results),
                "seconds_median": round(statistics.median(seconds), 3),
                "seconds_max": round(max(seconds), 3),
                "peak_mib_median": round(statistics.median(mib), 1) if mib else None,
                "peak_mib_max": round(max(mib), 1) if mib else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
