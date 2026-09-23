import json
from pathlib import Path
import sys
import tempfile
import unittest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.verse.service import VerseService
from app.verse.providers.base import AIResponse
from app.verse.telemetry import PlatformTelemetry, install_telemetry
from app.verse.analytics import _apply_filters


class RecordingProvider:
    def __init__(self): self.requests = []
    def generate(self, request):
        self.requests.append(request)
        return AIResponse(text=json.dumps({'message': 'There is one running service.', 'summary': 'Service status reviewed.', 'confidence': 'High'}), provider='fake', model='fake')


class PlatformIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snapshot = {'services': [{'apiName': 'orders', 'status': 'RUNNING'}], 'activity': [{'action': '/orders', 'status': 500, 'durationMs': 12, 'requests': 1, 'errors': 1}]}
        self.provider = RecordingProvider()
        self.service = VerseService(verse_root=Path(__file__).resolve().parents[2] / 'verse', data_dir=self.tmp.name,
            provider_config={'AI_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'fake'},
            provider=self.provider, platform_context_loader=lambda username: self.snapshot)

    def test_datasets_exist_without_upload_and_refresh_in_place(self):
        datasets = self.service.list_datasets('alice')
        self.assertEqual(len(datasets), 3)
        dataset = next(row for row in datasets if row['title'] == 'Service status')
        analysis = self.service.analyze_dataset(dataset['id'], 'alice')
        self.assertEqual(analysis['chart']['data'][0]['label'], 'RUNNING')
        self.snapshot['services'] = []
        self.assertEqual(self.service.get_dataset(dataset['id'], 'alice')['rows'], [])
        self.assertIsNone(self.service.get_dataset(dataset['id'], 'bob'))
        self.assertEqual(len(self.service.list_datasets('alice')), 3)

    def test_analytics_filters_keep_false_and_zero_values(self):
        rows = [
            {'enabled': False, 'requests': 0, 'service': 'draft'},
            {'enabled': True, 'requests': 12, 'service': 'running'},
        ]

        self.assertEqual(_apply_filters(rows, [{'column': 'enabled', 'op': 'eq', 'value': 'false'}]), [rows[0]])
        self.assertEqual(_apply_filters(rows, [{'column': 'requests', 'op': 'eq', 'value': 0}]), [rows[0]])
        self.assertEqual(_apply_filters(rows, [{'column': 'requests', 'op': 'lte', 'value': '0'}]), [rows[0]])

    def test_service_performance_dataset_aggregates_volume_errors_and_latency(self):
        self.snapshot['activity'] = [
            {'service': 'orders', 'action': '/orders', 'status': 200, 'durationMs': 10, 'requests': 1, 'errors': 0},
            {'service': 'orders', 'action': '/orders', 'status': 500, 'durationMs': 30, 'requests': 1, 'errors': 1},
            {'service': 'billing', 'action': '/invoices', 'status': 201, 'durationMs': 20, 'requests': 2, 'errors': 0},
        ]
        dataset = next(row for row in self.service.list_datasets('alice') if row['title'] == 'Service performance')

        analysis = self.service.analyze_dataset(dataset['id'], 'alice')
        rows = {row['service']: row for row in analysis['tablePreview']}

        self.assertEqual(rows['orders']['requests'], 2)
        self.assertEqual(rows['orders']['errors'], 1)
        self.assertEqual(rows['orders']['errorRate'], 0.5)
        self.assertEqual(rows['billing']['avgDurationMs'], 20.0)
        self.assertEqual(analysis['chart']['xKey'], 'label')

    def test_live_service_collection_handles_nested_contracts_without_exposing_them(self):
        self.snapshot['services'][0]['lapis_config'] = {'auth': {'privateKey': 'must-not-appear'}, 'models': {'user': {'fields': {}}}}
        dataset = next(row for row in self.service.list_datasets('alice') if row['title'] == 'Service status')

        loaded = self.service.get_dataset(dataset['id'], 'alice')

        self.assertEqual(loaded['rows'][0]['apiName'], 'orders')
        self.assertNotIn('lapis_config', loaded['rows'][0])

    def test_user_started_chat_receives_collected_data_not_truncated_page_note(self):
        self.service.assist('alice', '@Ananse summarize service activity', current_screen='/ananse-workbench')
        blocks = [block for request in self.provider.requests for block in request.context_blocks if block.label == 'Live platform intelligence']
        self.assertTrue(blocks)
        data = json.loads(blocks[0].content)
        self.assertEqual(data[0]['recentRows'][0]['apiName'], 'orders')
        self.assertTrue(data[0]['datasetId'].startswith('platform-'))
        self.assertEqual(data[1]['recentRows'][0]['errors'], 1)

    def test_proactive_ananse_review_receives_same_observations(self):
        self.service.update_user_settings('alice', proactive_mode_enabled=True, agent_settings={
            agent['id']: {'proactivityEnabled': agent['id'] == 'liwiro-analyst', 'proactivityLevel': 6}
            for agent in self.service.list_agents()
        })
        self.service.run_due_proactive_evaluations('alice', force=True)
        blocks = [block for request in self.provider.requests for block in request.context_blocks if block.label == 'Live platform intelligence']
        self.assertTrue(blocks)
        self.assertEqual(json.loads(blocks[0].content)[1]['recentRows'][0]['errors'], 1)

    def test_telemetry_scopes_service_access_and_never_records_request_secrets(self):
        app = Flask(__name__)
        install_telemetry(app, self.tmp.name, session_loader=lambda: {'username': 'alice'})
        app.add_url_rule('/actions/<item>', 'action', lambda item: ('ok', 201), methods=['POST'])
        app.test_client().post('/actions/private-id?token=secret', json={'password': 'hidden'})
        store = PlatformTelemetry(self.tmp.name)
        store.record(username='bob', action='private-action')
        store.record(service='public-orders', action='/orders', status=500)
        store.record(service='restricted', action='do-not-disclose')
        rows = store.rows('alice', ['public-orders'])
        self.assertEqual(len(rows), 2)
        content = json.dumps(rows)
        for secret in ('hidden', 'private-id', 'secret', 'private-action', 'do-not-disclose'):
            self.assertNotIn(secret, content)
        self.assertEqual(rows[-1]['action'], '/actions/<item>')

    def test_ananse_analysis_reports_missing_and_duplicate_data_quality(self):
        created = self.service.create_dataset(
            'alice',
            title='Quality check',
            raw_text='team,value,note\nA,10,\nA,10,\nB,20,reviewed\n',
            filename='quality.csv',
        )

        analysis = self.service.analyze_dataset(created['id'], 'alice', {'chartType': 'table'})

        metrics = analysis['dataset']['analysisSummary']['metrics']
        self.assertEqual(metrics['duplicateRows'], 1)
        self.assertEqual(metrics['completeRows'], 1)
        self.assertGreater(metrics['missingRate'], 0)
        quality = analysis['dataset']['analysisSummary']['quality']['columnQuality']
        self.assertEqual(quality[0]['key'], 'note')
        self.assertTrue(any(finding['title'] == 'Duplicate records detected' for finding in analysis['findings']))
