# Security policy

## Reporting a vulnerability

If you found a vulnerability, please **do not open a public issue**. Create a private security advisory from the repository's *Security* tab (GitHub Security Advisories) and include: the affected version, the steps to reproduce, and the impact.

## Scope and design assumptions

- The app is designed for **a single user on `localhost`**; there is no authentication. Exposing it to the internet is not supported.
- User-supplied addresses go through a single client (SSRF protection): private and loopback addresses and cloud metadata addresses are rejected, and every redirect and render request is validated. Any finding that bypasses this protection is a priority.
- Keys are kept only in the `.env` file and are never written to logs, reports or error messages. Google tokens are stored in `data/google_tokens.json`, readable only by the owner.
- Text taken from a page is treated as untrusted: HTML is escaped, text handed to the AI is bounded and quotes are verified.

## Supported versions

Only the latest release.
