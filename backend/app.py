"""Orbit demo API. Never deploy publicly with real student data before adding auth."""
import json
import hashlib
import os
import secrets
import time
import base64
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

CATEGORIES = {'school', 'work', 'leadership', 'projects', 'personal'}
PRIORITIES = {'low', 'medium', 'high'}
STATUSES = {'pending', 'completed'}


def response(status, data):
    def serialize_decimal(value):
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            return float(value)
        raise TypeError(f'Object of type {type(value).__name__} is not JSON serializable')

    return {
        'statusCode': status,
        'headers': {'content-type': 'application/json'},
        'body': json.dumps(data, default=serialize_decimal),
    }


def parse_body(event):
    try:
        obj = json.loads(event.get('body') or '{}')
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None


def validate_create(obj):
    if obj is None:
        return 'Request body must be a JSON object'
    title = obj.get('title')
    if not isinstance(title, str) or not (1 <= len(title.strip()) <= 120):
        return 'Title must be 1–120 characters'
    if obj.get('category') not in CATEGORIES:
        return 'Invalid category'
    if obj.get('priority', 'medium') not in PRIORITIES:
        return 'Invalid priority'
    due = obj.get('dueAt')
    if due is None:
        return None
    if not isinstance(due, str):
        return 'dueAt must be ISO 8601 with timezone'
    try:
        parsed = datetime.fromisoformat(due.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return 'dueAt must have a timezone'
    except ValueError:
        return 'Invalid dueAt timestamp'
    return None


def validate_canvas_import(obj):
    if obj is None or not isinstance(obj.get('items'), list):
        return 'items must be a list'
    if not 1 <= len(obj['items']) <= 250:
        return 'Import between 1 and 250 calendar events at a time'
    for event in obj['items']:
        if not isinstance(event, dict):
            return 'Each calendar event must be an object'
        title = event.get('title')
        due = event.get('dueAt')
        source_key = event.get('sourceKey')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            return 'Calendar event titles must be 1–120 characters'
        if not isinstance(source_key, str) or not 1 <= len(source_key) <= 512:
            return 'Each calendar event needs a valid source key'
        if not isinstance(due, str):
            return 'Each calendar event needs a dueAt timestamp'
        try:
            parsed = datetime.fromisoformat(due.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return 'Calendar dueAt timestamps must include a timezone'
        except ValueError:
            return 'Invalid calendar dueAt timestamp'
    return None


def workspace_id_from_code(code):
    return 'workspace-' + hashlib.sha256(code.strip().upper().encode('utf-8')).hexdigest()


def scan_all(table, **kwargs):
    """Read every matching scan page; Limit bounds evaluated rows per request."""
    items = []
    scan_kwargs = dict(kwargs)
    seen_keys = set()
    while True:
        page = table.scan(**scan_kwargs)
        items.extend(page.get('Items', []))
        last_key = page.get('LastEvaluatedKey')
        if not last_key:
            return items
        marker = json.dumps(last_key, sort_keys=True, separators=(',', ':'))
        if marker in seen_keys:
            raise RuntimeError('DynamoDB scan repeated its continuation key')
        seen_keys.add(marker)
        scan_kwargs['ExclusiveStartKey'] = last_key


def encode_cursor(key):
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key, separators=(',', ':')).encode()).decode().rstrip('=')


def decode_cursor(cursor):
    if cursor is None or cursor == '':
        return None
    if not isinstance(cursor, str) or len(cursor) > 2048:
        return None
    try:
        encoded = cursor + '=' * (-len(cursor) % 4)
        raw = base64.b64decode(encoded, altchars=b'-_', validate=True)
        value = json.loads(raw.decode())
        if not isinstance(value, dict) or set(value) != {'id'} or not isinstance(value.get('id'), str) or not value['id']:
            return None
        return value
    except (ValueError, TypeError, UnicodeError):
        return None


def project_for_invite(table, code):
    # New projects get a deterministic key-addressable lookup record. Legacy projects
    # are paginated as a fallback until invite records have been populated on write.
    invite_id = 'invite-' + code
    invite = table.get_item(Key={'id': invite_id}).get('Item')
    if invite and invite.get('recordType') == 'project_invite':
        project = table.get_item(Key={'id': invite.get('projectId', '')}).get('Item')
        if project and project.get('recordType') == 'project' and project.get('inviteCode') == code:
            return project
    projects = scan_all(table, FilterExpression=Attr('recordType').eq('project') & Attr('inviteCode').eq(code))
    return projects[0] if projects else None


def join_project(table, project_id, member, workspace_key, retries=6):
    for attempt in range(retries):
        project = table.get_item(Key={'id': project_id}).get('Item')
        if not project:
            return None, 'missing'
        members = list(project.get('members', []))
        member_ids = list(project.get('memberIds', []))
        version = project.get('membershipVersion', 0)
        if member not in members:
            members.append(member)
        if workspace_key not in member_ids:
            member_ids.append(workspace_key)
        if members == project.get('members', []) and member_ids == project.get('memberIds', []):
            return project, None
        try:
            table.update_item(
                Key={'id': project_id},
                UpdateExpression='SET members = :members, memberIds = :memberIds, membershipVersion = :nextVersion',
                ConditionExpression='membershipVersion = :oldVersion OR attribute_not_exists(membershipVersion)',
                ExpressionAttributeValues={
                    ':members': members, ':memberIds': member_ids,
                    ':oldVersion': version, ':nextVersion': version + 1,
                },
            )
            return {**project, 'members': members, 'memberIds': member_ids, 'membershipVersion': version + 1}, None
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
                raise
            if attempt + 1 < retries:
                time.sleep(0.005 * (2 ** attempt))
    return None, 'conflict'


def create_project(table, project, retries=8):
    """Reserve a unique invite key before writing the project; retry rare collisions."""
    for _ in range(retries):
        code = secrets.token_hex(4).upper()
        # Detect legacy projects which predate the lookup records.
        if project_for_invite(table, code):
            continue
        invite_id = 'invite-' + code
        invite_record = {'id': invite_id, 'recordType': 'project_invite', 'projectId': project['id']}
        try:
            table.put_item(Item=invite_record, ConditionExpression='attribute_not_exists(id)')
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                continue
            raise
        project['inviteCode'] = code
        try:
            table.put_item(Item=project, ConditionExpression='attribute_not_exists(id)')
            return
        except Exception:
            table.delete_item(Key={'id': invite_id}, ConditionExpression='projectId = :projectId', ExpressionAttributeValues={':projectId': project['id']})
            raise
    raise RuntimeError('Unable to reserve a unique project invite code')


def handler(event, context):
    method = (event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod'))
    path = event.get('rawPath') or event.get('path') or ''

    if path == '/api':
        path= '/'
    elif path.startswith('/api/'):
        path = path[4:]

    if method == 'GET' and path == '/health':
        return response(200, {'status': 'ok', 'service': 'orbit'})
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    try:
        obj = parse_body(event)
        headers = {key.lower(): value for key, value in (event.get('headers') or {}).items()}
        access_code = headers.get('x-orbit-access-code', '')
        workspace = None
        if method == 'POST' and path == '/spaces':
            name = obj.get('name') if obj else None
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
                return response(400, {'error': 'Workspace name must be 1–60 characters'})
            access_code = secrets.token_hex(12).upper()
            workspace = {'id': workspace_id_from_code(access_code), 'recordType': 'workspace', 'name': name.strip(), 'createdAt': datetime.now(timezone.utc).isoformat()}
            table.put_item(Item=workspace, ConditionExpression='attribute_not_exists(id)')
            return response(201, {'workspace': {'id': workspace['id'], 'name': workspace['name']}, 'accessCode': access_code})
        if method == 'POST' and path == '/spaces/open':
            code = obj.get('accessCode', '').strip().upper() if obj and isinstance(obj.get('accessCode'), str) else ''
            if not code or len(code) != 24:
                return response(400, {'error': 'Enter a valid 24-character Orbit access code'})
            workspace = table.get_item(Key={'id': workspace_id_from_code(code)}).get('Item')
            if not workspace or workspace.get('recordType') != 'workspace':
                return response(404, {'error': 'No Orbit space found for that code'})
            return response(200, {'workspace': {'id': workspace['id'], 'name': workspace['name']}})
        if not access_code:
            return response(401, {'error': 'Enter your Orbit access code to continue'})
        workspace = table.get_item(Key={'id': workspace_id_from_code(access_code)}).get('Item')
        if not workspace or workspace.get('recordType') != 'workspace':
            return response(401, {'error': 'Orbit access code is invalid. Sign in again.'})
        workspace_key = workspace['id']
        member_projects = []
        project_ids = set()
        if method in ('GET', 'POST') and (path == '/projects' or path == '/items'):
            project_result = scan_all(table, FilterExpression=Attr('recordType').eq('project'))
            member_projects = [project for project in project_result if workspace_key in project.get('memberIds', [])]
            project_ids = {project['id'] for project in member_projects}
        if method == 'GET' and path == '/spaces/me':
            return response(200, {'workspace': {'id': workspace_key, 'name': workspace['name']}})
        if method == 'GET' and path == '/items':
            cursor = (event.get('queryStringParameters') or {}).get('cursor')
            exclusive_start_key = decode_cursor(cursor)
            if cursor and not exclusive_start_key:
                return response(400, {'error': 'Invalid pagination cursor'})
            result = table.scan(Limit=100, **({'ExclusiveStartKey': exclusive_start_key} if exclusive_start_key else {}))
            items = [item for item in result.get('Items', []) if item.get('recordType') not in {'project', 'workspace', 'project_invite'} and (item.get('workspaceId') == workspace_key or item.get('projectId') in project_ids)]
            items.sort(key=lambda x: x.get('dueAt', ''))
            next_cursor = encode_cursor(result.get('LastEvaluatedKey'))
            return response(200, {'items': items, 'nextCursor': next_cursor, 'truncated': bool(next_cursor)})
        if method == 'GET' and path == '/projects':
            projects = member_projects
            projects.sort(key=lambda project: project.get('createdAt', ''))
            return response(200, {'projects': projects})
        if method == 'POST' and path == '/projects':
            obj = parse_body(event)
            name = obj.get('name') if obj else None
            member = obj.get('memberName') if obj else None
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                return response(400, {'error': 'Project name must be 1–80 characters'})
            if not isinstance(member, str) or not 1 <= len(member.strip()) <= 40:
                return response(400, {'error': 'Your name must be 1–40 characters'})
            project = {
                'id': str(uuid4()), 'recordType': 'project', 'name': name.strip(),
                'inviteCode': '', 'members': [member.strip()], 'membershipVersion': 0,
                'memberIds': [workspace_key],
                'createdAt': datetime.now(timezone.utc).isoformat(),
            }
            create_project(table, project)
            return response(201, {'project': project})
        if method == 'POST' and path == '/projects/join':
            obj = parse_body(event)
            code = obj.get('inviteCode', '').strip().upper() if obj and isinstance(obj.get('inviteCode'), str) else ''
            member = obj.get('memberName') if obj else None
            if not code or len(code) != 8:
                return response(400, {'error': 'Enter a valid 8-character invite code'})
            if not isinstance(member, str) or not 1 <= len(member.strip()) <= 40:
                return response(400, {'error': 'Your name must be 1–40 characters'})
            project = project_for_invite(table, code)
            if not project or project.get('recordType') != 'project':
                return response(404, {'error': 'No project found for that invite code'})
            member = member.strip()
            project, join_error = join_project(table, project['id'], member, workspace_key)
            if join_error:
                return response(404 if join_error == 'missing' else 409, {'error': 'Project no longer available' if join_error == 'missing' else 'Project membership changed; please retry'})
            return response(200, {'project': project})
        if method == 'POST' and path == '/items':
            obj = parse_body(event)
            error = validate_create(obj)
            if error:
                return response(400, {'error': error})
            item = {
                'id': str(uuid4()), 'title': obj['title'].strip(),
                'category': obj['category'], 'priority': obj.get('priority', 'medium'),
                'status': 'pending', 'source': 'manual',
                'createdAt': datetime.now(timezone.utc).isoformat()
            }
            if obj.get('dueAt') is not None:
                item['dueAt'] = obj['dueAt']
            if obj.get('projectId'):
                if not isinstance(obj['projectId'], str) or len(obj['projectId']) > 64:
                    return response(400, {'error': 'Invalid project'})
                project = table.get_item(Key={'id': obj['projectId']}).get('Item')
                if not project or project.get('recordType') != 'project' or workspace_key not in project.get('memberIds', []):
                    return response(400, {'error': 'Project not found'})
                item['projectId'] = obj['projectId']
                assignee = obj.get('assignee')
                if assignee:
                    if not isinstance(assignee, str) or len(assignee.strip()) > 40:
                        return response(400, {'error': 'Assignee must be 40 characters or fewer'})
                    item['assignee'] = assignee.strip()
            else:
                item['workspaceId'] = workspace_key
            table.put_item(Item=item)
            return response(201, {'item': item})
        if method == 'POST' and path == '/items/import':
            obj = parse_body(event)
            error = validate_canvas_import(obj)
            if error:
                return response(400, {'error': error})
            imported = 0
            updated = 0
            skipped = 0
            for calendar_event in obj['items']:
                event_id = 'canvas-' + hashlib.sha256(f"{workspace_key}:{calendar_event['sourceKey']}".encode('utf-8')).hexdigest()
                title = calendar_event['title'].strip()
                due_at = calendar_event['dueAt']
                existing = table.get_item(Key={'id': event_id}, ProjectionExpression='id, title, dueAt').get('Item')
                if existing:
                    if existing.get('title') != title or existing.get('dueAt') != due_at:
                        table.update_item(
                            Key={'id': event_id},
                            UpdateExpression='SET #title = :title, dueAt = :due',
                            ExpressionAttributeNames={'#title': 'title'},
                            ExpressionAttributeValues={':title': title, ':due': due_at},
                        )
                        updated += 1
                    else:
                        skipped += 1
                    continue
                table.put_item(Item={
                    'id': event_id,
                    'title': title,
                    'category': 'school',
                    'priority': 'medium',
                    'status': 'pending',
                    'source': 'calendar',
                    'dueAt': due_at,
                    'createdAt': datetime.now(timezone.utc).isoformat(),
                    'workspaceId': workspace_key,
                })
                imported += 1
            return response(200, {'imported': imported, 'updated': updated, 'skipped': skipped})
        if method == 'PATCH' and path.startswith('/items/'):
            item_id = (event.get('pathParameters') or {}).get('id') or path.rsplit('/', 1)[-1]
            obj = parse_body(event)
            if not obj:
                return response(400, {'error': 'Request body must be a JSON object'})
            existing_item = table.get_item(Key={'id': item_id}).get('Item')
            if not existing_item:
                return response(404, {'error': 'Item not found'})
            if existing_item.get('projectId'):
                existing_project = table.get_item(Key={'id': existing_item['projectId']}).get('Item')
                if not existing_project or workspace_key not in existing_project.get('memberIds', []):
                    return response(404, {'error': 'Item not found'})
            elif existing_item.get('workspaceId') != workspace_key:
                return response(404, {'error': 'Item not found'})
            set_updates = []
            remove_updates = []
            names = {}
            values = {}
            if 'status' in obj:
                if obj['status'] not in STATUSES:
                    return response(400, {'error': 'status must be pending or completed'})
                set_updates.append('#s = :status')
                names['#s'] = 'status'
                values[':status'] = obj['status']
            if 'assignee' in obj:
                assignee = obj['assignee']
                if not isinstance(assignee, str) or len(assignee.strip()) > 40:
                    return response(400, {'error': 'Assignee must be 40 characters or fewer'})
                if assignee.strip():
                    set_updates.append('assignee = :assignee')
                    values[':assignee'] = assignee.strip()
                else:
                    remove_updates.append('assignee')
            if 'title' in obj:
                title = obj['title']
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
                    return response(400, {'error': 'Title must be 1–120 characters'})
                set_updates.append('#title = :title')
                names['#title'] = 'title'
                values[':title'] = title.strip()
            if 'description' in obj:
                description = obj['description']
                if not isinstance(description, str) or len(description) > 2000:
                    return response(400, {'error': 'Details must be 2000 characters or fewer'})
                if description.strip():
                    set_updates.append('#description = :description')
                    names['#description'] = 'description'
                    values[':description'] = description.strip()
                else:
                    remove_updates.append('description')
            if 'dueAt' in obj:
                due_at = obj['dueAt']
                if due_at == '':
                    remove_updates.append('dueAt')
                elif not isinstance(due_at, str):
                    return response(400, {'error': 'dueAt must be ISO 8601 with timezone'})
                else:
                    try:
                        parsed = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
                        if parsed.tzinfo is None:
                            return response(400, {'error': 'dueAt must include a timezone'})
                    except ValueError:
                        return response(400, {'error': 'Invalid dueAt timestamp'})
                    set_updates.append('dueAt = :dueAt')
                    values[':dueAt'] = due_at
            if not set_updates and not remove_updates:
                return response(400, {'error': 'Provide a valid status or assignee'})
            expression = ('SET ' + ', '.join(set_updates) if set_updates else '')
            if remove_updates:
                expression += (' ' if expression else '') + 'REMOVE ' + ', '.join(remove_updates)
            result = table.update_item(
                Key={'id': item_id},
                UpdateExpression=expression,
                ConditionExpression='attribute_exists(id)',
                **({'ExpressionAttributeNames': names} if names else {}),
                **({'ExpressionAttributeValues': values} if values else {}),
                ReturnValues='ALL_NEW'
            )
            return response(200, {'item': result['Attributes']})
        return response(404, {'error': 'Route not found'})
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return response(404, {'error': 'Item not found'})
        print('AWS operation failed:', exc.response.get('Error', {}).get('Code', 'Unknown'))
        return response(500, {'error': 'Internal server error'})
