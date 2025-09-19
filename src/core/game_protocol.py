# src/core/game_protocol.py
from __future__ import annotations

from typing import Protocol, List, Dict, Any, runtime_checkable
import discord

@runtime_checkable
class Game(Protocol):
    async def parse_message(self, msg) -> List[Dict[str, Any]]:
        """
        Parse a Discord message and return a list of results in the format:
          {
            "member_id": int,
            "score": int | 'X',
            "number": int,               # puzzle number
            "timestamp": datetime,       # optional, defaults to msg.created_at
            "meta": Dict[str, Any]       # optional additional data
          }
        Return an empty list if the message doesn't contain any game results.
        """
        ...

    async def build_stats_embed(self, user_dict, bot, helpers) -> discord.Embed:
        """
        Build and return a Discord embed for the current stats.
        helpers provides reusable functions such as:
          - longest_all_time_streak(user)
          - qualifying_try_values(user)
          - total_games_played(user)
          - total_x(user)
          - total_ones(user)
        """
        ...