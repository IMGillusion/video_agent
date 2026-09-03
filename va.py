#!/usr/bin/env python3
"""video_agent CLI：看视频的助理。

闭环：视频 → ASR 出带时间戳字幕 → 存会话 → qwen 多轮对话(引用时间点) → 看细节(抽帧+字幕)。
一个视频一个会话，可追问(多轮)、可恢复指定会话、可按视频划分。模型 qwen。

用法:
  va.py new <视频路径|BV号> [--title T] [--force]
         开新会话：自动下载(若BV号)+语音识别存带时间戳字幕。同视频指纹复用已有会话。
  va.py ask <session_id> "问题"
         多轮追问：字幕全文+对话历史+问题 喂 qwen，回答带时间戳，存入会话历史。
  va.py clip <session_id> <start秒> <end秒> [--frames N] "问题"
         看细节：该时间段抽 N 帧 + 该段字幕 一起喂 qwen(多模态)回答细节。
  va.py show <session_id>
         看会话：元信息+字幕全文+对话历史。
  va.py list
         列所有会话。

示例:
  .venv/bin/python va.py new BV1xxx --title 测试
  .venv/bin/python va.py ask s-20260901-162000-ab12cd34 "这个视频在讲什么"
  .venv/bin/python va.py ask s-... "16秒那段具体说了啥"
  .venv/bin/python va.py clip s-... 16 20 --frames 3 "这段画面里有什么"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asr  # noqa: E402
import clip  # noqa: E402
import llm  # noqa: E402
import session  # noqa: E402

CFG = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))

_BILI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# ── 视频获取 ────────────────────────────────────────────────────
def _probe_dur(path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        timeout=30,
    ).strip())


def _curl_json(url: str) -> dict:
    """走 curl 子进程拉 JSON（requests 的 TLS 指纹会被 B站风控挡，curl 能通）。"""
    out = subprocess.check_output(
        ["curl", "-s", "--max-time", "30",
         "-A", _BILI_UA, "-H", "Referer: https://www.bilibili.com/", url],
        timeout=40,
    )
    return json.loads(out)


def _curl_file(url: str, out: Path, referer: str = "") -> None:
    cmd = ["curl", "-s", "--max-time", "300", "-A", _BILI_UA, "-o", str(out)]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    subprocess.check_output(cmd, timeout=320)


def _load_video(src: str):
    """src 是本地路径或 B站 BV 号，返回 (本地路径, 标题, 来源)。"""
    p = Path(src)
    if p.exists():
        return str(p), p.stem, "local"
    # bvid 大小写敏感，只判断前缀、不改写本体的大小写
    if "BV" in src.upper():
        bvid = src if src.upper().startswith("BV") else "BV" + src
        view = _curl_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
        if view.get("code") != 0:
            raise RuntimeError(f"B站 view 失败: {view.get('message')}")
        d = view["data"]
        title = d.get("title", "")
        play = _curl_json(
            f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={d['cid']}&qn=32&fnval=0")
        if play.get("code") != 0:
            raise RuntimeError(f"playurl 失败: {play.get('message')}")
        url = play["data"]["durl"][0]["url"]
        out = HERE / "_dl"
        out.mkdir(exist_ok=True)
        mp4 = out / f"{bvid}.mp4"
        _curl_file(url, mp4, referer="https://www.bilibili.com")
        return str(mp4), title or bvid, f"bilibili:{bvid}"
    raise SystemExit(f"无法识别的视频来源: {src}（要本地路径或含 BV 的 B站 号）")


def _resolve_sid(sid: str):
    """session_id 或目录路径 → 目录 Path。"""
    base = HERE / CFG.get("sessions_dir", "sessions")
    if (base / sid).exists():
        return base / sid
    if Path(sid).exists():
        return Path(sid)
    for m in session.list_sessions(CFG):
        if m["session_id"] == sid:
            return Path(m["dir"])
    return None


# ── 命令 ────────────────────────────────────────────────────────
def cmd_new(args) -> None:
    path, title, source = _load_video(args.src)
    dur = _probe_dur(path)
    vhash = asr.video_hash(path)
    existing = session.find_by_hash(CFG, vhash)
    if existing and not args.force:
        print(f"复用已有会话 {Path(existing).name}（同视频指纹 {vhash}），直接 ask 追问即可")
        print(f"SESSION_ID={Path(existing).name}")
        return
    title = args.title or title
    d, sid = session.new_session(CFG, title, source, dur, path, vhash)
    print(f"[new] 会话 {sid}", flush=True)
    print(f"[new] 标题:{title} 时长:{dur:.1f}s 来源:{source}", flush=True)
    print("[new] 正在语音识别(ASR, 首次加载模型约几分钟)...", flush=True)
    segs, info = asr.transcribe(path, CFG)
    session.save_subtitles(d, segs)
    print(f"[new] 完成 句数:{len(segs)} 语言:{info.language}", flush=True)
    for sg in segs:
        print(f"  [{sg['start']:.1f}-{sg['end']:.1f}] {sg['text']}")
    print(f"\nSESSION_ID={sid}")
    print(f"问内容: .venv/bin/python va.py ask {sid} \"你的问题\"")


def cmd_ask(args) -> None:
    d = _resolve_sid(args.session)
    if not d:
        raise SystemExit("会话不存在")
    meta = session.load_meta(d)
    transcript = session.load_transcript(d)
    hist = session.load_history(d)
    sys_prompt = (
        f"你是视频内容分析助理。下面是一部视频《{meta['title']}》(时长{meta['duration']}秒)的完整字幕,"
        f"每句带时间戳[起-止]秒。请基于字幕回答用户问题,回答中引用相关时间点(如 0:03-0:06)帮助定位。"
        f"用简体中文,口语,简洁,直接给答案,别套话。"
    )
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": "【视频字幕全文】\n" + transcript + "\n\n请基于以上字幕回答问题。"}]
    for h in hist:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": args.question})
    ans = llm.chat(messages, CFG)
    session.add_history(d, "user", args.question)
    session.add_history(d, "assistant", ans)
    print(ans)


def cmd_clip(args) -> None:
    d = _resolve_sid(args.session)
    if not d:
        raise SystemExit("会话不存在")
    meta = session.load_meta(d)
    video = meta["video_path"]
    if not Path(video).exists():
        raise SystemExit(f"视频文件不存在: {video}")
    s, e, n = args.start, args.end, args.frames
    frames = clip.frames_range(video, s, e, n, d / "frames")
    if not frames:
        raise SystemExit("该时间段没抽到帧")
    segs = session.load_subtitles(d)
    seg_lines = [
        f"[{g['start']:.1f}-{g['end']:.1f}] {g['text']}"
        for g in segs if (s - 0.5 <= g["start"] < e) or (s - 0.5 < g["end"] <= e) or (g["start"] < s and g["end"] > e)
    ]
    segtxt = "\n".join(seg_lines) or "(该段无字幕)"
    sys_p = (f"你是视频内容分析助理,正在查看视频《{meta['title']}》在 {s:.0f}-{e:.0f}秒的细节。"
             f"下面给你这一段抽的画面帧和该段字幕,结合画面和字幕回答用户问题。用简体中文,口语,简洁。")
    content = [{"type": "text", "text": f"【时间段 {s:.0f}-{e:.0f}秒 字幕】\n{segtxt}\n\n问题:{args.question}"}]
    for t, fp in frames:
        content.append({"type": "text", "text": f"(第{t:.0f}秒画面)"})
        content.append(llm.mm_img(fp))
    messages = [{"role": "system", "content": sys_p}, {"role": "user", "content": content}]
    ans = llm.chat(messages, CFG, max_tokens=800)
    session.add_history(d, "user", f"[clip {s:.0f}-{e:.0f}s] {args.question}")
    session.add_history(d, "assistant", ans, has_image=True)
    print(ans)


def cmd_show(args) -> None:
    d = _resolve_sid(args.session)
    if not d:
        raise SystemExit("会话不存在")
    meta = session.load_meta(d)
    print(f"会话 {meta['session_id']}")
    print(f"标题:{meta['title']}  来源:{meta['source']}  时长:{meta['duration']}s  轮数:{meta.get('turns', 0)}")
    print(f"创建:{meta['created']}  更新:{meta['updated']}")
    print("视频文件:", meta.get("video_path"))
    print("\n=== 字幕 ===")
    print(session.load_transcript(d) or "(无)")
    hist = session.load_history(d)
    if hist:
        print("\n=== 对话历史 ===")
        for h in hist:
            tag = "问" if h["role"] == "user" else "答"
            img = "(含图)" if h.get("has_image") else ""
            print(f"[{tag} {h['ts']} {img}] {h['content']}")


def cmd_list(args) -> None:
    ms = session.list_sessions(CFG)
    if not ms:
        print("(无会话)")
        return
    for m in ms:
        print(f"{m['session_id']}  {m['title'][:20]:20s}  {m['duration']:6.1f}s  {m.get('turns', 0):>2}轮  {m['updated']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="video_agent：看视频的助理")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("new"); n.add_argument("src"); n.add_argument("--title"); n.add_argument("--force", action="store_true")
    a = sub.add_parser("ask"); a.add_argument("session"); a.add_argument("question")
    c = sub.add_parser("clip"); c.add_argument("session"); c.add_argument("start", type=float)
    c.add_argument("end", type=float); c.add_argument("--frames", type=int, default=2); c.add_argument("question")
    s = sub.add_parser("show"); s.add_argument("session")
    sub.add_parser("list")
    args = ap.parse_args()
    {"new": cmd_new, "ask": cmd_ask, "clip": cmd_clip, "show": cmd_show, "list": cmd_list}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
