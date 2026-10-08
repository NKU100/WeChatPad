import json
import subprocess
import tempfile
import unittest
import io
from pathlib import Path

from scripts.ci.codex_trace import EncryptedTrace
from scripts.ci.codex_goal import AppServer


class EncryptedTraceTest(unittest.TestCase):
    def test_app_server_records_requests_and_successful_tool_events(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            key = directory / 'identity'
            subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
            recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
            client = AppServer.__new__(AppServer)
            client.trace = EncryptedTrace(directory, recipient)
            event = {'method': 'item/completed', 'params': {'item': {'type': 'commandExecution', 'id': 'tool', 'exitCode': 0, 'aggregatedOutput': 'successful sensitive output'}}}
            class Process:
                stdin = io.StringIO()
                stdout = io.StringIO(json.dumps(event) + '\n')
            client.process = Process()
            client.secrets = []
            client.messages = []
            client.tool_output = {}
            client.send({'method': 'turn/start', 'params': {'text': 'full prompt'}})
            client.read()
            client.trace.close()
            records = [json.loads(line) for line in subprocess.check_output(['age', '-d', '-i', str(key), str(directory / 'session.jsonl.age')], text=True).splitlines()]
            self.assertEqual('full prompt', records[0]['message']['params']['text'])
            self.assertEqual(event, records[1]['message'])

    def test_complete_events_round_trip_without_plaintext_file(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            key = directory / 'identity'
            subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
            recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
            trace = EncryptedTrace(directory, recipient)
            trace.record('request', {'method': 'turn/start', 'params': {'text': 'sensitive prompt'}})
            trace.record('response', {'method': 'item/commandExecution/outputDelta', 'params': {'delta': 'successful output' * 1000}})
            trace.close()
            encrypted = directory / 'session.jsonl.age'
            self.assertNotIn(b'sensitive prompt', encrypted.read_bytes())
            self.assertEqual({'identity', 'session.jsonl.age'}, {p.name for p in directory.iterdir()})
            records = [json.loads(line) for line in subprocess.check_output(['age', '-d', '-i', str(key), str(encrypted)], text=True).splitlines()]
            self.assertEqual(['request', 'response'], [record['direction'] for record in records])
            self.assertEqual('sensitive prompt', records[0]['message']['params']['text'])
            self.assertEqual('successful output' * 1000, records[1]['message']['params']['delta'])
            self.assertTrue(all(record['timestamp'] for record in records))
            wrong_key = directory / 'wrong-identity'
            subprocess.run(['age-keygen', '-o', str(wrong_key)], check=True, capture_output=True)
            result = subprocess.run(['age', '-d', '-i', str(wrong_key), str(encrypted)], capture_output=True)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b'', result.stdout)

    def test_invalid_recipient_leaves_no_uploadable_file(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with self.assertRaises(ValueError):
                EncryptedTrace(directory, 'not-a-public-key')
            self.assertEqual([], list(directory.iterdir()))

    def test_failed_encryption_removes_partial_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            key = directory / 'identity'
            subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
            recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
            trace = EncryptedTrace(directory, recipient)
            trace.record('request', {'text': 'never publish plaintext'})
            trace.process.kill()
            trace.process.wait()
            with self.assertRaises(RuntimeError):
                trace.close()
            self.assertFalse((directory / 'session.jsonl.age').exists())
            self.assertFalse((directory / 'session.jsonl.age.partial').exists())
