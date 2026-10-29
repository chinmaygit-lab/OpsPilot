import pytest
from opspilot.connectors import MockTicketConnector
from opspilot.db import Database
from opspilot.services import create_task, ingest_event, list_tasks
from opspilot.agents import invoke


def test_connector_pages():
    connector=MockTicketConnector()
    first, cursor=connector.fetch_page(0, 2)
    assert cursor == 2 and len(first)==2
    last, cursor=connector.fetch_page(4, 2)
    assert cursor == 5 and len(last)==1
    assert connector.fetch_page(5)[0] == []


def test_key_storage_not_plaintext(tmp_path):
    db=Database(str(tmp_path/'db.sqlite'))
    db.add_org('o','Org')
    db.add_key('o','Test','owner','very-secret')
    with db.connect() as con:
        data=con.execute('SELECT key_hash FROM principals').fetchone()[0]
    assert data!='very-secret' and len(data)==64
    assert db.identity('very-secret')['org_id']=='o'
    assert db.identity('wrong') is None


def test_invalid_and_tenant_scoped_service(tmp_path):
    db=Database(str(tmp_path/'db.sqlite'))
    db.add_org('one','One');db.add_org('two','Two')
    item=create_task(db,'one',' title ')
    assert item['title']=='title'
    assert not list_tasks(db,'two')
    with pytest.raises(ValueError):
        create_task(db,'one','')
    with pytest.raises(PermissionError):
        invoke(db, {'org_id':'one','name':'Viewer','role':'viewer'},'tasks.create',{'title':'Denied'})
