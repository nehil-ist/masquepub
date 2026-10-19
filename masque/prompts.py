"""The prompt of the day: rotates by UTC day. Set PROMPT_TODAY to replace today's question with your own text (PHP: dayprompt)."""
import os
import time

_PROMPTS = (
    "What is something you never told anyone?",
    "What is a small thing that made you happy this week?",
    "What would you do differently if nobody could ever find out?",
    "What is a belief you held a year ago that you have dropped?",
    "What is the kindest thing a stranger ever did for you?",
    "What do you pretend to like but secretly don't?",
    "What is a memory you return to when you need comfort?",
    "What is something you are proud of that nobody knows about?",
    "What is the best advice you ignored?",
    "What is a fear you have never said out loud?",
    "What would your younger self be surprised to learn about you?",
    "What song do you play when nobody is around?",
    "What is a mistake you are glad you made?",
    "What is something you wish people asked you about?",
    "What is the last thing that made you cry?",
    "What is a habit you are trying to break?",
    "If you could vanish for a week with no consequences, where would you go?",
    "What is the strangest thing you believe in?",
    "What is something you forgave but never forgot?",
    "What is a compliment you still think about?",
    "What is one thing you would change about how you were raised?",
    "What is the most spontaneous thing you have ever done?",
    "Who do you miss, and what would you tell them?",
    "What is a secret talent you have?",
    "What is something you are still learning to accept?",
    "What is the weirdest thing that comforts you?",
    "What is a lie you told that you still think about?",
    "What is the best day you can remember?",
    "What is something you do only when you are alone?",
    "What is a dream you gave up on, and do you miss it?",
    "What is something you wish you could say to your past self?",
    "What is a small rule you live by?",
    "What is the bravest thing you have done?",
    "What is something about you that people get wrong?",
    "What is a place that feels like home to you, and why?",
)


class DailyPrompt:
    @staticmethod
    def for_day(day: int) -> str:
        e = (os.environ.get("PROMPT_TODAY") or "").strip(" \t\n\r\0\x0b")
        if e != "" and day == int(time.time()) // 86400:
            return e[:200]
        return _PROMPTS[day % len(_PROMPTS)]
