"""Loopback byte recorder for Ollama's native Anthropic endpoint.

This is not a protocol adapter: application request/response bytes are unchanged.
HTTP transfer framing is terminated locally; exact dechunked body bytes, status,
and ordered upstream headers are retained. There are no inference retries.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit

MODEL = 'qwen3.5:9b-q4_K_M'
MAX_CALLS = 16
MAX_BODY_BYTES = 8_000_000
MAX_SECONDS = 1860  # Requested 1800-second CLI budget plus the unchanged 60-second transport margin.


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def allowed_path(path):
    parsed = urlsplit(path)
    return (not parsed.scheme and not parsed.netloc and not parsed.fragment
            and parsed.path == '/v1/messages' and parsed.query in ('', 'beta=true'))


def validate_request(raw):
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('model') != MODEL:
        raise ValueError('Only the pinned local model is authorized.')
    if type(payload.get('max_tokens')) is not int or not 1 <= payload['max_tokens'] <= 4096:
        raise ValueError('The observed output bound must be 1..4096.')
    if type(payload.get('stream')) is not bool:
        raise ValueError('An explicit streaming choice is required.')
    tools = payload.get('tools', [])
    if not isinstance(tools, list) or not tools:
        raise ValueError('The actual restricted read-only tools are required.')
    names = [tool.get('name') if isinstance(tool, dict) else None for tool in tools]
    if len(names) != len(set(names)) or any(name not in ('Read', 'Glob', 'Grep') for name in names):
        raise ValueError('Unexpected or duplicate tool declarations.')
    return payload


class RecorderServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(min(10, max(0.1, self.deadline - time.monotonic())))
        # Absolute header/body parse bound, including a slow trickle of bytes.
        def abort_parse():
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        timer = threading.Timer(min(10, max(0.1, self.deadline - time.monotonic())), abort_parse)
        timer.daemon = True
        timer.start()
        self.header_timer = timer
        return connection, address


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *_):
        pass

    def finish(self):
        timer = getattr(self.server, 'header_timer', None)
        if timer is not None:
            timer.cancel()
        super().finish()

    def reject(self, status, message):
        body = json.dumps(dict(type='error', error=dict(type='invalid_request_error', message=message))).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        server = self.server
        server.requests += 1
        prefix = server.directory / ('request-%02d' % server.requests)
        record = dict(startedAtUtc=now(), path=self.path, upstreamCallsMade=0,
                      upstreamCallsObservedTotal=server.calls, byteTransformation=False,
                      anthropicServerClassifierImplemented=False)
        raw = b''
        upstream = None
        connected_socket = None
        absolute_timer = None
        response_path = prefix.with_name(prefix.name + '-response.bin')
        try:
            length = self.headers.get('Content-Length', '')
            if not length.isdecimal() or not 0 < int(length) <= MAX_BODY_BYTES or self.headers.get('Transfer-Encoding'):
                raise ValueError('A bounded exact Content-Length body is required.')
            raw = self.rfile.read(int(length))
            prefix.with_name(prefix.name + '-request.bin').write_bytes(raw)
            record.update(requestBytes=len(raw), requestSha256=sha(raw))
            if len(raw) != int(length):
                raise ValueError('Incomplete request body.')
            server.header_timer.cancel()
            if not allowed_path(self.path):
                raise ValueError('Only the native messages path and observed beta=true are authorized.')
            if server.stopped or server.calls >= MAX_CALLS or time.monotonic() >= server.deadline:
                raise ValueError('This single attempt is stopped or exhausted.')
            validate_request(raw)
            remaining = max(0.1, server.deadline - time.monotonic())
            self.connection.settimeout(remaining)
            upstream = http.client.HTTPConnection('127.0.0.1', server.upstream_port, timeout=remaining)
            # No auth, cookie, proxy, or arbitrary client header is copied.
            headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
            for name in ('anthropic-version', 'anthropic-beta'):
                if self.headers.get(name):
                    headers[name] = self.headers[name]
            server.calls += 1
            record.update(upstreamCallsMade=1, upstreamCallsObservedTotal=server.calls, forwardedAtUtc=now())
            # A stalled native model stream cannot exceed the absolute session deadline.
            def abort_sockets():
                for connection in (connected_socket, getattr(upstream, 'sock', None), self.connection):
                    if connection is not None:
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        try:
                            connection.close()
                        except OSError:
                            pass
            absolute_timer = threading.Timer(remaining, abort_sockets)
            absolute_timer.daemon = True
            absolute_timer.start()
            upstream.request('POST', self.path, body=raw, headers=headers)
            # HTTPResponse may detach the socket from HTTPConnection for close-delimited
            # responses. Retain it so the absolute timer also interrupts body reads.
            connected_socket = upstream.sock
            response = upstream.getresponse()
            record.update(status=response.status, reason=response.reason, responseHeaders=response.getheaders(),
                          headersReceivedAtUtc=now(), responseBodyEncoding='exact dechunked application bytes')
            self.send_response_only(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in ('connection', 'transfer-encoding', 'content-length', 'keep-alive'):
                    self.send_header(name, value)
            self.send_header('Connection', 'close')
            self.end_headers()
            with response_path.open('xb') as output:
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    output.write(chunk)
                    output.flush()
                    self.wfile.write(chunk)
                    self.wfile.flush()
                if response.length not in (None, 0):
                    raise RuntimeError('Native response ended before its declared Content-Length.')
            record['responseComplete'] = True
            if response.status != 200:
                server.stopped = True
                record['permanentStopReason'] = 'native_http_error_no_retry'
        except Exception as error:
            server.stopped = True
            record.update(error=type(error).__name__ + ': ' + str(error), permanentStopReason='no_retry_after_ambiguous_or_rejected_request')
            if 'status' not in record:
                try:
                    self.reject(502 if record['upstreamCallsMade'] else 400, record['error'])
                except OSError:
                    pass
        finally:
            if absolute_timer is not None:
                absolute_timer.cancel()
            if upstream is not None:
                upstream.close()
            record['completedAtUtc'] = now()
            if response_path.exists():
                body = response_path.read_bytes()
                record.update(responseBytes=len(body), responseSha256=sha(body))
            save(prefix.with_name(prefix.name + '-receipt.json'), record)
            self.close_connection = True

    def do_GET(self):
        self.server.stopped = True
        self.reject(405, 'No recorder control or shutdown HTTP route exists.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-port', type=int, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.upstream_port <= 65535:
        raise ValueError('The exact owned loopback port is required.')
    directory = args.evidence_dir.resolve()
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    stop = args.stop_file.resolve()
    if stop.parent != directory or stop.exists():
        raise ValueError('The new stop file must be a direct child of evidence.')
    server = RecorderServer(('127.0.0.1', 0), Handler)
    server.timeout = 1
    server.directory, server.upstream_port = directory, args.upstream_port
    server.calls, server.requests, server.stopped = 0, 0, False
    server.deadline = time.monotonic() + MAX_SECONDS
    save(directory / 'session.json', dict(startedAtUtc=now(), listenHost='127.0.0.1', listenPort=server.server_port,
        upstreamHost='127.0.0.1', upstreamPort=args.upstream_port, model=MODEL,
        nativeProtocol='Ollama Anthropic-compatible API; no protocol translation',
        requestResponseBodyTransformation=False, authenticationHeadersRecorded=False,
        maxNativeCalls=MAX_CALLS, wholeSessionSeconds=MAX_SECONDS,
        anthropicServerClassifierImplemented=False))
    try:
        while time.monotonic() < server.deadline and not stop.exists() and not server.stopped:
            server.handle_request()
    finally:
        server.server_close()
        save(directory / 'closed.json', dict(closedAtUtc=now(), upstreamCalls=server.calls,
            requests=server.requests, stopped=server.stopped,
            operatorStopObserved=stop.exists(), wholeBudgetExpired=time.monotonic() >= server.deadline))


if __name__ == '__main__':
    main()
