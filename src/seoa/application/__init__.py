"""Application layer: use cases, the audit pipeline and the ports it needs.

Depends on ``domain`` only (plus the ports it declares). Concrete implementations of the ports
live in ``infrastructure`` and are injected by ``seoa.bootstrap``.
"""
