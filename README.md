# video_agent

**看视频的助理**。闭环：

```
视频 → ASR 出带时间戳字幕 → 存会话 → LLM 多轮对话(引用时间点) → 看细节(抽帧+字幕喂多模态)
```

一个视频一个会话，可追问（多轮）、可恢复指定会话、可按视频划分。给 B站 BV 号自动下载。
按需 CLI 工具（非常驻），`va.py` 驱动。

## 文件

| 文件 | 职责 |
|---|---|
| `va.py` | CLI 入口：new / ask / clip / show / list 五个子命令 + B站下载 |
| `asr.py` | 语音识别：faster-whisper，出**带时间戳**字幕（HF 镜像 + 关 xet） |
| `llm.py` | LLM 调用：OpenAI 兼容端点，思考型模型（reasoning_content） |
| `clip.py` | 抽帧：指定时间段抽 N 帧给多模态 LLM 看画面细节 |
| `session.py` | 会话管理：一个视频一个会话，存字幕 + 多轮对话历史，可恢复 |
| `test_asr.py` | ASR 冒烟测试 |
| `config.yaml` | 配置（ASR 模型 / LLM 端点 / 抽帧数） |

## 用法

```bash
# 开新会话（本地路径或 BV 号；BV 号自动下载 + ASR）
.venv/bin/python va.py new BV1xxx --title 测试
.venv/bin/python va.py new /path/to/video.mp4

# 多轮追问（回答带时间戳）
.venv/bin/python va.py ask s-20260901-162000-ab12cd "这个视频在讲什么"
.venv/bin/python va.py ask s-... "16秒那段具体说了啥"

# 看细节（该时间段抽 N 帧 + 该段字幕 喂多模态 LLM）
.venv/bin/python va.py clip s-... 16 20 --frames 3 "这段画面里有什么"

.venv/bin/python va.py show s-...   # 看会话（元信息+字幕全文+对话历史）
.venv/bin/python va.py list         # 列所有会话
```

## 配置

`config.yaml`：

| 段 | 键 | 默认 | 说明 |
|---|---|---|---|
| `asr` | model_size | small | whisper tiny/base/small/medium/large-v3；CPU 上 small 是质量/速度平衡点 |
| | compute_type | int8 | CPU 用 int8（省内存快） |
| | language | zh | 强制中文 |
| | vad_filter | true | 静音检测，跳过无人声段 |
| `llm` | base_url | http://127.0.0.1:9000/v1 | **占位，换成你的 LLM 端点** |
| | model | qwen3.8-27b | 思考型模型，max_tokens 要留足 |
| `clip` | frames_default | 2 | 看细节默认抽几帧 |

## 依赖

- Python 3.10+
- `faster-whisper`、`pyyaml`、`openai`（或任意 OpenAI 兼容 SDK）
- `ffmpeg` / `ffprobe`（在 PATH，抽帧 + 探时长）
- `opencc`（可选，繁转简；装不上自动跳过）
- B站下载：`curl`（**注意用 curl 不用 requests**——requests 的 TLS 指纹会被 B站风控挡，curl 能通）

## 设计要点 / 已知坑

- **ASR 走 HF 镜像**：`HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`
  （直连和 xet 协议都被挡，镜像 + 关 xet 才行）。
- **B站下载走 curl 子进程**：带 UA + Referer。requests 直连会被风控拦。
- **bvid 大小写敏感**：只判前缀、不改写大小写（`src.upper()` 会破坏 bvid）。
- **字幕带时间戳**是这套的关键：追问时 LLM 能引用「X 秒那段说了啥」，
  看细节也能精确到时间段抽帧，而不是整片喂。
- **一个视频一个会话**：同视频指纹复用已有会话，追问在同一会话里累积历史。

—— 幻日出品
