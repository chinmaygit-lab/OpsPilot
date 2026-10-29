import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from opspilot.api import create_app


def test_non_demo_does_not_seed_public_demo_keys(tmp_path):
    app = create_app(str(tmp_path/'prod.sqlite'), demo_mode=False)
    with TestClient(app) as client:
        assert client.get('/api/me',headers={'X-API-Key':'demo-acme-owner'}).status_code == 401
        assert client.post('/webhooks/default/nope', json={}).status_code == 503


def test_csv_validation_before_side_effects(client, acme_headers):
    iid = client.post('/api/integrations',headers=acme_headers,
                      json={'name':'CSV', 'kind':'csv_upload'}).json()['id']
    bad = 'external_id,title,severity\n1,Valid,high\n2,Invalid,unknown\n'
    response = client.post(f'/api/integrations/{iid}/import-csv', headers=acme_headers,content=bad)
    assert response.status_code == 422
    assert client.get('/api/tasks',headers=acme_headers).json() == []


def test_signature_cannot_be_reused_for_another_tenant(client, acme_headers, nova_headers):
    a = client.post('/api/integrations',headers=acme_headers,json={'name':'A'}).json()['id']
    n = client.post('/api/integrations',headers=nova_headers,json={'name':'N'}).json()['id']
    raw = json.dumps({'title':'Untrusted'}).encode()
    d = hmac.new(b'DEMO-WEBHOOK-SECRET-NEVER-DEPLOY',f'acme:{a}'.encode(),hashlib.sha256).digest()
    sig = 'sha256=' + hmac.new(d,raw,hashlib.sha256).hexdigest()
    headers={'X-Signature':sig,'X-Event-ID':'bad-replay'}
    assert client.post(f'/webhooks/nova/{n}',headers=headers,content=raw).status_code == 401
    assert client.get('/api/summary',headers=nova_headers).json()['events'] == 0
