"""Offline reliability tests; all DynamoDB operations are served by an in-memory fake."""
import json
import threading
import unittest
from decimal import Decimal
from unittest.mock import patch

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

import app


class FakeTable:
    def __init__(self, records=(), page_size=100, forced_conflicts=0):
        self.records = {record['id']: dict(record) for record in records}
        self.page_size = page_size
        self.lock = threading.Lock()
        self.forced_conflicts = forced_conflicts
        self.initial_read_barrier = None
        self.initial_project_reads = 0

    def get_item(self, Key, **kwargs):
        with self.lock:
            result = {'Item': dict(self.records[Key['id']])} if Key['id'] in self.records else {}
            wait_at_barrier = Key['id'] == 'p' and self.initial_read_barrier is not None and self.initial_project_reads < 2
            if wait_at_barrier:
                self.initial_project_reads += 1
                barrier = self.initial_read_barrier
            else:
                barrier = None
        if barrier:
            barrier.wait(timeout=2)
        return result

    def put_item(self, Item, **kwargs):
        with self.lock:
            if kwargs.get('ConditionExpression') and Item['id'] in self.records:
                raise conditional_failure()
            self.records[Item['id']] = dict(Item)

    def scan(self, **kwargs):
        rows = list(self.records.values())
        start = kwargs.get('ExclusiveStartKey', {}).get('id')
        if start:
            ids = [row['id'] for row in rows]
            rows = rows[ids.index(start) + 1:]
        limit = min(kwargs.get('Limit', self.page_size), self.page_size)
        evaluated, remaining = rows[:limit], rows[limit:]
        filt = kwargs.get('FilterExpression')
        page = [row for row in evaluated if filt is None or matches(filt, row)]
        result = {'Items': [dict(row) for row in page]}
        if remaining and evaluated:
            result['LastEvaluatedKey'] = {'id': evaluated[-1]['id']}
        return result

    def update_item(self, Key, **kwargs):
        with self.lock:
            row = self.records[Key['id']]
            values = kwargs['ExpressionAttributeValues']
            if self.forced_conflicts:
                self.forced_conflicts -= 1
                raise conditional_failure()
            if row.get('membershipVersion', 0) != values[':oldVersion']:
                raise conditional_failure()
            row['members'] = list(values[':members'])
            row['memberIds'] = list(values[':memberIds'])
            row['membershipVersion'] = values[':nextVersion']
            return {'Attributes': dict(row)}

    def delete_item(self, Key, **kwargs):
        with self.lock:
            row = self.records.get(Key['id'])
            values = kwargs.get('ExpressionAttributeValues', {})
            if row and (not values or row.get('projectId') == values.get(':projectId')):
                self.records.pop(Key['id'])


def conditional_failure():
    return ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'UpdateItem')


def matches(expression, row):
    # The fake only needs the Attr equality conditions used by these tests.
    operation = type(expression).__name__
    if operation == 'And':
        return all(matches(child, row) for child in expression._values)
    attribute, value = expression._values
    return row.get(attribute.name) == value


def invoke(table, method, path, code, body=None, query=None):
    event = {'httpMethod': method, 'path': path, 'headers': {'x-orbit-access-code': code},
             'body': json.dumps(body) if body is not None else None,
             'queryStringParameters': query or {}}
    with patch.object(app.boto3, 'resource', return_value=type('Resource', (), {'Table': lambda self, _: table})()), \
         patch.dict(app.os.environ, {'TABLE_NAME': 'test'}):
        result = app.handler(event, None)
    return result['statusCode'], json.loads(result['body'])


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.code_a, self.code_b = 'A' * 24, 'B' * 24
        self.workspace_a, self.workspace_b = app.workspace_id_from_code(self.code_a), app.workspace_id_from_code(self.code_b)
        self.base = [
            {'id': self.workspace_a, 'recordType': 'workspace', 'name': 'A'},
            {'id': self.workspace_b, 'recordType': 'workspace', 'name': 'B'},
        ]

    def test_response_serializes_nested_decimal_values(self):
        result = app.response(200, {
            'whole': Decimal('7.000'),
            'nested': [{'fractional': Decimal('2.75'), 'whole': Decimal('-3')}],
        })
        self.assertEqual(json.loads(result['body']), {
            'whole': 7,
            'nested': [{'fractional': 2.75, 'whole': -3}],
        })

    def test_projects_listing_serializes_decimal_membership_version(self):
        project = {
            'id': 'p', 'recordType': 'project', 'workspaceId': self.workspace_a,
            'name': 'Team', 'members': ['Alice'], 'memberIds': [self.workspace_a],
            'membershipVersion': Decimal('4'),
        }
        table = FakeTable(self.base + [project])
        status, result = invoke(table, 'GET', '/projects', self.code_a)
        self.assertEqual(status, 200)
        self.assertEqual(result['projects'][0]['membershipVersion'], 4)
        self.assertIsInstance(result['projects'][0]['membershipVersion'], int)

    def test_items_paginate_beyond_100_and_isolate_workspaces(self):
        rows = self.base + [{'id': f'a-{i:03}', 'workspaceId': self.workspace_a, 'title': 'A'} for i in range(120)]
        rows += [{'id': f'b-{i:03}', 'workspaceId': self.workspace_b, 'title': 'B'} for i in range(130)]
        table = FakeTable(rows, page_size=17)
        seen, cursor = [], None
        while True:
            status, data = invoke(table, 'GET', '/items', self.code_a, query={'cursor': cursor} if cursor else None)
            self.assertEqual(status, 200)
            seen.extend(data['items'])
            cursor = data['nextCursor']
            if not cursor:
                break
        self.assertEqual(len(seen), 120)
        self.assertTrue(all(item['workspaceId'] == self.workspace_a for item in seen))
        self.assertFalse(data['truncated'])

    def test_invite_lookup_finds_project_after_many_records(self):
        project = {'id': 'target', 'recordType': 'project', 'inviteCode': 'A1B2C3D4', 'members': [], 'memberIds': []}
        rows = self.base + [{'id': f'old-{i:03}', 'recordType': 'project', 'inviteCode': f'{i:08}', 'members': [], 'memberIds': []} for i in range(160)] + [project]
        table = FakeTable(rows, page_size=11)
        self.assertEqual(app.project_for_invite(table, 'A1B2C3D4')['id'], 'target')

    def test_legacy_invitation_lookup_scans_all_pages(self):
        target = {'id': 'legacy-target', 'recordType': 'project', 'inviteCode': 'A1B2C3D4', 'members': [], 'memberIds': []}
        table = FakeTable(self.base + [{'id': f'x-{i}', 'recordType': 'workspace'} for i in range(30)] + [target], page_size=3)
        self.assertEqual(app.project_for_invite(table, 'A1B2C3D4')['id'], 'legacy-target')

    def test_scan_all_continues_after_empty_filtered_page_and_detects_repeated_key(self):
        rows = [{'id': f'w-{i}', 'recordType': 'workspace'} for i in range(5)] + [{'id': 'project', 'recordType': 'project'}]
        table = FakeTable(rows, page_size=2)
        self.assertEqual([row['id'] for row in app.scan_all(table, FilterExpression=Attr('recordType').eq('project'))], ['project'])

        class RepeatingTable:
            def scan(self, **kwargs):
                return {'Items': [], 'LastEvaluatedKey': {'id': 'same'}}
        with self.assertRaisesRegex(RuntimeError, 'repeated'):
            app.scan_all(RepeatingTable())

    def test_concurrent_membership_joins_preserve_both_workspaces(self):
        table = FakeTable([{'id': 'p', 'recordType': 'project', 'members': [], 'memberIds': []}])
        table.initial_read_barrier = threading.Barrier(2)
        outcomes = []
        def join(name, workspace):
            outcomes.append(app.join_project(table, 'p', name, workspace))
        threads = [threading.Thread(target=join, args=('Alice', self.workspace_a)),
                   threading.Thread(target=join, args=('Bob', self.workspace_b))]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        project = table.records['p']
        self.assertCountEqual(project['members'], ['Alice', 'Bob'])
        self.assertCountEqual(project['memberIds'], [self.workspace_a, self.workspace_b])
        self.assertEqual(project['membershipVersion'], 2)
        self.assertTrue(all(error is None for _, error in outcomes))

    def test_join_initializes_legacy_membership_lists(self):
        table = FakeTable([{'id': 'legacy-project', 'recordType': 'project'}])
        project, error = app.join_project(table, 'legacy-project', 'New member', self.workspace_a)
        self.assertIsNone(error)
        self.assertEqual(project['members'], ['New member'])
        self.assertEqual(project['memberIds'], [self.workspace_a])
        self.assertEqual(project['membershipVersion'], 1)

    def test_join_returns_conflict_after_retry_exhaustion(self):
        table = FakeTable(self.base + [{'id': 'p', 'recordType': 'project', 'inviteCode': 'A1B2C3D4', 'members': [], 'memberIds': [], 'membershipVersion': 0}], forced_conflicts=6)
        with patch.object(app.time, 'sleep') as sleep:
            status, result = invoke(table, 'POST', '/projects/join', self.code_a, {'inviteCode': 'A1B2C3D4', 'memberName': 'Alice'})
        self.assertEqual(status, 409)
        self.assertIn('retry', result['error'])
        self.assertEqual(sleep.call_count, 5)

    def test_calendar_import_is_idempotent(self):
        table = FakeTable(self.base)
        payload = {'items': [{'title': 'Exam', 'dueAt': '2026-12-01T10:00:00Z', 'sourceKey': 'uid-1'}]}
        self.assertEqual(invoke(table, 'POST', '/items/import', self.code_a, payload)[1], {'imported': 1, 'updated': 0, 'skipped': 0})
        self.assertEqual(invoke(table, 'POST', '/items/import', self.code_a, payload)[1], {'imported': 0, 'updated': 0, 'skipped': 1})
        self.assertEqual(len([r for r in table.records.values() if r.get('source') == 'calendar']), 1)

    def test_workspace_creation_does_not_claim_legacy_rows(self):
        legacy = {'id': 'legacy-task', 'title': 'Unscoped'}
        table = FakeTable([legacy])
        status, result = invoke(table, 'POST', '/spaces', '', {'name': 'New space'})
        self.assertEqual(status, 201)
        self.assertEqual(table.records['legacy-task'], legacy)
        self.assertEqual(table.records[result['workspace']['id']]['recordType'], 'workspace')

    def test_workspace_creation_keeps_existing_workspace_access_valid(self):
        table = FakeTable(self.base)
        status, result = invoke(table, 'POST', '/spaces', '', {'name': 'New space'})
        self.assertEqual(status, 201)
        self.assertIn(self.workspace_a, table.records)
        opened, space = invoke(table, 'POST', '/spaces/open', '', {'accessCode': self.code_a})
        self.assertEqual(opened, 200)
        self.assertEqual(space['workspace']['id'], self.workspace_a)
        self.assertEqual(result['workspace']['id'], app.workspace_id_from_code(result['accessCode']))

    def test_invalid_cursor_and_calendar_validation_errors(self):
        table = FakeTable(self.base)
        for cursor in ('%%%', 'eyJpZCI6Im9rIiwieCI6MX0', 'eyJpZCI6IiJ9', 'A' * 3000):
            self.assertEqual(invoke(table, 'GET', '/items', self.code_a, query={'cursor': cursor})[0], 400)
        status, result = invoke(table, 'POST', '/items/import', self.code_a, {'items': []})
        self.assertEqual(status, 400)
        self.assertIn('error', result)

    def test_new_invite_record_is_key_addressable(self):
        code = 'A' * 24
        table = FakeTable(self.base)
        status, result = invoke(table, 'POST', '/projects', code, {'name': 'Team', 'memberName': 'Alice'})
        self.assertEqual(status, 201)
        project = result['project']
        invite = table.records['invite-' + project['inviteCode']]
        self.assertEqual(invite['projectId'], project['id'])
        self.assertEqual(invoke(table, 'POST', '/projects/join', self.code_b, {'inviteCode': project['inviteCode'], 'memberName': 'Bob'})[0], 200)

    def test_invite_metadata_never_appears_in_tasks_or_projects(self):
        invite = {'id': 'invite-A1B2C3D4', 'recordType': 'project_invite', 'projectId': 'p', 'workspaceId': self.workspace_a}
        project = {'id': 'p', 'recordType': 'project', 'inviteCode': 'A1B2C3D4', 'members': [], 'memberIds': [self.workspace_a]}
        table = FakeTable(self.base + [invite, project], page_size=2)
        status, items = invoke(table, 'GET', '/items', self.code_a)
        self.assertEqual(status, 200)
        self.assertEqual(items['items'], [])
        status, projects = invoke(table, 'GET', '/projects', self.code_a)
        self.assertEqual(status, 200)
        self.assertEqual([p['id'] for p in projects['projects']], ['p'])

    def test_invite_id_collision_retries_without_overwriting_existing_row(self):
        existing = {'id': 'invite-AAAAAAAA', 'recordType': 'manual', 'title': 'Keep me'}
        table = FakeTable(self.base + [existing])
        with patch.object(app.secrets, 'token_hex', side_effect=['aaaaaaaa', 'bbbbbbbb']):
            status, result = invoke(table, 'POST', '/projects', self.code_a, {'name': 'Team', 'memberName': 'Alice'})
        self.assertEqual(status, 201)
        self.assertEqual(table.records['invite-AAAAAAAA'], existing)
        self.assertEqual(result['project']['inviteCode'], 'BBBBBBBB')


if __name__ == '__main__':
    unittest.main()
