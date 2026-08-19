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
## D-010: PCI-DSS scope minimisation by schema design
- The payments table stores only an opaque gateway token and the last
  four digits (varchar(4)). No column exists that could hold a PAN,
  CVV or expiry date.
- Scope is reduced structurally, not by convention: a defect in
  application code could not cause card data to be persisted.
- In a production integration the card number would pass directly from
  the client to the payment provider and never transit this service at
  all, keeping it outside PCI-DSS assessment scope entirely.
## D-011: Test isolation under eventual consistency
- An end-to-end test asserting an exact stock delta failed
  intermittently: earlier tests had created orders whose sagas were
  still in flight when the assertion ran.
- The fault was in the test's assumption, not the system. Stock is
  updated by an asynchronous consumer, so a read immediately after an
  API response does not reflect pending reservations.
- Resolved by giving the test an exclusive product fixture. This is
  the same constraint a real client faces: order acceptance and stock
  reservation are separated in time by design, which is why the
  client is notified over WebSocket rather than polling.
## D-012: Erasure placeholder broke the user listing endpoint
- GDPR erasure replaced the email with a value on the .local
  special-use domain. That value fails EmailStr validation, so
  serialising an erased record through the response schema raised an
  error: a single erased account returned 500 from GET /api/v1/users.
- Found by an automated security test, not by manual testing — the
  fault only appears when an erased record is included in a list
  response.
- Resolved by using the IANA documentation domain example.com, which
  is non-routable but syntactically valid.
- Illustrates why anonymisation values must satisfy the same
  validation constraints as real data.
## D-013: Data repair required after fixing the erasure defect
- Correcting the erasure placeholder did not restore the listing
  endpoint: records written by the defective version remained in the
  database and continued to fail response validation.
- A code fix alone is insufficient when a defect has already written
  invalid data. A migration was required to repair existing rows.
- Reinforces why anonymisation values must satisfy the same validation
  constraints as live data: an invalid value written once persists
  until explicitly corrected.
## D-014: Scaling comparison invalidated by an unrelated bottleneck
- The first scalability comparison registered a distinct account per
  simulated user. At 200 concurrent users this issued roughly 400
  Argon2id hashes simultaneously, saturating the User Service:
  registration reached 145s and login 181s, and the health check
  failed, preventing the scale-up step from running at all.
- The measurement was therefore invalid: the bottleneck had moved to
  the User Service, so scaling the Order Service could not have shown
  any effect.
- Corrected by issuing a single shared token at test start, isolating
  the order path as the component under test, and reducing
  concurrency to 100 to remain below the saturation point identified
  by the stress test.
- Demonstrates that a load profile must be designed around the
  component under measurement: an incidental cost elsewhere in the
  system can dominate and invalidate the result.
## D-015: Fixed host port prevented horizontal scaling
- The order service published a fixed host port (8003:8000). Scaling
  beyond one instance failed with "port is already allocated": only one
  container can bind a given host port.
- Even had the containers started, all client traffic addressed
  localhost:8003 and would have reached a single instance, so no load
  distribution was possible.
- Resolved by removing the published port and placing nginx in front as
  a load balancer, using Docker's embedded DNS to resolve all instances
  of the service and least-connections routing to account for variable
  request cost.
- This is the same constraint that makes fixed host ports unusable in
  container orchestration generally, and why ECS and Kubernetes assign
  dynamic ports and register targets with a load balancer rather than
  publishing ports directly.
## D-016: Connection pool capacity confirmed as the scaling constraint
- Scaling the Order Service 1 to 3 behind nginx raised throughput
  3.5 to 72.6 req/s and cut failures from 35.2% to zero.
- The superlinear gain confirms the single-instance run was saturated
  rather than merely slow: blocked requests held connections for the
  full 60s gateway timeout.
- Endpoints using the PostgreSQL pool improved by 98-99.9%; DynamoDB
  reads regressed 80-97% at p95 under the higher aggregate load,
  showing the remaining constraint is shared host CPU.
- Confirms the stress-test diagnosis and validates horizontal scaling
  of the application tier as the correct remediation.
## D-017: Endpoint configuration prevented deployment to real AWS
- The catalogue service always passed endpoint_url to boto3, defaulting
  to the LocalStack address. In AWS the container failed during startup
  and ECS restarted it repeatedly (uvicorn exit code 3).
- Fixed by passing endpoint_url only when explicitly configured, so
  boto3 resolves the regional endpoint by default.
- The same image now runs against LocalStack locally and managed AWS
  services in deployment, differing only by one environment variable.
- Found only by deploying: local emulation validated the SDK calls but
  not the configuration path used in production.
## D-018: Incomplete stored item surfaced as a 500 rather than a 422
- A DynamoDB item written directly via the CLI omitted fields required
  by the response schema. The read returned 500 Internal Server Error
  rather than a diagnostic message.
- The schemaless datastore accepts any item shape; validation occurs
  only at serialisation time, so malformed data is detected on read
  rather than on write.
- Illustrates a genuine trade-off in schemaless storage: flexibility on
  write shifts the integrity burden to the application. A production
  system would validate on the write path and treat unserialisable
  stored records as 500-class defects requiring data repair, as
  occurred earlier with the erasure placeholder (D-012).