"""qwen 端点封装（文本 + 多模态）。

端点是思考型模型：正式回答在 message.content，思考在 reasoning_content。
只取 content；max_tokens 要留足，否则正文被 reasoning 吃光变空。
"""
from __future__ import annotations

import base64

import requests


def _lcfg(cfg: dict) -> dict:
    return cfg.get("llm", {})


def chat(messages: list, cfg: dict, max_tokens: int | None = None) -> str:
    """发一轮对话，返回正式回答文本。"""
    c = _lcfg(cfg)
    r = requests.post(
        c["base_url"].rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + c.get("api_key", ""), "Content-Type": "application/json"},
        json={"model": c.get("model", "qwen3.8-27b"), "messages": messages,
              "max_tokens": max_tokens or c.get("max_tokens", 1024)},
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


def img_b64(path: str) -> str:
    return base64.b64encode(open(path, "rb").read()).decode()


def mm_text(text: str) -> dict:
    return {"type": "text", "text": text}


def mm_img(path: str) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64(path)}}
