"""Print the Google / Search Console setup status and the next step (never secrets).

Usage: .venv/bin/python scripts/google_setup_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seoa.config import get_settings  # noqa: E402
from seoa.infrastructure.integrations.google_oauth import GoogleOAuth  # noqa: E402


def main() -> int:
    settings = get_settings()
    oauth = GoogleOAuth(settings)
    st = oauth.status()
    mark = {True: "evet", False: "hayır"}
    print(f"OAuth istemcisi tanımlı : {mark[st['configured']]}  ({settings.google_client_path})")
    print(
        f"Hesap bağlı             : {mark[st['connected']]}"
        + (f"  ({st['email']})" if st["email"] else "")
    )
    print(f"API anahtarı (CrUX/PSI) : {mark[bool(os.environ.get('SEOA_GOOGLE_API_KEY'))]}")
    if not st["configured"]:
        print(
            "\nSonraki adım: docs/google-setup.md bölüm 1-3; JSON'u data/google_client.json yapın."
        )
    elif not st["connected"]:
        print(
            "\nSonraki adım: uygulamayı başlatıp http://127.0.0.1:<port>/connect/google adresini açın."
        )
    else:
        print(
            "\nHazır. Denetlediğiniz alan adı için Search Console'da doğrulanmış mülk olmalı (bölüm 5)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
