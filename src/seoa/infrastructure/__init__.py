"""Infrastructure layer: everything that touches the outside world.

SQLite, the SSRF-safe HTTP client, the headless browser, the LLM client and third-party APIs.
Implements the ports declared in ``application``; never imported by ``domain`` or ``application``.
"""
