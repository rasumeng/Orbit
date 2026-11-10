"""Exercise the inline CloudFormation frontend custom resource with fake S3."""
import io
import sys
import textwrap
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


def custom_resource_source():
    template = (Path(__file__).resolve().parents[1] / 'orbit-stack.yaml').read_text(encoding='utf-8')
    marker = '        ZipFile: |\n'
    start = template.index(marker) + len(marker)
    end = template.index('\n\n  FrontendContent:', start)
    return textwrap.dedent(template[start:end])


class FakeS3:
    def __init__(self, archive, fail_key=None):
        self.archive = archive
        self.fail_key = fail_key
        self.objects = {'index.html': b'old root', 'releases/old/assets/app.js': b'old asset'}
        self.put_order = []

    def get_object(self, Bucket, Key):
        return {'Body': io.BytesIO(self.archive), 'ContentLength': len(self.archive)}

    def put_object(self, Bucket, Key, Body, **kwargs):
        if Key == self.fail_key:
            raise RuntimeError('simulated S3 write failure')
        self.put_order.append(Key)
        self.objects[Key] = Body

    def get_paginator(self, operation):
        return self

    def paginate(self, Bucket, Prefix=None):
        keys = sorted(key for key in self.objects if Prefix is None or key.startswith(Prefix))
        yield {'Contents': [{'Key': key} for key in keys]}

    def delete_objects(self, Bucket, Delete):
        for entry in Delete['Objects']:
            self.objects.pop(entry['Key'], None)
        return {'Deleted': Delete['Objects']}


def frontend_zip(version='v1', unsafe=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('assets/a.js', b'a')
        archive.writestr('assets/b.js', b'b')
        archive.writestr('index.html', f'<script src="/releases/{version}/assets/a.js"></script>')
        if unsafe:
            archive.writestr('../escape', b'bad')
    return output.getvalue()


class InlineDeployerTests(unittest.TestCase):
    def setUp(self):
        self.responses = []
        self.s3 = FakeS3(frontend_zip())
        boto3 = types.ModuleType('boto3')
        boto3.client = lambda _: self.s3
        cfnresponse = types.ModuleType('cfnresponse')
        cfnresponse.SUCCESS = 'SUCCESS'
        cfnresponse.FAILED = 'FAILED'
        cfnresponse.send = lambda event, context, status, data, physical_id: self.responses.append((status, data, physical_id))
        self.modules = patch.dict(sys.modules, {'boto3': boto3, 'cfnresponse': cfnresponse})
        self.modules.start()
        self.namespace = {}
        exec(compile(custom_resource_source(), 'orbit-stack.yaml:FrontendDeployer', 'exec'), self.namespace)

    def tearDown(self):
        self.modules.stop()

    def event(self, request_type, version='v1'):
        return {
            'RequestType': request_type,
            'ResourceProperties': {
                'DestinationBucket': 'frontend-dest',
                'ArtifactBucket': 'artifacts',
                'FrontendZipKey': f'releases/{version}/orbit-frontend.zip',
                'ArtifactVersion': version,
            },
        }

    def test_create_uploads_assets_before_switching_root_index(self):
        self.namespace['handler'](self.event('Create'), None)
        self.assertEqual(self.responses[-1][0], 'SUCCESS')
        self.assertEqual(self.s3.put_order, ['releases/v1/assets/a.js', 'releases/v1/assets/b.js', 'index.html'])
        self.assertIn('releases/v1/assets/a.js', self.s3.objects)

    def test_failed_update_removes_partial_new_assets_and_keeps_live_site(self):
        self.s3.archive = frontend_zip('v2')
        self.s3.fail_key = 'releases/v2/assets/b.js'
        self.namespace['handler'](self.event('Update', 'v2'), None)
        self.assertEqual(self.responses[-1][0], 'FAILED')
        self.assertEqual(self.s3.objects['index.html'], b'old root')
        self.assertEqual(self.s3.objects['releases/old/assets/app.js'], b'old asset')
        self.assertFalse(any(key.startswith('releases/v2/') for key in self.s3.objects))

    def test_index_publish_failure_keeps_old_root_and_cleans_new_assets(self):
        self.s3.archive = frontend_zip('v2')
        self.s3.fail_key = 'index.html'
        self.namespace['handler'](self.event('Update', 'v2'), None)
        self.assertEqual(self.responses[-1][0], 'FAILED')
        self.assertEqual(self.s3.objects['index.html'], b'old root')
        self.assertEqual(self.s3.objects['releases/old/assets/app.js'], b'old asset')
        self.assertFalse(any(key.startswith('releases/v2/') for key in self.s3.objects))

    def test_invalid_archive_fails_before_any_destination_write(self):
        self.s3.archive = frontend_zip(unsafe=True)
        self.namespace['handler'](self.event('Create'), None)
        self.assertEqual(self.responses[-1][0], 'FAILED')
        self.assertEqual(self.s3.put_order, [])
        self.assertEqual(self.s3.objects['index.html'], b'old root')

    def test_delete_empties_only_the_stack_owned_frontend_bucket(self):
        self.namespace['handler'](self.event('Delete'), None)
        self.assertEqual(self.responses[-1][0], 'SUCCESS')
        self.assertEqual(self.s3.objects, {})


if __name__ == '__main__':
    unittest.main()
