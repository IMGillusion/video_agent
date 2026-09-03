"""ASR 封装：faster-whisper 出带时间戳字幕。

- CPU aarch64 上 small/int8 实测：中文语义准、时间戳准，RTF≈4(离线可用非实时)
- 模型走 hf-mirror 镜像下载(HF 直连本机被挡)，缓存到 ~/.cache/huggingface
- 繁转简用 opencc(纯 python)；装不上就跳过(不影响，qwen 能读繁体)
"""
from __future__ import annotations

import hashlib
import os

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")       # 关 xet(镜像下被 401 挡)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from faster_whisper import WhisperModel  # noqa: E402

try:
    from opencc import OpenCC
    _CC = OpenCC("t2s")
    def simplify(t: str) -> str:
        return _CC.convert(t)
except Exception:
    def simplify(t: str) -> str:
        return t

_MODEL_CACHE: dict = {}


def _model(size: str, compute_type: str) -> WhisperModel:
    key = (size, compute_type)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(size, device="cpu", compute_type=compute_type)
    return _MODEL_CACHE[key]


def transcribe(video_path: str, cfg: dict):
    """返回 (segments, info)。segments=[{start,end,text}] 带时间戳(秒)。"""
    a = cfg.get("asr", {})
    model = _model(a.get("model_size", "small"), a.get("compute_type", "int8"))
    segments, info = model.transcribe(
        str(video_path),
        language=a.get("language", "zh"),
        vad_filter=a.get("vad_filter", True),
        beam_size=int(a.get("beam_size", 5)),
    )
    segs = []
    for s in segments:
        text = s.text.strip()
        if a.get("simplify", True):
            text = simplify(text)
        if text:
            segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
    return segs, info


def video_hash(path: str) -> str:
    """视频内容指纹(sha256 前8位)，用于识别同一视频、复用会话。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:8]
