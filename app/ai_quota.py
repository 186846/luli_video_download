"""免费用户 AI 总结每日配额（按 Asia/Shanghai 自然日）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import FREE_AI_SUMMARIZE_DAILY
from app.db import get_conn

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001 — Windows 无 tzdata 时回退 UTC+8
    TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def get_summarize_count(user_id: int, day: str | None = None) -> int:
    day = day or today_str()
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT summarize_count FROM ai_daily_usage
            WHERE user_id = ? AND usage_date = ?
            """,
            (user_id, day),
        ).fetchone()
        return int(row["summarize_count"]) if row else 0
    finally:
        conn.close()


def remaining_summarize(user: dict) -> int | None:
    """VIP 返回 None（无限）；免费返回剩余次数。"""
    if user.get("is_vip"):
        return None
    used = get_summarize_count(user["id"])
    return max(0, FREE_AI_SUMMARIZE_DAILY - used)


def consume_summarize_quota(user: dict) -> dict:
    """
    创建总结前调用：校验并扣减 1 次。
    返回 { remaining, used, daily_limit, is_vip }。
    未登录由调用方先判；免费超额抛 ValueError。
    """
    if user.get("is_vip"):
        return {
            "is_vip": True,
            "remaining": None,
            "used": 0,
            "daily_limit": FREE_AI_SUMMARIZE_DAILY,
        }

    day = today_str()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT summarize_count FROM ai_daily_usage
            WHERE user_id = ? AND usage_date = ?
            """,
            (user["id"], day),
        ).fetchone()
        used = int(row["summarize_count"]) if row else 0
        if used >= FREE_AI_SUMMARIZE_DAILY:
            conn.rollback()
            raise ValueError(
                f"今日免费 AI 总结已用完（{FREE_AI_SUMMARIZE_DAILY} 次/天），请升级永久会员"
            )
        if row:
            conn.execute(
                """
                UPDATE ai_daily_usage
                SET summarize_count = summarize_count + 1
                WHERE user_id = ? AND usage_date = ?
                """,
                (user["id"], day),
            )
        else:
            conn.execute(
                """
                INSERT INTO ai_daily_usage (user_id, usage_date, summarize_count)
                VALUES (?, ?, 1)
                """,
                (user["id"], day),
            )
        conn.commit()
        used += 1
        return {
            "is_vip": False,
            "remaining": max(0, FREE_AI_SUMMARIZE_DAILY - used),
            "used": used,
            "daily_limit": FREE_AI_SUMMARIZE_DAILY,
        }
    except ValueError:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def quota_snapshot(user: dict) -> dict:
    rem = remaining_summarize(user)
    used = 0 if user.get("is_vip") else get_summarize_count(user["id"])
    return {
        "is_vip": bool(user.get("is_vip")),
        "ai_summarize_remaining": rem,
        "ai_summarize_used_today": used,
        "ai_summarize_daily_limit": FREE_AI_SUMMARIZE_DAILY,
    }
