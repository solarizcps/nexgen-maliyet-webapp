# -*- coding: utf-8 -*-
"""Injectable clock for weekly review tests (Europe/Istanbul)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config

IST = ZoneInfo(config.TIMEZONE)


class RealClock:
    def now_utc(self):
        return datetime.now(timezone.utc)

    def now_local(self):
        return self.now_utc().astimezone(IST)


class FixedClock:
    def __init__(self, utc_dt):
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        self._utc = utc_dt

    def now_utc(self):
        return self._utc

    def now_local(self):
        return self._utc.astimezone(IST)


def get_clock(app=None):
    if app is not None:
        return app.config.get("CLOCK") or RealClock()
    try:
        from flask import current_app

        return current_app.config.get("CLOCK") or RealClock()
    except RuntimeError:
        return RealClock()
