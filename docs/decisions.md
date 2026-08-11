# Design Decisions Log

## D-001: Container base image and vulnerability remediation
- Chose python:3.12-slim over python:3.12 (full) to reduce image
  size and attack surface.
- Docker Scout scan of v1.0.0 reported 57 vulnerabilities, 7 of
  which originated in the application dependency layer
  (3 high, 3 medium, 1 low - all in starlette 0.41.3).
- Remediated by upgrading FastAPI and Uvicorn, rebuilt as v1.0.1.
- Result: application-layer findings reduced to 0. Image size
  reduced from 243.91 MB to 212.34 MB.
- Residual 50 findings originate in the Debian base layer and
  cannot be patched at application level. Mitigated by non-root
  container execution. Production remediation would be rebasing
  onto a distroless image with scheduled rebuilds.
## D-002: Explicit image tagging in Compose
- Compose configured with both image: and build: so that the
  built artefact carries an explicit semantic version tag.
- Ensures the running container is traceable to a specific scanned
  image, rather than an anonymous project-named build.
- Supports rollback and supply-chain traceability.
## D-003: Exact dependency pinning
- All dependencies pinned to exact versions (==) rather than
  ranges, so builds are byte-reproducible and a given image can be
  rebuilt identically at any later date.
- Trade-off: pinned versions do not pick up security patches
  automatically. Mitigated by Docker Scout scanning, which surfaces
  outdated packages, and by a deliberate upgrade-and-retag cycle
  (see D-001).