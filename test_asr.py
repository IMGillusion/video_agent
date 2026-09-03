#!/usr/bin/env python3
"""ASR 预实验：拿 /tmp/huanri_video/bili.mp4 (30s 中文新闻) 测 faster-whisper
   验证 1) 模型能不能下载( HF / hf-mirror )  2) CPU aarch64 转写速度  3) 中文质量+时间戳
用法:
   HF_ENDPOINT=https://hf-mirror.com .venv/bin/python test_asr.py small
"""
import os, sys, time
from faster_whisper import WhisperModel

VIDEO = "/tmp/huanri_video/bili.mp4"
size = sys.argv[1] if len(sys.argv) > 1 else "small"

t0 = time.time()
print(f"[load] downloading/加载模型 {size} (int8) ...", flush=True)
model = WhisperModel(size, device="cpu", compute_type="int8")
t_load = time.time() - t0
print(f"[load] 完成 耗时 {t_load:.1f}s", flush=True)

t1 = time.time()
segments, info = model.transcribe(
    VIDEO, language="zh", vad_filter=True,
    word_timestamps=False, beam_size=5,
)
print(f"[info] 语言={info.language} p={info.language_probability:.2f} 时长={info.duration:.1f}s", flush=True)

lines = []
for seg in segments:
    print(f"[seg] {seg.start:7.2f} -> {seg.end:7.2f}  {seg.text.strip()}", flush=True)
    lines.append(f"{seg.start:7.2f} - {seg.end:7.2f}\t{seg.text.strip()}")

t2 = time.time() - t1
print(f"\n[done] 转写耗时 {t2:.1f}s  RTF={t2/info.duration:.2f} (越小越快)", flush=True)
print("\n===== SRT-like =====")
print("\n".join(lines))
