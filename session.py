"""会话管理：目录式存储。一个视频一个会话。

sessions/<session_id>/
  meta.json       会话元信息(id/标题/来源/时长/视频路径/指纹/时间/轮数)
  subtitles.json  [{start,end,text}] 带时间戳字幕
  subtitles.srt   人类可读字幕
  transcript.txt  拼好的 [起-止]文本 全文(喂 qwen 的基础上下文)
  frames/         clip 抽的帧
  history.jsonl   多轮对话历史 [{role,content,ts,has_image}]
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _base(cfg: dict) -> Path:
    return Path(__file__).resolve().parent / cfg.get("sessions_dir", "sessions")


def new_session(cfg, title, source, duration, video_path, video_hash):
    """建会话目录，写 meta。返回 (dir, session_id)。"""
    base = _base(cfg)
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    sid = f"s-{ts}-{video_hash}"
    d = base / sid
    (d / "frames").mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id": sid, "title": title, "source": source,
        "duration": round(float(duration), 1), "video_path": str(video_path),
        "video_hash": video_hash, "created": _now(), "updated": _now(), "turns": 0,
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return d, sid


def _srt_ts(t: float) -> str:
    h = int(t // 3600); m = int(t % 3600 // 60); s = int(t % 60); ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def save_subtitles(d: Path, segs: list) -> None:
    d = Path(d)
    (d / "subtitles.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
    srt = []
    for i, sg in enumerate(segs, 1):
        srt.append(f"{i}\n{_srt_ts(sg['start'])} --> {_srt_ts(sg['end'])}\n{sg['text']}\n")
    (d / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    (d / "transcript.txt").write_text(
        "\n".join(f"[{sg['start']:.1f}-{sg['end']:.1f}] {sg['text']}" for sg in segs), encoding="utf-8")


def load_meta(d: Path) -> dict:
    return json.loads((Path(d) / "meta.json").read_text(encoding="utf-8"))


def load_subtitles(d: Path) -> list:
    p = Path(d) / "subtitles.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_transcript(d: Path) -> str:
    p = Path(d) / "transcript.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_history(d: Path) -> list:
    p = Path(d) / "history.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def add_history(d: Path, role: str, content: str, has_image: bool = False) -> dict:
    rec = {"role": role, "content": content, "ts": _now(), "has_image": has_image}
    with open(Path(d) / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    meta = load_meta(d)
    meta["turns"] = meta.get("turns", 0) + 1
    meta["updated"] = _now()
    (Path(d) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def list_sessions(cfg: dict) -> list:
    base = _base(cfg)
    if not base.exists():
        return []
    out = []
    for d in base.iterdir():
        if d.is_dir() and (d / "meta.json").exists():
            m = load_meta(d)
            m["dir"] = str(d)
            out.append(m)
    out.sort(key=lambda m: m.get("updated", ""), reverse=True)
    return out


def find_by_hash(cfg: dict, vhash: str):
    """按视频指纹找已有会话目录(同视频复用)。"""
    for m in list_sessions(cfg):
        if m.get("video_hash") == vhash:
            return m["dir"]
    return None
