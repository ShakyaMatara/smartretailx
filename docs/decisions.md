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
## D-004: Private key mounting and container user permissions
- JWT signing key mounted read-only at runtime rather than copied
  into the image, so the secret is never baked into a distributable
  artefact.
- Initial deployment failed with PermissionError: the key was
  generated 0600 root-owned while the container runs as a non-root
  user - the least-privilege control working as intended.
- Resolved by assigning a fixed UID/GID to the application user and
  granting group read on the key file, preserving both non-root
  execution and the read-only mount.
- In AWS this problem does not arise: the key would be retrieved from
  Secrets Manager by the task at launch and never exist as a file on
  a mounted volume.
## D-005: RS256 asymmetric token signing
- JWTs signed with RS256 rather than HS256. HS256 uses one shared
  secret for both signing and verification, so any service able to
  verify a token could also forge one.
- With RS256 only the User Service holds the private key. Other
  services verify using the public key published at
  /.well-known/jwks.json, with no shared secret distributed.
- Tokens carry a kid header so multiple public keys can be published
  simultaneously, enabling key rotation without invalidating tokens
  signed by the previous key.
- Access tokens expire in 15 minutes to limit the exposure window
  from a stolen token; refresh tokens last 7 days.
- Decoding uses an explicit algorithm allow-list, preventing the
  "alg: none" and algorithm-confusion attack classes.
## D-006: Local AWS emulation and third-party dependency risk
- LocalStack chosen to emulate DynamoDB, SQS and SNS locally so that
  application code uses the real AWS SDK (boto3) and is portable to
  AWS by changing a single endpoint environment variable.
- Encountered a licensing change: as of the 2026.03 release the
  previously free community image was consolidated into a single
  authenticated image, causing the container to exit on startup.
- Resolved by registering for the free non-commercial tier and
  injecting the auth token as an environment variable, and by pinning
  the image to an explicit version rather than :latest.
- Illustrates a real supply-chain risk in distributed architectures:
  a third-party dependency changed its access model and broke the
  build. Pinning versions and avoiding :latest limits exposure to
  unannounced upstream changes.
## D-007: Idempotency scope
- POST /api/v1/products is non-idempotent by REST convention: repeated
  submissions create separate products, and SKU uniqueness is not
  enforced at the datastore.
- Accepted as a known limitation for the catalogue, where duplicates
  are a data-quality issue rather than a correctness failure.
- Idempotency keys ARE implemented for order creation and payment,
  where a duplicated request would result in a double charge. Effort
  is directed at the operations where non-idempotency causes harm.
- Production remediation for the catalogue would be a conditional
  write against a uniqueness index on sku.
## D-008: Redundant identifier in inventory upsert payload
- PUT /api/v1/inventory/{product_id} accepts product_id in both the
  path and the request body. Only the path value is used.
- Identified during testing when a mismatched body silently had no
  effect, creating stock against the wrong product.
- A duplicated identifier with no validation is an API design fault:
  it permits a request whose meaning is ambiguous.
- Remediation would be to remove product_id from the request schema,
  or to return 400 when the two disagree.
## D-009: Container logs are ephemeral
- Log evidence for one transaction was lost when a service container
  was recreated: Docker retains logs per container instance, not per
  service.
- Demonstrates why centralised log aggregation is required in a
  distributed system rather than optional. Logs must be shipped off
  the compute instance as they are written.
- Locally, stdout JSON logs are collected by the Docker daemon; in
  AWS the ECS awslogs driver streams them to CloudWatch Logs, where
  they persist independently of task lifecycle and are queryable via
  Logs Insights across all services.