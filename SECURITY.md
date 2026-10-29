# Security model (demo)

## Trust boundaries
Untrusted: user input, uploaded documents, retrieved text, tool outputs, **and model output**. Trusted: server-side policy code and configuration.

## Controls
| Threat | Control | Tests |
|---|---|---|
| Credential theft / brute force | Argon2id, per-email+IP login throttle, uniform login errors | `test_auth`, `test_security_csrf_sessions` |
| Session theft / replay | Opaque 256-bit tokens, only SHA-256 stored, expiry, revocation, HttpOnly SameSite=Lax cookie | same |
| CSRF | Per-session token required in `X-CSRF-Token` on every non-GET | `test_every_mutation_requires_csrf_token` |
| Cross-user data access | Ownership checks return 404; retrieval filters in the query itself | `test_chat`, `test_rag` |
| Role forgery | Role never read from client; self-registration is always `user` | `test_auth` |
| Prompt injection | Retrieved text is delimited as untrusted data; tool use is validated server-side regardless of model output | `test_security_injection` |
| Unsafe tool execution | Allowlist, schema validation, permission check, confirmation for high-risk, idempotency, timeout, output cap, bounded loop | `test_tools`, `test_security_injection` |
| Upload abuse | Extension allowlist, signature check, size cap, page and zip-expansion limits, basename-only filenames | `test_rag` |
| Secret leakage | Log redaction, admin health omits config values, keys server-side only | `test_observability`, `test_admin` |

## Known limitations (accepted for the demo)
- Prompt injection cannot be eliminated; controls limit blast radius rather than detect attacks.
- Login throttling and cancellation state are in-process (single instance only).
- Uploads are parsed in-process (no sandbox).
- No TLS termination or `Secure` cookies by default; set `NOVA_COOKIE_SECURE=true` behind HTTPS.
- Demo seed accounts share a published synthetic password; never seed outside local use.
