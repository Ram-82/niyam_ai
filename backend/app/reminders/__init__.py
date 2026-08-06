"""Due-date reminders — cron-driven nudges for approaching GST deadlines.

Public surface: ``sweep_reminders(today)`` computes what needs sending
today, dispatches emails via ``app.email``, and idempotently records
every send in ``reminder_log`` so retries can't double-fire.
"""
from app.reminders.sweep import SweepReport, sweep_reminders

__all__ = ["SweepReport", "sweep_reminders"]
