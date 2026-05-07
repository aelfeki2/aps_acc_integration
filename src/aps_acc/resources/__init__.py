"""Resource modules — one per ACC API surface.

Each resource class wraps a single APS endpoint family. They take the shared
APSClient in their constructor and never make HTTP calls directly; all
requests go through `client.request()` so retries, paging, logging, and auth
work uniformly.
"""
