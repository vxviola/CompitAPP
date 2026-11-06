"""Reminder times must follow Rome even when the container clock uses UTC."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))
import scheduler


class ReminderTimezoneTest(unittest.TestCase):
    def trigger(self, configured_time):
        sched = BackgroundScheduler(timezone='Europe/Rome')
        with patch.object(scheduler, 'BackgroundScheduler', return_value=sched), \
             patch.object(sched, 'start'), \
             patch.object(scheduler, 'sync_tutto'), \
             patch.object(scheduler, '_scheduler', None), \
             patch.object(scheduler, 'ORARIO_REMINDER', configured_time), \
             patch('apscheduler.triggers.cron.get_localzone', return_value=pytz.UTC):
            scheduler.avvia_scheduler()
        return sched.get_job('reminder_sera').trigger

    def assert_daily(self, trigger, start, expected):
        previous = None
        now = datetime.fromisoformat(start)
        actual = []
        for _ in expected:
            fire = trigger.get_next_fire_time(previous, now)
            actual.append((fire.astimezone(pytz.timezone('Europe/Rome')).isoformat(),
                           fire.astimezone(timezone.utc).isoformat()))
            previous, now = fire, fire + timedelta(seconds=1)
        self.assertEqual(actual, expected)

    def test_default_evening_is_rome_when_host_is_utc(self):
        self.assert_daily(self.trigger('20:00'), '2026-11-06T00:00:00+00:00', [
            ('2026-11-06T20:00:00+01:00', '2026-11-06T19:00:00+00:00')])

    def test_configured_time_in_summer(self):
        self.assert_daily(self.trigger('07:15'), '2026-07-01T00:00:00+00:00', [
            ('2026-07-01T07:15:00+02:00', '2026-07-01T05:15:00+00:00')])

    def test_spring_transition_keeps_local_evening_once_per_day(self):
        self.assert_daily(self.trigger('20:00'), '2026-03-28T00:00:00+00:00', [
            ('2026-03-28T20:00:00+01:00', '2026-03-28T19:00:00+00:00'),
            ('2026-03-29T20:00:00+02:00', '2026-03-29T18:00:00+00:00'),
            ('2026-03-30T20:00:00+02:00', '2026-03-30T18:00:00+00:00')])

    def test_autumn_transition_keeps_local_evening_once_per_day(self):
        self.assert_daily(self.trigger('20:00'), '2026-10-24T00:00:00+00:00', [
            ('2026-10-24T20:00:00+02:00', '2026-10-24T18:00:00+00:00'),
            ('2026-10-25T20:00:00+01:00', '2026-10-25T19:00:00+00:00'),
            ('2026-10-26T20:00:00+01:00', '2026-10-26T19:00:00+00:00')])

    def test_invalid_configuration_falls_back_to_20_rome(self):
        for value in ('invalid', '25:00'):
            with self.subTest(value=value):
                self.assert_daily(self.trigger(value), '2026-07-01T00:00:00+00:00', [
                    ('2026-07-01T20:00:00+02:00', '2026-07-01T18:00:00+00:00')])


if __name__ == '__main__':
    unittest.main()
