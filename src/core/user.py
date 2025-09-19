#!/usr/bin/python

from .dates import date_to_num
from .models import Result
import logging

logger = logging.getLogger(__name__)

class User:
    def __init__(self, author):
        self.author = author
        self.results: [Result] = []
        self.played_nums: [int] = []
        self.last_played: int | None = None
        self.cur_streak = 0
        self.total_games = 0
        self.streaks = []

    async def add_result(self, result: Result):

        today_num = await date_to_num()
        if result.number > today_num:
            print(f"Invalid game number: {result.number}. Newest number is {today_num}. This might be due to a time zone related error.")
            return

        if result.number not in self.played_nums:
            self.results.append(result)
            self.results.sort(key=lambda x: x.number)
            logger.debug("User.add_result: user_id=%s added number=%s score=%s (total_results=%s)",
                         getattr(self.author, "id", None), result.number, getattr(result, "score", None), len(self.results))

            # If result was from today, update streak
            if result.number == today_num:
                # Generic win rule: any numeric score counts as a win
                score = getattr(result, "score", None)
                if isinstance(score, int):
                    self.cur_streak += 1
                else:
                    self.cur_streak = 0

            # Update played numbers and last played
            self.total_games += 1
            self.played_nums.append(result.number)
            if not self.last_played or result.number > self.last_played:
                self.last_played = result.number
        else:
            logger.debug("User.add_result: duplicate ignored for user_id=%s number=%s",
                         getattr(self.author, "id", None), result.number)

    def get_last_result(self):
        if not self.results:
            return None
        return self.results[len(self.results)-1]
