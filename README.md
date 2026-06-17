# 拾光 / AfterGlow (TUI)

```
 ██████   ██        ███████  ██        ██
██    ██  ██       ██     ██ ██   ██   ██
██        ██       ██     ██ ██   ██   ██
██   ████ ██       ██     ██ ██   ██   ██
██    ██  ██       ██     ██ ██   ██   ██
██    ██  ██       ██     ██ ██   ██   ██
 ██████   ████████  ███████  ████    ████
```

一个给你自己用的日记工具。

`Markdown` 存盘、终端里写、终端里读。不想打开 GUI、但又想坚持记点东西的时候用。

跟 [macOS 版](https://github.com/Rain-Shuoyu/AfterGlow-AI-Powered-Reflective-Journal-Manager) 用同一份 `.md` 文件格式——你在 Mac 上写的，TUI 也能读；TUI 上写的，Mac 也能读。

## 装

```bash
pip install afterglow-tui
```

要 `Python 3.9+`。其他方式：

```bash
pipx install afterglow-tui    # 隔离环境装
```

## 用

```bash
glow --init     # 初始化日记目录（默认 ~/Documents/Journal）
glow            # 开 TUI
```

或者直接指定目录：

```bash
glow --folder /path/to/diary
```

## 四个 tab

| 按键 | tab       | 干啥的                                             |
| ---- | --------- | -------------------------------------------------- |
| `0`  | 首页      | GLOW 标识 + 三项菜单                              |
| `1`  | 数据面板  | 写作天数、字数、心情分布、月度趋势、Tag 频率、词云 |
| `2`  | 创作笔记  | 列表 + `TextArea` 编辑器，写今天的                |
| `3`  | 洞察笔记  | 全部日记，左边选、右边预览                        |

每个 tab 内 `?` 看帮助，`q` 退。

## 关键按键

```
↑↓ / j k        上下移动
← / Esc          返回 / 切到上一个 focus
→ / Enter        进入 / 切到下一个 focus
Ctrl+S           保存当前编辑
n                新建今日（连续按两次确认覆盖）
d                删除当前（连续按两次确认）
c                改日记目录
0                回首页
?                帮助
q                退出
```

browse / edit 模式里两个 pane 之间切换是 `Enter` 进、`Esc` 退。

## 状态文件

```
~/.config/shiguang/state.json   # Linux
~/Library/Application Support/ShiGuang/state.json   # macOS
```

默认日记目录是 `~/Documents/Journal`，也可以用 `SHIGUANG_FOLDER` 环境变量覆盖。

LLM 配置（v0.2 还没接，先把字段留好）：

```json
{
  "diary_folder": "/Users/you/Documents/Journal"
}
```

## 自己改

```bash
git clone https://github.com/Rain-Shuoyu/shiguang-tui.git
cd shiguang-tui
pip install -e .

# 跑
glow --folder /path/to/test/diary

# 跑非 TUI 自检（确认 diary 能扫、stats 能算）
glow --sanity-check --folder /path/to/diary
```

模块分工（v0.2.14）：

```
src/shiguang/
├── app.py            Textual App + 4 个 mode 的调度
├── home_view.py      首页 widget
├── edit_view.py      编辑 tab widget
├── browse_view.py    洞察 tab widget
├── modals.py         HelpScreen + ChangeFolderScreen
├── stats.py          统计计算（无 Textual 依赖）
├── diary.py          .md 读写
├── frontmatter.py    YAML frontmatter
├── markup.py         md → rich markup
├── logo.py           GLOW 标识
├── theme.py          AMBER 调色板 + 字符常量
├── format.py         visual_width / 8 阶条形图
├── config.py         state.json I/O
├── init_cmd.py       `glow --init`
├── sanity.py         `glow --sanity-check`
└── __main__.py       CLI 入口
```

## License

MIT
