# chatterbox#11 Unblock Rationale

Date: 2026-08-02

The previous blocker was `grahama1970/tau#288` because Chatterbox needed Tau's
canonical `tau.voice_render_request.v2` schema and hash-bound fixtures before
implementing a strict consumer.

That source contract is now available on `grahama1970/tau@main`:

- commit: `a1106d9b97edf41bb66843a60164b3ab3b1a571d`
- schema: `docs/contracts/voice/tau.voice_render_request.v2.schema.json`
- fixtures: `docs/contracts/voice/fixtures/*.json`
- manifest: `docs/contracts/voice/MANIFEST.sha256`

The remaining work is now deterministic Chatterbox implementation and live
readback proof, so `needs-human` / `maintainer-blocked` are stale for
`chatterbox#11`.
