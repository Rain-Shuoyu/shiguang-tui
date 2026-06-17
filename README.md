# 拾光 / AfterGlow — TUI 版本

终端版 拾光。跟 [macOS 版](https://github.com/Rain-Shuoyu/AfterGlow-AI-Powered-Reflective-Journal-Manager) 共享同一份 Markdown 日记文件——你在 Mac 上写的，TUI 也能读；TUI 上写的，Mac 也能读。

> **v0.1** — 7 个核心 tab（写作 / 列表 / 日记 / 镜像 / 周年 / 急救 / AI），跨平台（macOS / Linux / Windows）。

## 安装

```bash
pip install --user afterglow-tui
# 或者
pipx install afterglow-tui
```

需要 Python 3.9+。

## 快速开始

```bash
# 1. 初始化日记目录（默认 ~/Documents/Journal）
glow --init

# 2. 启动 TUI
glow
```

或者直接指定目录：

```bash
glow --folder /path/to/diary
```

## 7 个模式

按数字键 `1`-`7` 切换：

| 键 | 模式 | 说明 |
| --- | --- | --- |
| `1` | **写作** | 列表视图，新建/删除 |
| `2` | **列表** | 全部日记，按月分组 |
| `3` | **日记** | **默认视图**：今天的日记 + 今日签 + 周年 + 急救 |
| `4` | **镜像** | 5-7 句自己写过的话（多样性采样） |
| `5` | **周年** | 往年今天你写过什么 |
| `6` | **急救** | 连续 3 天情绪低时浮现 |
| `7` | **AI** | 自由问答（v0.2 计划） |

`?` 看帮助。`q` 退出。

## 配置

LLM API 配置存在 `~/.config/shiguang/state.json`（macOS 是 `~/Library/Application Support/ShiGuang/`）。

v0.1 的 TUI **不暴露配置 UI**——直接编辑 JSON 即可：

```json
{
  "llm": {
    "provider": "minimax",
    "base_url": "https://api.minimax.chat",
    "api_key": "sk-...",
    "model": "MiniMax-M2.7"
  },
  "diary_folder": "/Users/you/Documents/Journal"
}
```

v0.2 会加 `glow config` 交互式配置。

## v0.1 不做的

- 写信 ✍️（要富文本编辑 + LLM 写主体，复杂）
- 自我追问 📓（TUI 不太合适，留 GUI）
- 关系图谱 🔗（终端画不动）
- 实时流式 AI 问答 💬（v0.2）
- iCloud 同步 / 多日记本

## 开发

```bash
git clone https://github.com/Rain-Shuoyu/AfterGlow-AI-Powered-Reflective-Journal-Manager
cd shiguang-tui
pip install --user -e .

# Run from source
PYTHONPATH=src python3 -m shiguang

# Sanity check
PYTHONPATH=src python3 -m shiguang --sanity-check /path/to/diary
```

## 文件结构

```
shiguang-tui/
├── pyproject.toml
├── src/shiguang/
│   ├── __main__.py        # CLI entry
│   ├── app.py             # Textual app + 7 mode renderers
│   ├── config.py          # state.json + paths
│   ├── diary.py           # .md read/write
│   ├── frontmatter.py     # YAML frontmatter parser
│   ├── llm.py             # OpenAI/Anthropic streaming
│   ├── init_cmd.py        # `shi --init`
│   ├── sanity.py          # `shi --sanity-check`
│   └── algorithms/
│       ├── daily_practice.py   # 24 题
│       ├── anniversary.py      # m/d 匹配
│       ├── rescue.py           # 情绪检测
│       └── mirror.py           # MMR 采样
```

## License

MIT
