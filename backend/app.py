"""Orbit demo API. Never deploy publicly with real student data before adding auth."""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError

CATEGORIES = {'school', 'work', 'leadership', 'projects', 'personal'}
PRIORITIES = {'low', 'medium', 'high'}
STATUSES = {'pending', 'completed'}


def response(status, data):
    return {'statusCode': status, 'headers': {'content-type': 'application/json'}, 'body': json.dumps(data)}


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


def handler(event, context):
    method = (event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod'))
    path = event.get('rawPath') or event.get('path') or ''
    if method == 'GET' and path == '/health':
        return response(200, {'status': 'ok', 'service': 'orbit'})
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    try:
        if method == 'GET' and path == '/items':
            # Scan is appropriate only for the small, shared midpoint demonstration dataset.
            result = table.scan(Limit=100)
            items = result.get('Items', [])
            items.sort(key=lambda x: x.get('dueAt', ''))
            return response(200, {'items': items, 'truncated': bool(result.get('LastEvaluatedKey'))})
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
            table.put_item(Item=item)
            return response(201, {'item': item})
        if method == 'PATCH' and path.startswith('/items/'):
            item_id = (event.get('pathParameters') or {}).get('id') or path.rsplit('/', 1)[-1]
            obj = parse_body(event)
            if not obj or obj.get('status') not in STATUSES:
                return response(400, {'error': 'status must be pending or completed'})
            result = table.update_item(
                Key={'id': item_id},
                UpdateExpression='SET #s = :status',
                ConditionExpression='attribute_exists(id)',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':status': obj['status']},
                ReturnValues='ALL_NEW'
            )
            return response(200, {'item': result['Attributes']})
        return response(404, {'error': 'Route not found'})
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return response(404, {'error': 'Item not found'})
        print('AWS operation failed:', exc.response.get('Error', {}).get('Code', 'Unknown'))
        return response(500, {'error': 'Internal server error'})
