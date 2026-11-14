# Security, privacy and limits

**English** · [Türkçe](security-and-limits.tr.md)

## Security and privacy

- User-supplied addresses go through a single client: private IPs, loopback and metadata addresses are rejected; every redirect and render request is validated.
- Keys live only in `.env`; they are never written to logs, reports or error messages. The Settings page never shows a key back, only whether it is set.
- To report a vulnerability, see [`SECURITY.md`](../SECURITY.md).

## Limits

Single user, no authentication, in-process queue and SQLite. Speed is **lab** data (measured from this machine); real-user data needs a CrUX key, and Google has no data for new or low-traffic sites. There is no backlink data. The full list of known limits is in [`CHANGELOG.md`](../CHANGELOG.md).
