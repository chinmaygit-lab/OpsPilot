"""Sign and send a sample event; local demo by default, requires 'httpx'."""
import argparse
import hashlib
import hmac
import json
import secrets
import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--org', default='acme')
    p.add_argument('--integration-id', required=True)
    p.add_argument('--base-url', default='http://127.0.0.1:8000')
    p.add_argument('--secret', default='DEMO-WEBHOOK-SECRET-NEVER-DEPLOY')
    args = p.parse_args()
    payload = json.dumps({'kind': 'ticket.created', 'title': 'Signed webhook example',
                          'severity': 'high'}).encode()
    derived = hmac.new(args.secret.encode(),
                       f'{args.org}:{args.integration_id}'.encode(), hashlib.sha256).digest()
    signature = 'sha256=' + hmac.new(derived, payload, hashlib.sha256).hexdigest()
    url = f'{args.base_url.rstrip("/")}/webhooks/{args.org}/{args.integration_id}'
    response = httpx.post(url, content=payload, headers={
        'X-Signature': signature, 'X-Event-ID': secrets.token_hex(12),
        'Content-Type': 'application/json'}, timeout=10)
    print(response.status_code, response.text)
    response.raise_for_status()


if __name__ == '__main__':
    main()
