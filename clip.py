"""抽帧/截时间段（ffmpeg）。用于"看细节"：定位时间段抽几帧喂 qwen 多模态。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def frame_at(video: str, t: float, out_jpg: str) -> str:
    """在 t 秒抽一帧到 out_jpg。"""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(out_jpg)],
        capture_output=True, timeout=60, check=True,
    )
    return out_jpg


def frames_range(video: str, start: float, end: float, n: int, out_dir) -> list:
    """在 [start,end] 段均分抽 n 帧，返回 [(t, path)]。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = []
    if n <= 0 or end <= start:
        return res
    if n == 1:
        ts = [(start + end) / 2]
    else:
        ts = [start + (end - start) * i / (n - 1) for i in range(n)]
    for t in ts:
        t = max(0.0, min(t, end - 0.05))
        p = out_dir / f"f{t:.1f}.jpg"
        frame_at(video, t, str(p))
        res.append((round(t, 1), str(p)))
    return res
