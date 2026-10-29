'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function createHarness() {
  const nodes = new Map();
  const globalListeners = new Map();
  const timeoutTasks = new Map();
  const fetchCalls = [];
  let timerId = 0;
  let didReload = false;

  function element(name) {
    if (!nodes.has(name)) {
      const handlers = new Map();
      const classes = new Set();
      nodes.set(name, {
        value: '', textContent: '', innerHTML: '', className: '',
        classList: {
          add: (c) => classes.add(c),
          remove: (c) => classes.delete(c),
          toggle: (c, force) => force ? classes.add(c) : classes.delete(c),
          contains: (c) => classes.has(c),
        },
        addEventListener: (type, fn) => handlers.set(type, fn),
        trigger: (type, arg) => handlers.get(type)(arg),
      });
    }
    return nodes.get(name);
  }
  class FakeWebSocket {
    static instances = [];
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.closed = false;
      FakeWebSocket.instances.push(this);
    }
    send(message) { this.sent.push(message); }
    close() {
      this.closed = true;
      if (this.onclose) this.onclose({code: 1000});
    }
  }
  const sandbox = {
    document: {
      querySelector: element,
      addEventListener: (type, fn) => globalListeners.set(type, fn),
    },
    window: {location: {reload: () => {didReload = true;}}},
    location: {protocol: 'http:', host: '127.0.0.1:8000'},
    WebSocket: FakeWebSocket,
    fetch: async (endpoint) => {
      fetchCalls.push(endpoint);
      const responses = {
        '/api/me': {org_id:'acme', role:'owner', name:'Acme Admin'},
        '/api/summary': {
          total_tasks:0, events:0, integrations:0, pending_approvals:0,
          status:{}, priority:{}, sources:{}, event_trend:[],
        },
        '/api/tasks': [], '/api/integrations': [], '/api/approvals': [], '/api/audit': [],
      };
      assert.ok(Object.hasOwn(responses, endpoint), `Unexpected API call: ${endpoint}`);
      return {ok:true, json: async () => responses[endpoint]};
    },
    setTimeout: (fn, delay) => {const id=++timerId;timeoutTasks.set(id, {fn: () => {timeoutTasks.delete(id); fn();},delay});return id;},
    clearTimeout: (id) => timeoutTasks.delete(id),
    console,
  };
  const source = fs.readFileSync(path.join(__dirname, '..', 'opspilot', 'static', 'app.js'), 'utf8');
  vm.runInNewContext(source, sandbox, {filename: 'app.js'});
  return {element, FakeWebSocket, timeoutTasks, get didReload(){return didReload;}};
}

(async function main(){
  const h = createHarness();
  h.element('#apiKey').value = 'demo-acme-owner';
  await h.element('#connect').trigger('click');
  assert.equal(h.element('#identity').textContent, 'acme · owner');
  assert.equal(h.FakeWebSocket.instances.length, 1);
  const first = h.FakeWebSocket.instances[0];
  assert.match(h.element('#connection').textContent, /Connecting/);
  first.onopen();
  assert.deepEqual(JSON.parse(first.sent[0]), {api_key:'demo-acme-owner'});
  assert.match(h.element('#connection').textContent, /Authenticating/);
  first.onmessage({data:JSON.stringify({type:'snapshot', summary:{total_tasks:0, events:0, pending_approvals:0, status:{},priority:{}},tasks:[]})});
  assert.match(h.element('#connection').textContent, /Live/);
  assert.equal(h.element('#connection').classList.contains('online'), true);
  first.onclose({code:1006});
  assert.match(h.element('#connection').textContent, /Reconnecting/);
  assert.equal(h.timeoutTasks.size, 1);
  const task = [...h.timeoutTasks.values()][0];
  assert.equal(task.delay, 1000);
  task.fn();
  assert.equal(h.FakeWebSocket.instances.length, 2);
  const second = h.FakeWebSocket.instances[1];
  assert.match(h.element('#connection').textContent, /Reconnecting/);
  h.element('#disconnect').trigger('click');
  assert.equal(second.closed, true);
  assert.equal(h.timeoutTasks.size, 0);
  assert.equal(h.didReload, true);
  console.log('PASS: authenticated snapshot, auto-reconnect, disconnect cleanup');
})().catch(error => {console.error(error);process.exitCode=1;});
