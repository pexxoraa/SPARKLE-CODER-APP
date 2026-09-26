"""Test-only loopback service; no real model calls or container commands."""
from pathlib import Path
import signal
import sys
import tempfile
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sparkle_coder.hosted import HostedServer, Tenants
from sparkle_coder.provider import NemotronClient

gateway=sys.argv[1]
if not gateway.startswith('http://127.0.0.1:'):
    raise SystemExit('The test gateway must use loopback.')

with tempfile.TemporaryDirectory() as directory:
    manager=Tenants(Path(directory),gateway,'R'*64,provider_factory=NemotronClient)
    server=HostedServer(('127.0.0.1',0),manager)
    signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
    print(server.server_port,flush=True)
    try:server.serve_forever(poll_interval=0.02)
    finally:server.server_close();manager.close()
