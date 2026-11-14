"""Start the MVP: API + HTML UI on localhost (single user, no auth)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn  # noqa: E402

from seoa.bootstrap import build_local_service  # noqa: E402
from seoa.infrastructure.integrations.google_oauth import GoogleOAuth  # noqa: E402
from seoa.infrastructure.integrations.gsc import GscClient  # noqa: E402
from seoa.presentation.api.app import create_app  # noqa: E402
from seoa.presentation.api.google_routes import create_google_router  # noqa: E402


def main() -> None:
    oauth = GoogleOAuth()
    # the client is built per audit run; it reports "not connected" itself when there is no token
    service = build_local_service(gsc_client=GscClient(oauth) if oauth.is_configured() else None)
    app = create_app(service, google_router=create_google_router(oauth), google_status=oauth.status)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"SEO analyzer MVP -> http://127.0.0.1:{port}  (localhost only)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
