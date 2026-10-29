import hashlib
import hmac
import json


def test_health_and_auth(client, acme_headers):
    assert client.get('/health').json()['status'] == 'ok'
    assert client.get('/api/tasks').status_code == 401
    assert client.get('/api/me', headers=acme_headers).json()['role'] == 'owner'
    assert client.get('/').status_code == 200
    assert client.get('/assets/styles.css').status_code == 200


def test_tenant_isolation_and_role(client, acme_headers, nova_headers, viewer_headers):
    response = client.post('/api/tasks', headers=acme_headers, json={'title':'Alpha confidential','priority':'urgent'})
    assert response.status_code == 201
    task = response.json()
    assert len(client.get('/api/tasks', headers=acme_headers).json()) == 1
    assert client.get('/api/tasks', headers=nova_headers).json() == []
    assert client.get('/api/summary', headers=nova_headers).json()['total_tasks'] == 0
    assert client.post('/api/tasks', headers=viewer_headers, json={'title':'Try create'}).status_code == 403
    assert client.post('/api/tools/call', headers=nova_headers,
                       json={'name':'tasks.complete','arguments':{'task_id':task['id']}}).status_code == 200
    assert client.get('/api/tasks', headers=acme_headers).json()[0]['status'] == 'open'
    assert client.get('/api/approvals', headers=viewer_headers).status_code == 403


def test_tool_policy_and_audit(client, acme_headers, viewer_headers):
    assert client.post('/api/tools/call', headers=viewer_headers,
                       json={'name':'tasks.create','arguments':{'title':'x'}}).status_code == 403
    assert client.post('/api/tools/call', headers=acme_headers,
                       json={'name':'tasks.create','arguments':{'title':'x','unexpected':1}}).status_code == 422
    created = client.post('/api/tools/call', headers=acme_headers,
                          json={'name':'tasks.create','arguments':{'title':'Need review'}}).json()
    task_id = created['task']['id']
    pending = client.post('/api/tools/call', headers=acme_headers,
                          json={'name':'tasks.complete','arguments':{'task_id':task_id}}).json()
    assert 'approval_id' in pending
    assert client.get('/api/tasks', headers=acme_headers).json()[0]['status'] == 'open'
    approval_id = pending['approval_id']
    assert len(client.get('/api/approvals', headers=acme_headers).json()) == 1
    reviewed = client.post(f'/api/approvals/{approval_id}/review', headers=acme_headers,
                           json={'decision':'approve'})
    assert reviewed.status_code == 200
    assert client.get('/api/tasks', headers=acme_headers).json()[0]['status'] == 'done'
    assert client.post(f'/api/approvals/{approval_id}/review', headers=acme_headers,
                       json={'decision':'approve'}).status_code == 404
    assert len(client.get('/api/audit', headers=acme_headers).json()) >= 4


def test_rejection(client, acme_headers):
    tid = client.post('/api/tasks', headers=acme_headers,json={'title':'Unchanged'}).json()['id']
    aid = client.post('/api/tools/call', headers=acme_headers,
                      json={'name':'tasks.complete','arguments':{'task_id':tid}}).json()['approval_id']
    assert client.post(f'/api/approvals/{aid}/review', headers=acme_headers,
                       json={'decision':'reject'}).json()['status'] == 'rejected'
    assert client.get('/api/tasks', headers=acme_headers).json()[0]['status'] == 'open'


def test_sync_cursor_and_duplicate(client, acme_headers, nova_headers):
    integration = client.post('/api/integrations', headers=acme_headers,
                              json={'name':'Demo'}).json()
    iid = integration['id']
    assert client.post(f'/api/integrations/{iid}/sync', headers=nova_headers).status_code == 404
    first = client.post(f'/api/integrations/{iid}/sync', headers=acme_headers).json()
    assert first['created'] == 5 and first['cursor'] == 5 and first['pages'] == 3
    second = client.post(f'/api/integrations/{iid}/sync', headers=acme_headers).json()
    assert second['created'] == 0
    metrics = client.get('/api/summary', headers=acme_headers).json()
    assert metrics['events'] == metrics['total_tasks'] == 5
    assert metrics['priority']['urgent'] == 1
    assert client.get('/api/summary', headers=nova_headers).json()['events'] == 0


def test_signed_webhook_and_idempotency(client, acme_headers):
    iid = client.post('/api/integrations', headers=acme_headers,
                      json={'name':'Webhook destination'}).json()['id']
    payload = {'kind':'ticket.created','title':'High stakes','severity':'critical'}
    raw = json.dumps(payload).encode()
    url = f'/webhooks/acme/{iid}'
    assert client.post(url, content=raw, headers={'X-Event-ID':'evt-x'}).status_code == 401
    derived = hmac.new(b'DEMO-WEBHOOK-SECRET-NEVER-DEPLOY',f'acme:{iid}'.encode(), hashlib.sha256).digest()
    signature = 'sha256=' + hmac.new(derived,raw,hashlib.sha256).hexdigest()
    headers = {'X-Event-ID':'evt-x','X-Signature':signature,'Content-Type':'application/json'}
    first = client.post(url,content=raw,headers=headers)
    assert first.status_code == 200 and first.json()['deduplicated'] is False
    assert client.post(url,content=raw,headers=headers).json()['deduplicated'] is True
    assert client.get('/api/summary',headers=acme_headers).json()['total_tasks'] == 1


def test_agent_team_and_tenant_guard(client, acme_headers, viewer_headers):
    response = client.post('/api/agent/run', headers=viewer_headers,
                           json={'objective':'Summarize outstanding issues'})
    assert response.status_code == 200
    result = response.json()
    assert result['agents'] == ['insight-agent','planner-agent','tool-executor']
    assert [x['tool'] for x in result['tool_results']] == ['analytics.summary','tasks.list']
    assert client.get('/api/tools',headers=viewer_headers).json()[0]['name'] == 'tasks.list'
    assert client.get('/api/approvals',headers=acme_headers).json() == []


def test_csv_formula_escape(client, acme_headers):
    client.post('/api/tasks',headers=acme_headers,json={'title':'=HYPERLINK("http://evil")'})
    data=client.get('/api/tasks.csv',headers=acme_headers).text
    assert "'=HYPERLINK" in data


def test_live_socket(client):
    with client.websocket_connect('/ws/live') as socket:
        socket.send_json({'api_key':'demo-acme-viewer'})
        frame = socket.receive_json()
        assert frame['type'] == 'snapshot'
        assert frame['summary']['total_tasks'] == 0


def test_csv_ingestion_is_tenant_scoped_and_repeat_safe(client, acme_headers, nova_headers):
    iid = client.post('/api/integrations',headers=acme_headers,
                      json={'name':'CSV', 'kind':'csv_upload'}).json()['id']
    csv_data = 'external_id,title,severity\nrow-1,New import,high\nrow-2,Critical issue,critical\n'
    endpoint = f'/api/integrations/{iid}/import-csv'
    assert client.post(endpoint, headers=nova_headers, content=csv_data).status_code == 404
    first = client.post(endpoint, headers=acme_headers, content=csv_data)
    assert first.status_code == 200 and first.json()['created'] == 2
    second = client.post(endpoint, headers=acme_headers, content=csv_data)
    assert second.json()['deduplicated'] == 2
    assert client.get('/api/summary',headers=acme_headers).json()['events'] == 2
    assert client.post(endpoint, headers=acme_headers, content='wrong,column\nx,y').status_code == 422
    assert client.post(f'/api/integrations/{iid}/sync', headers=acme_headers).status_code == 422
