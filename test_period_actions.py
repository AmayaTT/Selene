import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import cycle
import db
import period_actions as actions
import selene_rest
import selene_rest_deploy


class PeriodActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, 'DB_PATH', str(Path(self.temp.name) / 'test.db'))
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def apply(self, action, value, token, ident=None):
        return actions.apply(action, value, token, ident, today=date(2026, 9, 19))

    def test_status_boundaries(self):
        self.assertEqual(cycle.describe_status([], date(2026, 9, 11))['state'], 'pending')
        periods = [{'start_date': '2026-08-21', 'end_date': '2026-08-26'}]
        for day in (21, 26):
            status = cycle.describe_status(periods, date(2026, 8, day), 28)
            self.assertEqual(status['state'], 'menstrual')
            self.assertFalse(status['phase_is_estimated'])
        self.assertEqual(cycle.describe_status(periods, date(2026, 9, 11), 28)['state'], 'ended')
        self.assertEqual(cycle.current_phase(periods, date(2026, 9, 11), 28)['phase'], 'luteal')
        for day, state, overdue in ((18, 'due', 0), (19, 'overdue', 1)):
            status = cycle.describe_status(periods, date(2026, 9, day), 28)
            self.assertEqual((status['state'], status['overdue_days']), (state, overdue))
        periods[0]['end_date'] = ''
        self.assertEqual(cycle.describe_status(periods, date(2026, 8, 22), 28)['state'], 'started')

    def test_duplicates_and_undo_restore(self):
        self.apply('start', '2026-08-21', 'start')
        ident = db.get_periods()[0]['id']
        self.apply('end', '2026-08-26', 'end', ident)
        self.assertTrue(self.apply('end', '2026-08-26', 'end', ident)['duplicate'])
        self.assertFalse(self.apply('start', '2026-08-21', 'same-date')['changed'])
        self.assertEqual(db.get_periods()[0]['end_date'], '2026-08-26')
        self.assertEqual(len(db.get_periods()), 1)
        actions.undo('end')
        self.assertEqual(db.get_periods()[0]['end_date'], '')
        self.assertEqual(actions.latest_undo()['request_id'], 'start')
        actions.undo('start')
        self.assertEqual(db.get_periods(), [])
        self.assertFalse(actions.undo('start')['changed'])
        self.assertTrue(self.apply('start', '2026-08-21', 'start')['undone'])
        self.assertEqual(db.get_periods(), [])

    def test_undo_preserves_metadata_and_rejects_later_edit(self):
        ident = db.add_period('2026-08-21', '2026-08-25', pain=3, note='keep')
        self.apply('end', '2026-08-26', 'end', ident)
        actions.undo('end')
        row = db.get_period_by_id(ident)
        self.assertEqual((row['end_date'], row['pain'], row['note']), ('2026-08-25', 3, 'keep'))
        self.apply('end', '2026-08-26', 'again', ident)
        db.update_period(ident, end_date='2026-08-27')
        with self.assertRaises(actions.ActionConflict):
            actions.undo('again')
        self.assertEqual(db.get_period_by_id(ident)['end_date'], '2026-08-27')
        self.assertIsNone(actions.latest_undo())

    def test_validation_is_atomic(self):
        ident = db.add_period('2026-08-21', '2026-08-26')
        db.add_period('2026-09-18')
        before = db.get_periods()
        for action, value, target in [('start', '', None), ('start', '2026-09-20', None),
                                      ('start', '2026-08-22', None), ('end', '2026-08-20', ident),
                                      ('end', '2026-09-18', ident), ('end', '2026-08-26', 999)]:
            with self.assertRaises(ValueError):
                self.apply(action, value, value or 'empty', target)
            self.assertEqual(db.get_periods(), before)

    def test_both_rest_entry_points(self):
        for module in (selene_rest, selene_rest_deploy):
            client = TestClient(module.app)
            response = client.post('/period/action', json={'action': 'start', 'date': '2026-08-21', 'request_id': module.__name__})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body['periodId'])
            self.assertIn('phase_label', body['status'])
            response = client.post('/period/undo', json={'request_id': module.__name__})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status']['state'], 'pending')
            self.assertEqual(client.post('/period/undo', json={'request_id': 'missing'}).status_code, 409)
        paths = {route.path for route in selene_rest_deploy.app.routes}
        self.assertTrue({'/', '/selene_browser.js', '/period/action', '/period/undo'} <= paths)


if __name__ == '__main__':
    unittest.main()
