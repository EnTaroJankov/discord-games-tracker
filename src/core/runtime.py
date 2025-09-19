#!/usr/bin/python

from datetime import datetime, timezone, date as _date
from typing import Dict, Any, Iterable
import logging
import calendar

# Local imports
from .user import User
from .models import Result
from .dates import date_to_num, date_format, min_date
from .game_protocol import Game

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Stats helpers (reused by game plugins)
# -----------------------------------------------------------------------------

def _numeric_scores(user):
    """
    Generic helper: return numeric score values from user results.
    """
    vals: list[int] = []
    for r in getattr(user, "results", []) or []:
        score = getattr(r, "score", None)
        if isinstance(score, int):
            vals.append(score)
            continue
        # If score is a numeric string, coerce
        try:
            if isinstance(score, str) and score.isdigit():
                vals.append(int(score))
        except Exception:
            continue
    return vals

def _total_games_played(user) -> int:
    """
    Generic total games played: count all recorded results.
    Assumes each user has a 'results' list.
    """
    results = getattr(user, "results", []) or []
    return len(results)

def _longest_all_time_streak(user, is_win=None) -> int:
    """
    Generic longest streak across all-time puzzle/round numbers.

    is_win: optional predicate(result) -> bool to determine wins for the streak.
            Defaults to treating any numeric score as a win.
    """
    results = getattr(user, "results", []) or []
    if not results:
        return 0

    def default_is_win(r):
        score = getattr(r, "score", None)
        return isinstance(score, int)

    win_fn = is_win or default_is_win

    # Collect numbers that are wins according to the predicate
    try:
        wins = {int(getattr(r, "number")) for r in results if win_fn(r)}
    except Exception:
        wins = set()

    if not wins:
        return 0

    # Find the longest consecutive streak among wins
    longest = 0
    for n in wins:
        if (n - 1) not in wins:
            cur, length = n, 1
            while (cur + 1) in wins:
                cur += 1
                length += 1
            longest = max(longest, length)
    return longest

async def print_stats(text_channel, user_dict: Dict[int, Any], bot, game: Game, send_results: bool = True):
    embed = await game.build_stats_embed(
        user_dict, bot,
        helpers={
            "longest_all_time_streak": _longest_all_time_streak,
            "total_games_played": _total_games_played,
        }
    )

    if not send_results:
        # Pretty-print the embed to stdout instead of sending to Discord
        print("==== Stats (DEBUG) ====")
        title = getattr(embed, "title", None) or ""
        desc = getattr(embed, "description", None) or ""
        print(f"Title: {title}")
        if desc:
            print(f"Description: {desc}")
        # Iterate embed fields safely
        fields = getattr(embed, "fields", []) or []
        for f in fields:
            name = getattr(f, "name", "")
            value = getattr(f, "value", "")
            print(f"\n{name}\n{'-' * len(name)}\n{value}")
        footer = getattr(getattr(embed, "footer", None), "text", None)
        if footer:
            print(f"\nFooter: {footer}")
        print("==== End Stats (DEBUG) ====")
        return

    await text_channel.send(embed=embed)

# -----------------------------------------------------------------------------
# Parse a message (delegates to the game plugin)
# -----------------------------------------------------------------------------
async def parse_result(msg, user_dict: Dict[int, Any], game: Game) -> int:
    """
    Parse a Discord message via the game plugin and store results.
    Returns the number of results ingested from this message.
    """
    try:
        parsed_items = await game.parse_message(msg)
    except Exception as e:
        logger.exception("parse_result: game.parse_message raised for msg id=%s", getattr(msg, "id", None))
        return 0

    if not parsed_items:
        logger.debug("parse_result: no parsable results in message id=%s", getattr(msg, "id", None))
        return 0

    ingested = 0
    for item in parsed_items:
        try:
            member_id = item["member_id"]
            # Generic field name
            score_val = item["score"]
            number = item["number"]
            timestamp = item.get("timestamp", msg.created_at)
            meta = item.get("meta", {})

            member = msg.guild.get_member(member_id) if getattr(msg, "guild", None) else None
            if member_id not in user_dict:
                if member is None:
                    class _Stub:
                        def __init__(self, uid):
                            self.id = uid
                            self.name = str(uid)
                            self.display_name = str(uid)
                    user_dict[member_id] = User(_Stub(member_id))
                    logger.debug("parse_result: created stub User for member_id=%s", member_id)
                else:
                    user_dict[member_id] = User(member)
                    logger.debug("parse_result: created User for member_id=%s (%s)", member_id, member.display_name)

            result = Result(
                number=number,
                score=score_val,            # keep legacy populated
                timestamp=timestamp,
                meta=meta
            )
            # Attach generic field for new code paths
            try:
                setattr(result, "score", score_val)
            except Exception:
                pass

            await user_dict[member_id].add_result(result)
            logger.info(
                "parse_result: stored result member_id=%s number=%s score=%s ts=%s",
                member_id, number, score_val, getattr(timestamp, "isoformat", lambda: timestamp)()
            )
            ingested += 1
        except KeyError as ke:
            logger.exception("parse_result: missing required key %s in item for msg id=%s", ke, getattr(msg, "id", None))
        except Exception:
            logger.exception("parse_result: failed to process one item from msg id=%s", getattr(msg, "id", None))

    return ingested

# -----------------------------------------------------------------------------
# Catch up history (uses dates config and game parser)
# -----------------------------------------------------------------------------
async def catchup(text_channel, user_dict: Dict[int, Any], game: Game):
    logger.info("Catching up in channel/thread '%s'", getattr(text_channel, "name", str(text_channel)))
    start_date = datetime.strptime(min_date, date_format)
    total_messages = 0
    total_results = 0

    async for msg in text_channel.history(limit=None, after=start_date):
        total_messages += 1
        count = await parse_result(msg, user_dict, game)
        total_results += count

    logger.info("Catchup scanned %s messages, ingested %s results", total_messages, total_results)

    today_num = await date_to_num()
    for user in user_dict.values():
        last = user.get_last_result()
        if last is None:
            continue
        if last.number == today_num:
            user.played_today = True

    # Generic streak recomputation:
    # default rule: any numeric score counts as a win.
    def _is_win_default(res) -> bool:
        score = getattr(res, "score", None)
        return isinstance(score, int)

    for user in user_dict.values():
        last_result = user.get_last_result()
        if last_result is None:
            user.cur_streak = 0
            continue

        today_num = await date_to_num()
        check_num = today_num
        cur_streak = 0

        if int(last_result.number) == today_num and _is_win_default(last_result):
            cur_streak += 1
        else:
            check_num -= 1

        for result in reversed(user.results):
            if int(result.number) == today_num:
                check_num -= 1
                continue
            if int(result.number) == check_num and _is_win_default(result):
                check_num -= 1
                cur_streak += 1
                continue
            else:
                break

        user.cur_streak = cur_streak

    logger.info("All caught up in %s (users=%s)", getattr(text_channel, "name", str(text_channel)), len(user_dict))

    # Schedule a single daily update (idempotent via job_id)
    # schedule_daily_midnight(lambda: update_streaks(user_dict), job_id="update_streaks")

async def print_month_calendars(user_dict: Dict[int, Any], year: int, month: int, tz=timezone.utc):
    """
    Print, to stdout, a calendar grid per user for the specified year/month.
    Shows the actual score for played days, X for past missed days,
    and blanks for days outside the month or in the future.
    """
    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    today = datetime.now(tz).date()

    # Visual “font size”: wider cells for better readability
    cell_w = 4  # increase for a larger appearance

    def fmt_cell(val: str | None) -> str:
        s = "" if val is None else str(val)
        return s.center(cell_w)

    # Precompute mapping from calendar date -> puzzle/round number
    day_to_num: dict[_date, int] = {}
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            if d.month != month:
                continue
            dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz)
            day_to_num[d] = await date_to_num(dt)

    # Header built to match cell width
    days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    week_header = "".join(fmt_cell(d) for d in days)

    for uid, user in user_dict.items():
        results = getattr(user, "results", []) or []
        # Map puzzle/round number -> score for quick lookup
        number_to_score = {}
        for r in results:
            n = getattr(r, "number", None)
            if n is not None:
                number_to_score[int(n)] = getattr(r, "score", None)

        display = getattr(getattr(user, "author", None), "display_name", None) or \
                  getattr(getattr(user, "author", None), "name", None) or str(uid)

        print("")
        print(f"===== {display} — {calendar.month_name[month]} {year} =====")
        print(week_header)

        for week in cal.monthdatescalendar(year, month):
            row_cells = []
            for d in week:
                if d.month != month:
                    row_cells.append(fmt_cell(None))  # overflow day
                    continue
                if d > today:
                    row_cells.append(fmt_cell(None))  # future day stays blank
                    continue
                num = day_to_num.get(d)
                score = number_to_score.get(num)
                if score is None:
                    row_cells.append(fmt_cell("X"))   # missed past day
                else:
                    row_cells.append(fmt_cell(score))  # show actual score
            print("".join(row_cells).rstrip())

        # Summary line (don’t count future days as missed)
        total_days_in_month = sum(1 for d in day_to_num.keys() if d <= today)
        played_days = sum(1 for d, n in day_to_num.items() if d <= today and n in number_to_score)
        missed_days = total_days_in_month - played_days
        print(f"Played: {played_days}/{total_days_in_month} — Missed: {missed_days}")

def _collect_scores_for_numbers(results: Iterable[Any]) -> Dict[int, Any]:
    """
    Build a mapping number -> score (int 1..6 or 'X'), preserving 'X' for Wordle failures.
    """
    mapping: Dict[int, Any] = {}
    for r in results or []:
        n = getattr(r, "number", None)
        s = getattr(r, "score", None)
        if n is None:
            continue
        # Keep 'X' as-is; coerce numeric strings to ints
        if isinstance(s, int):
            mapping[int(n)] = s
        elif isinstance(s, str):
            if s.isdigit():
                mapping[int(n)] = int(s)
            elif s.upper() == "X":
                mapping[int(n)] = "X"
    return mapping

def _wordle_score_to_emoji(score: Any) -> str:
    """
    Map Wordle scores to unique color squares:
      1 -> 🟩, 2 -> 🟦, 3 -> 🟨, 4 -> 🟧, 5 -> 🟥, 6 -> 🟫, 'X' -> 🟪
    """
    if isinstance(score, str) and score.upper() == "X":
        return "🟪"
    if isinstance(score, int):
        return {
            1: "🟩",
            2: "🟦",
            3: "🟨",
            4: "🟧",
            5: "🟥",
            6: "🟫",
        }.get(score, "⬛")
    return "⬛"
# ... existing code ...
async def send_last_n_month_calendars(
    text_channel,
    user_dict: Dict[int, Any],
    n_months: int,
    end_dt: datetime | None = None,
    tz=timezone.utc,
    use_emojis: bool = False,
):
    """
    Send, to a Discord channel, side-by-side calendars for the last N months (1 <= N <= 12) per user.

    Visual rules:
      - Wordle score colors:
          1 -> 🟩, 2 -> 🟦, 3 -> 🟨, 4 -> 🟧, 5 -> 🟥, 6 -> 🟫, X -> 🟪
      - Missed past day -> ⬛
      - Future or overflow (non-month) day -> blank (space)
      When use_emojis=False (recommended for alignment):
        - Use monospaced ASCII tokens: '1','2','3','4','5','6','X'
        - Missed past day -> '·'
        - Future/overflow day -> ' ' (blank)
        A legend with emojis is sent above the grid to preserve the color meaning.
    """
    # Strict clamp of N
    n = max(1, min(12, int(n_months)))

    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    now_dt = end_dt.astimezone(tz) if end_dt else datetime.now(tz)
    today_date = now_dt.date()

    # Helper to back up N months from a given year/month
    def back_months(y: int, m: int, delta: int) -> tuple[int, int]:
        idx = (y * 12 + (m - 1)) - delta
        ny, nm = divmod(idx, 12)
        return ny, nm + 1

    # Build the list of months [M-(n-1), ..., M-1, M]
    end_year, end_month = now_dt.year, now_dt.month
    months: list[tuple[int, int]] = [back_months(end_year, end_month, d) for d in range(n - 1, -1, -1)]

    # Precompute mapping for each month: date -> puzzle/round number
    per_month_day_to_num: list[dict[_date, int]] = []
    per_month_weeks: list[list[list[_date]]] = []  # weeks of dates per month
    for (y, m) in months:
        weeks = cal.monthdatescalendar(y, m)
        per_month_weeks.append(weeks)
        day_to_num: dict[_date, int] = {}
        for week in weeks:
            for d in week:
                if d.month != m:
                    continue
                dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz)
                day_to_num[d] = await date_to_num(dt)
        per_month_day_to_num.append(day_to_num)

    # Build headers once (per calendar month set)
    days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    week_header_block = " ".join(days)
    block_width = len(week_header_block)

    month_titles = []
    for (y, m) in months:
        label = f"{calendar.month_name[m]} {y}"
        month_titles.append(label.center(block_width))
    month_titles_line = "  ".join(month_titles)
    week_headers_line = "  ".join([week_header_block] * n)

    # Legend for color meaning
    legend_line = "Legend: 1=🟩  2=🟦  3=🟨  4=🟧  5=🟥  6=🟫  X=🟪  ·=missed  (blank=future)"

    # Utility: send large text in chunks (Discord 2000-char limit)
    async def _send_in_chunks(prefix: str, body_lines: list[str]):
        content = prefix + "\n" + "\n".join(body_lines)
        wrapped = f"```{content}```"
        if len(wrapped) <= 1900:
            await text_channel.send(wrapped)
            return
        chunk: list[str] = []
        current_len = len(prefix) + 1 + 6
        for line in body_lines:
            line_len = len(line) + 1
            if current_len + line_len > 1900:
                await text_channel.send(f"```{prefix}\n" + "\n".join(chunk) + "```")
                chunk = []
                current_len = len(prefix) + 1 + 6
            chunk.append(line)
            current_len += line_len
        if chunk:
            await text_channel.send(f"```{prefix}\n" + "\n".join(chunk) + "```")

    # Render and send one block per user
    for uid, user in user_dict.items():
        results = getattr(user, "results", []) or []
        number_to_score = _collect_scores_for_numbers(results)  # may contain ints 1..6 or 'X'

        display = getattr(getattr(user, "author", None), "display_name", None) or \
                  getattr(getattr(user, "author", None), "name", None) or str(uid)

        lines: list[str] = []
        # Legend (emoji) is outside the code block for clarity; keep inside to keep chunk logic simple
        # lines.append(legend_line)
        lines.append(month_titles_line)
        lines.append(week_headers_line)

        max_weeks = max(len(w) for w in per_month_weeks)

        for wi in range(max_weeks):
            row_blocks: list[str] = []
            for mi, (y, m) in enumerate(months):
                weeks = per_month_weeks[mi]
                if wi >= len(weeks):
                    row_blocks.append(" " * block_width)
                    continue
                week = weeks[wi]

                # Build cells uniformly
                if use_emojis:
                    # Emoji mode (may misalign on some clients)
                    cells: list[str] = []
                    for d in week:
                        if d.month != m or d > today_date:
                            cells.append("  ")
                            continue
                        num = per_month_day_to_num[mi].get(d)
                        score = number_to_score.get(num)
                        if score is None:
                            cells.append("⬛")
                        else:
                            cells.append(_wordle_score_to_emoji(score))
                    while len(cells) < 7:
                        cells.append("  ")
                    block = " ".join(cells)
                else:
                    # Monospaced ASCII mode for reliable alignment
                    # Each cell is 2 chars: value or '· ' for miss, '  ' for future/overflow
                    cells_ascii: list[str] = []
                    for d in week:
                        if d.month != m:
                            cells_ascii.append("  ")
                            continue
                        if d > today_date:
                            cells_ascii.append("  ")
                            continue
                        num = per_month_day_to_num[mi].get(d)
                        score = number_to_score.get(num)
                        if score is None:
                            cells_ascii.append("· ")
                        else:
                            # Normalize to single-char token: 1..6 or 'X'
                            tok = "X" if (isinstance(score, str) and score.upper() == "X") else str(int(score))
                            # Pad to 2 chars
                            cells_ascii.append(tok.ljust(2))
                    while len(cells_ascii) < 7:
                        cells_ascii.append("  ")
                    block = " ".join(cells_ascii)

                # Ensure block width roughly matches header width
                if len(block) < block_width:
                    block = block + " " * (block_width - len(block))
                row_blocks.append(block)

            lines.append("  ".join(row_blocks))

        prefix = f"{display} — Last {n} Month(s)"
        await _send_in_chunks(prefix, lines)