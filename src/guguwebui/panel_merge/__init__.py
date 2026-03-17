"""
Multi-server panel merge (master/slave) feature.

- Proxy middleware (master): dispatches /api/* to selected slave by X-Target-Server.
- Local-only APIs: /api/servers, /api/panel_merge_config
- Pairing handshake APIs: /api/pairing/*
"""

