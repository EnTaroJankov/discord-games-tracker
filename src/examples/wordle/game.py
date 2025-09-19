import re
import logging
from typing import List, Dict, Any
from src.core.dates import date_to_num
import discord

logger = logging.getLogger(__name__)

# New-format summary lines like:
#   "👑 3/6: @tim"
#   "X/6: @bob @joe"
LINE_PATTERN = re.compile(
    r'(?m)^\s*(?:\S+\s+)?'
    r'(?P<tries>\d+|X)\s*/\s*(?P<total>\d+)\s*'
    r':\s*(?P<handles>(?:<@!?\d+>|@[A-Za-z0-9._-]+)'
    r'(?:\s+(?:<@!?\d+>|@[A-Za-z0-9._-]+))*)\s*$'
)

def _iter_result_lines(text: str):
    for m in LINE_PATTERN.finditer(text):
        tries_token = m.group("tries")
        total = int(m.group("total"))
        handles = m.group("handles").split()
        if handles:
            yield tries_token, total, handles

def _resolve_member_from_token(msg, token):
    # Direct user mention: <@123> or <@!123>
    if token.startswith("<@") and token.endswith(">"):
        raw = token[2:-1].lstrip("!")
        return int(raw) if raw.isdigit() else None

    # Plain-text handle: @someone
    if token.startswith("@") and getattr(msg, "guild", None):
        handle = token[1:].strip()

        # Case-insensitive exact matches against several name fields
        handle_ci = handle.casefold()

        def normalize(s: str) -> str:
            # Keep only alphanumerics for fuzzy matching
            return "".join(ch for ch in s if ch.isalnum()).casefold()

        candidates = []
        for m in msg.guild.members:
            usernames = [
                getattr(m, "name", "") or "",
                getattr(m, "display_name", "") or "",
                getattr(getattr(m, "global_name", None), "strip", lambda: "")() if hasattr(m, "global_name") else (getattr(m, "global_name", None) or ""),
            ]
            # Exact case-insensitive match on any field
            if any((u and u.casefold() == handle_ci) for u in usernames):
                return m.id
            candidates.append((m, usernames))

        # Try normalized exact match (strip non-alphanum)
        handle_norm = normalize(handle)
        for m, usernames in candidates:
            if any((u and normalize(u) == handle_norm) for u in usernames):
                return m.id

        # As a last resort, try unique prefix match (case-insensitive) on any field
        prefix_matches = []
        for m, usernames in candidates:
            if any((u and u.casefold().startswith(handle_ci)) for u in usernames):
                prefix_matches.append(m)

        if len(prefix_matches) == 1:
            return prefix_matches[0].id

        # If ambiguous or no match, fall through
        logger.warning("resolve_member: could not uniquely resolve handle '%s' in guild '%s'", handle, getattr(msg.guild, "name", None))

    return None

class WordleGame:
    async def parse_message(self, msg) -> List[Dict[str, Any]]:
        ts_local = msg.created_at
        # Map message timestamp to today’s puzzle number (cap at newest today)
        puzzle_num = await date_to_num(ts_local)
        newest_num = await date_to_num()
        if puzzle_num > newest_num:
            logger.debug("parse_message: puzzle_num > newest_num; capping %s -> %s", puzzle_num, newest_num)
            puzzle_num = newest_num

        items: List[Dict[str, Any]] = []
        any_line_parsed = False
        line_matches = list(_iter_result_lines(getattr(msg, "content", "") or ""))
        if not line_matches:
            #logger.debug("parse_message: no matching lines for msg id=%s content='%s...'", getattr(msg, "id", None), (msg.content or "")[:80])
            return []

        logger.debug("parse_message: found %s result lines in msg id=%s", len(line_matches), getattr(msg, "id", None))

        for tries_tok, total, handle_tokens in line_matches:
            # Generalized result field: 'score' instead of Wordle-specific 'tries'
            score_val = int(tries_tok) if str(tries_tok).isdigit() else str(tries_tok)
            for tok in handle_tokens:
                member_id = _resolve_member_from_token(msg, tok)
                if member_id is None:
                    logger.warning("parse_message: could not resolve handle token '%s' in msg id=%s", tok, getattr(msg, "id", None))
                    continue
                items.append({
                    "member_id": member_id,
                    "score": score_val,
                    "number": puzzle_num,
                    "timestamp": msg.created_at,
                    "meta": {"total": total}
                })
                any_line_parsed = True

        if not any_line_parsed:
            logger.debug("parse_message: no valid handles resolved in msg id=%s", getattr(msg, "id", None))
        else:
            logger.debug("parse_message: parsed %s items from msg id=%s", len(items), getattr(msg, "id", None))

        return items if any_line_parsed else []

    async def build_stats_embed(self, user_dict, bot, helpers) -> discord.Embed:
        """
        Build and return a Discord embed for the current stats.

        user_dict: mapping of user_id -> per-user stats object/dict
        bot: discord.Client or commands.Bot instance
        helpers: dict exposing:
            - "longest_all_time_streak": callable(user, is_win: Optional[Callable[[result], bool]] = None) -> int
            - "total_games_played": callable(user) -> int
        Wordle-specific aggregates (like total_ones/total_x) are computed here.
        """
        # Defensive import if needed
        import discord  # type: ignore
        from datetime import datetime, timedelta, timezone

        embed = discord.Embed(
            title="Wordle Stats",
            description="Summary of player performance",
            color=discord.Color.blurple(),
        )

        def _to_aware_utc(ts):
            # Normalize timestamps: handle naive as UTC, aware convert to UTC
            if ts is None:
                return None
            if getattr(ts, "tzinfo", None) is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)

        def _avg(nums):
            nums = [n for n in nums if isinstance(n, (int, float))]
            return round(sum(nums) / len(nums), 2) if nums else None

        now_utc = datetime.now(timezone.utc)
        cutoff_30 = now_utc - timedelta(days=30)
        cutoff_7 = now_utc - timedelta(days=7)

        # Aggregate per-user stats
        per_user_rows = []
        totals = {"games": 0, "ones": 0, "x": 0}

        for user_id, user_obj in (user_dict or {}).items():
            total_games = 0
            best_streak = 0
            total_ones = 0
            total_x = 0

            try:
                total_games = int(helpers["total_games_played"](user_obj))
            except Exception:
                total_games = 0

            # Wordle win predicate: any score not equal to 'X'
            win_predicate = lambda r: getattr(r, "score", None) != 'X'

            try:
                best_streak = int(helpers["longest_all_time_streak"](user_obj, is_win=win_predicate))
            except Exception:
                best_streak = 0

            # Wordle-specific counts derived from generalized 'score' + averages
            results = getattr(user_obj, "results", []) or []

            # Lifetime numeric scores (exclude 'X')
            lifetime_scores = []
            month_scores = []
            week_scores = []

            for r in results:
                sc = getattr(r, "score", None)
                ts = _to_aware_utc(getattr(r, "timestamp", None))
                if isinstance(sc, str) and sc.isdigit():
                    sc = int(sc)
                is_numeric = isinstance(sc, int)

                if is_numeric:
                    lifetime_scores.append(sc)
                    if ts and ts >= cutoff_30:
                        month_scores.append(sc)
                    if ts and ts >= cutoff_7:
                        week_scores.append(sc)

            try:
                total_ones = sum(1 for r in results if getattr(r, "score", None) == 1)
            except Exception:
                total_ones = 0
            try:
                total_x = sum(1 for r in results if getattr(r, "score", None) == 'X')
            except Exception:
                total_x = 0

            avg_all = _avg(lifetime_scores)
            avg_30 = _avg(month_scores)
            avg_7 = _avg(week_scores)

            totals["games"] += total_games
            totals["ones"] += int(total_ones or 0)
            totals["x"] += int(total_x or 0)

            # Resolve a readable name/mention
            member = bot.get_user(int(user_id)) if user_id is not None else None
            display = member.mention if member is not None else f"<@{user_id}>"

            per_user_rows.append({
                "user_id": user_id,
                "display": display,
                "games": int(total_games or 0),
                "ones": int(total_ones or 0),
                "x": int(total_x or 0),
                "streak": int(best_streak or 0),
                "avg_all": avg_all,
                "avg_30": avg_30,
                "avg_7": avg_7,
            })

        # Sort by most games played; then by best streak
        per_user_rows.sort(key=lambda r: (r["games"], r["streak"]), reverse=True)

        # Build a concise leaderboard (top 10)
        def fmt_avg(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else "—"

        if per_user_rows:
            lines = []
            for idx, row in enumerate(per_user_rows[:10], start=1):
                lines.append(
                    f"{idx}. {row['display']} — Games: {row['games']}, 1️⃣: {row['ones']}, ❌: {row['x']}, "
                    f"Best Streak: {row['streak']} | Avg (All/30d/7d): "
                    f"{fmt_avg(row['avg_all'])}/{fmt_avg(row['avg_30'])}/{fmt_avg(row['avg_7'])}"
                )
            embed.add_field(
                name="Leaderboard",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="Leaderboard",
                value="No data available yet.",
                inline=False,
            )

        # Totals summary
        embed.add_field(
            name="Totals",
            value=f"Games: {totals['games']} • 1️⃣: {totals['ones']} • ❌: {totals['x']}",
            inline=False,
        )

        return embed