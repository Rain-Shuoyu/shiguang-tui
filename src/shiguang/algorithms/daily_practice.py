"""📓 今日签 — daily micro-practice.

24 prompts across 8 categories. Same date-hash picker as the
macOS app, so a user moving between the two will see the same
prompt on the same day.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional


@dataclass
class Prompt:
    id: int
    category: str
    text: str


# Same 24 prompts as the macOS app. Don't reorder; existing
# entries reference the same id.
POOL: list[Prompt] = [
    # 感激
    Prompt(0, "感激", "写下 3 件今天发生的小确幸，哪怕很无聊"),
    Prompt(1, "感激", "今天谁帮了你一个忙？哪怕对方自己都没意识到"),
    Prompt(2, "感激", "你身体里哪个部位今天感觉舒服？"),
    # 承认
    Prompt(3, "承认", "承认一个你今天回避的感受"),
    Prompt(4, "承认", "你今天对自己撒了什么谎？"),
    Prompt(5, "承认", "今天哪一刻你假装没事？"),
    # 自我对话
    Prompt(6, "自我对话", "用 1 句话告诉 3 个月前的自己，他现在没你想的那么糟"),
    Prompt(7, "自我对话", "现在的你最想跟谁说话？写第一句"),
    Prompt(8, "自我对话", "如果明天的你看到今天的记录，会说什么？"),
    # 观察
    Prompt(9, "观察", "你今天身体哪个部位最紧绷？它在说什么？"),
    Prompt(10, "观察", "今天的天气和你的心情匹配吗？"),
    Prompt(11, "观察", "你今天笑了多少次？真的笑了几次？"),
    # 行动
    Prompt(12, "行动", "明天做一件 5 分钟内能完成的小事，写下来"),
    Prompt(13, "行动", "今天能不能给别人一个具体的小帮助？"),
    Prompt(14, "行动", "今晚睡前做一件让身体放松的事，记下是什么"),
    # 问题
    Prompt(15, "问题", "你现在最想被谁看见？"),
    Prompt(16, "问题", "你最近一次说『算了』是什么时候？"),
    Prompt(17, "问题", "你现在最害怕失去的是什么？"),
    # 欣赏
    Prompt(18, "欣赏", "今天做的哪件事虽然没人看到，但你很为自己骄傲？"),
    Prompt(19, "欣赏", "你最近一次坚持完成的事是什么？"),
    Prompt(20, "欣赏", "你身体里哪个特质今天帮了你？"),
    # 释放
    Prompt(21, "释放", "写下一个你已经准备好放下的念头，一句就行"),
    Prompt(22, "释放", "你最近在心里反复演哪段对话？让它停在这里"),
    Prompt(23, "释放", "你今天累的不是身体，是哪里？"),
]


def pick_for(date: date_cls) -> Prompt:
    """Pick today's prompt by date-hash. Same day → same prompt."""
    seed = date.year * 10000 + date.month * 100 + date.day
    return POOL[abs(seed) % len(POOL)]


def is_done_today(state, today: Optional[date_cls] = None) -> bool:
    """True iff the user has already marked today's prompt done."""
    today = today or date_cls.today()
    if state.daily_practice_last_done_date != today.isoformat():
        return False
    p = pick_for(today)
    return state.daily_practice_last_done_prompt_id == p.id


def mark_done(state, today: Optional[date_cls] = None) -> None:
    """Mark today's prompt as done, bumping streak if yesterday was also done."""
    today = today or date_cls.today()
    p = pick_for(today)
    if is_done_today(state, today):
        return
    from datetime import date as dc, timedelta
    yesterday = today - timedelta(days=1)
    if state.daily_practice_last_done_date == yesterday.isoformat():
        state.daily_practice_streak += 1
    else:
        state.daily_practice_streak = 1
    state.daily_practice_last_done_date = today.isoformat()
    state.daily_practice_last_done_prompt_id = p.id
    if state.daily_practice_streak > state.daily_practice_longest:
        state.daily_practice_longest = state.daily_practice_streak
