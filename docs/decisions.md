# Design Decisions Log

What follows is a record of the decisions that shaped SmartRetailX, and the
problems that forced some of them. Thirteen of the eighteen entries are
defects — things that broke, why they broke, and what fixed them. The rest
are choices made deliberately, with the alternative that lost out.

| # | Decision | Type |
|---|----------|------|
| D-001 | Slim base image; vulnerability scan and remediation | Choice |
| D-002 | Explicit image tags in Compose for traceability | Choice |
| D-003 | Exact dependency pinning for reproducible builds | Choice |
| D-004 | Private key mounted at runtime, not baked into the image | Defect |
| D-005 | RS256 over HS256 for token signing | Choice |
| D-006 | LocalStack for AWS emulation; a licence change broke the build | Defect |
| D-007 | Idempotency only where duplication actually causes harm | Choice |
| D-008 | Redundant identifier in the inventory upsert payload | Defect |
| D-009 | Container logs vanish with the container | Defect |
| D-010 | PCI-DSS scope minimised by schema, not by convention | Choice |
| D-011 | Test isolation under eventual consistency | Defect |
| D-012 | GDPR erasure placeholder broke the user listing endpoint | Defect |
| D-013 | Fixing the code was not enough; the bad data was still there | Defect |
| D-014 | Scaling comparison ruined by a bottleneck somewhere else | Defect |
| D-015 | A fixed host port made horizontal scaling impossible | Defect |
| D-016 | The connection pool was the constraint all along | Finding |
| D-017 | Endpoint configuration stopped the service starting in AWS | Defect |
| D-018 | An incomplete stored item came back as a 500, not a 422 | Defect |

---

## D-001: Container base image and vulnerability remediation

The services build on `python:3.12-slim` rather than the full image, which
keeps both the download size and the attack surface smaller. Scanning the
first build with Docker Scout returned 57 vulnerabilities. Only seven of
those came from the application's own dependencies — three high, three
medium and one low, all in `starlette 0.41.3` — and those seven were the
only ones worth acting on.

Upgrading FastAPI and Uvicorn cleared all seven and dropped the image from
243.91 MB to 212.34 MB along the way. The remaining 50 findings live in the
Debian base layer, where nothing in the Dockerfile can reach them. Running
the container as a non-root user limits what an attacker could do with them;
properly fixing them would mean rebasing onto a distroless image and
rebuilding on a schedule.

The distinction matters more than the count. Seven were fixable and were
fixed; fifty were not, and pretending otherwise would be dishonest.

## D-002: Explicit image tagging in Compose

Compose specifies both `image:` and `build:`, so every build comes out
carrying a real version tag instead of an anonymous project-named one. That
means the container running right now can be traced back to the exact image
that was scanned — which is what makes both rollback and any later
supply-chain question answerable.

## D-003: Exact dependency pinning

Every dependency is pinned to an exact version, so the same image can be
rebuilt identically months from now. The cost is that security patches no
longer arrive on their own. Docker Scout catches outdated packages during
scanning, and the deliberate upgrade-and-retag cycle in D-001 is how they
get applied — but it is a manual step, and worth naming as one.

## D-004: Private key mounting and container user permissions

The JWT signing key is mounted read-only when the container starts, rather
than copied in during the build. A key baked into an image is a key that
leaks the moment the image is pushed anywhere.

The first attempt failed with a `PermissionError`, and the cause turned out
to be two good decisions colliding. OpenSSL generates private keys as `0600`
owned by root. The container deliberately runs as a non-root user. So the
process could not read the file it needed — the least-privilege control
doing exactly what it was put there to do.

Giving the application user a fixed UID and GID and granting group read on
the key resolved it without giving up either non-root execution or the
read-only mount. None of this arises in AWS, where the task pulls the key
from Secrets Manager at launch and it never touches a filesystem at all.

## D-005: RS256 asymmetric token signing

HS256 uses one secret for both signing and verifying. In a system where six
services all need to verify tokens, that means six services all able to
forge them. RS256 splits the two: the User Service holds the private key and
is the only thing that can issue a token, while everyone else verifies using
the public key published at `/.well-known/jwks.json`. No shared secret goes
anywhere.

Tokens carry a `kid` in the header so more than one public key can be
published at once, which is what makes key rotation possible without
invalidating every token already in circulation. Access tokens last fifteen
minutes to keep the damage window small if one is stolen; refresh tokens
last a week. Verification uses an explicit list of permitted algorithms
rather than trusting whatever the token claims — that one line is what
closes off the `alg: none` and algorithm-confusion attacks.

## D-006: Local AWS emulation and third-party dependency risk

LocalStack lets the application call the real AWS SDK against a local
endpoint, so the code that runs in development is the code that runs in
production, give or take one environment variable. That portability was the
whole reason for choosing it.

Then it stopped working. As of the 2026.03 release, LocalStack folded its
free community image into a single authenticated one, and the container
started exiting immediately with a licence error. Registering for the free
non-commercial tier and passing an auth token fixed it, and the image is now
pinned to an explicit version instead of `:latest`.

Worth recording because it is a supply-chain risk in miniature: a third
party changed how its software could be accessed, and a working build broke
without anything in the project changing. Pinning versions limits how often
that can happen, but it cannot prevent it.

## D-007: Idempotency scope

`POST /api/v1/products` is not idempotent, and SKU uniqueness is not enforced
in the datastore. Submitting the same product twice creates two products.
That is a data-quality problem rather than a correctness one, so it was left
alone.

Order creation and payment are a different matter — a duplicate there means
charging someone twice — and both require an idempotency key. The effort went
where non-idempotency actually causes harm. Fixing the catalogue properly
would mean a conditional write against a uniqueness index on `sku`.

## D-008: Redundant identifier in the inventory upsert payload

`PUT /api/v1/inventory/{product_id}` takes `product_id` in the path and again
in the request body, but only ever uses the path value. This surfaced during
testing when a mismatched body silently did nothing, and stock ended up
against the wrong product.

An identifier that appears twice with no check that the two agree lets a
client send a request whose meaning is genuinely ambiguous. The right fix is
to drop it from the request schema, or reject the request with a 400 when
they disagree.

## D-009: Container logs are ephemeral

Log evidence for a transaction disappeared when a service container was
recreated. Docker keeps logs per container instance, not per service, so
replacing a container throws its history away.

This is the argument for centralised log aggregation stated as a fact rather
than a principle: logs have to leave the compute instance as they are
written, because the instance will not be there later. In AWS the ECS
`awslogs` driver streams to CloudWatch Logs, where records outlive the task
and stay queryable across every service at once.

## D-010: PCI-DSS scope minimisation by schema design

The payments table holds an opaque gateway token and the last four digits,
and the last four digits sit in a `varchar(4)`. There is no column capable of
storing a card number, a CVV or an expiry date. A bug in the application
could not persist card data even by accident, because there is nowhere to put
it.

That is a stronger position than a policy of not storing card data, because
it does not depend on anyone remembering the policy. In a real integration
the card number would travel from the browser to the payment provider
directly and never pass through this service at all, which takes it out of
PCI-DSS assessment scope entirely.

## D-011: Test isolation under eventual consistency

An end-to-end test checking an exact stock figure failed intermittently.
Earlier tests in the same run had placed orders whose sagas were still
working through the queue when the assertion ran, so the numbers moved
underneath it.

The system was behaving correctly; the test was wrong. Stock is adjusted by
an asynchronous consumer, so reading it immediately after an API response
tells you nothing about reservations still in flight. Giving the test its own
product fixture fixed it. The same constraint applies to real clients, which
is precisely why they are notified over WebSocket instead of polling for an
answer that may not exist yet.

## D-012: Erasure placeholder broke the user listing endpoint

The GDPR erasure endpoint replaced the user's email with an address on the
`.local` domain. `.local` is reserved by IANA and fails `EmailStr`
validation, so any attempt to serialise an erased record through the response
schema raised an error — and one erased account was enough to make
`GET /api/v1/users` return 500 for everybody.

An automated security test caught it, which manual testing would not have,
because the fault only appears when an erased record happens to be included
in a list response. Switching to `example.com` — also non-routable, but
syntactically valid — resolved it.

## D-013: Data repair required after fixing the erasure defect

Fixing the code did not fix the endpoint. Records written by the broken
version were still sitting in the database, still failing validation, still
returning 500. A migration was needed to repair them.

Obvious in hindsight, but worth stating: once a defect has written bad data,
the code fix only stops it happening again. Everything already written stays
broken until something goes back and corrects it.

## D-014: Scaling comparison invalidated by an unrelated bottleneck

The first attempt at the scalability comparison registered a separate account
for every simulated user. At 200 concurrent users that meant roughly 400
Argon2id hashes running at once, and Argon2id is memory-hard by design.
The User Service buckled — registration took 145 seconds, login 181, and its
health check failed, which meant the scale-up step never even ran.

The measurement was worthless, because the bottleneck had moved somewhere
the test was not looking. Scaling the Order Service could not have shown
anything while the User Service was the thing falling over.

Issuing one shared token at test start removed the hashing entirely, and
dropping to 100 users kept the run below the saturation point the stress test
had already identified. The lesson is that a load profile has to be built
around whatever is being measured; an incidental cost elsewhere will quietly
take over the result.

## D-015: Fixed host port prevented horizontal scaling

The order service published a fixed host port, `8003:8000`. Scaling past one
instance failed immediately with "port is already allocated", because only
one container can bind a given host port. Even if the containers had started,
every client request went to `localhost:8003`, which resolves to exactly one
of them — so there would have been no distribution regardless.

Removing the published port and putting nginx in front as a load balancer
fixed it, using Docker's embedded DNS to find every instance of the service.

This is the same reason fixed host ports are unusable in container
orchestration generally, and why ECS and Kubernetes assign ports dynamically
and register targets with a load balancer instead of publishing them
directly. The local problem and the production design turn out to have the
same cause.

## D-016: Connection pool capacity confirmed as the scaling constraint

Scaling the Order Service from one instance to three behind nginx took
throughput from 3.5 to 72.6 requests per second and dropped the failure rate
from 35.2% to zero.

A twentyfold gain from tripling the instances should not be possible, and the
fact that it happened says the single-instance run was not slow but
saturated. Blocked requests were holding database connections for the full
60-second gateway timeout, so most of the capacity was being spent on
requests that would never complete.

The endpoints using the PostgreSQL pool improved by 98–99.9%. DynamoDB reads,
which were never the problem, got 80–97% *worse* at p95 — because the system
was now processing twenty times more traffic on the same host. That confirms
what the stress test suggested, and identifies the next constraint as shared
host CPU rather than application concurrency.

## D-017: Endpoint configuration prevented deployment to real AWS

The catalogue service always passed `endpoint_url` to boto3, and its default
pointed at LocalStack. In AWS there is no host by that name, so the container
died during startup and ECS kept restarting it — four stopped tasks before
the cause became clear, with uvicorn exiting 3 each time.

Passing `endpoint_url` only when it is explicitly set fixed it, letting boto3
resolve the regional endpoint on its own. The same image now runs against
LocalStack locally and managed AWS services in deployment, differing by one
environment variable.

Only deploying found this. Local emulation had validated every SDK call
correctly, but never exercised the configuration path that production
actually uses — which is a fair summary of what emulation can and cannot
prove.

## D-018: Incomplete stored item surfaced as a 500 rather than a 422

An item written directly into DynamoDB via the CLI left out five fields the
response schema requires. Reading it back returned a 500 with no useful
message, and the actual cause — five missing fields — was only visible in
CloudWatch Logs.

DynamoDB accepted the item quite happily, because a schemaless store has no
opinion about what an item should contain. Validation only happens when the
application tries to serialise it, so bad data is caught on read rather than
on write.

That is the real trade-off in schemaless storage: the flexibility is genuine,
but the integrity burden moves entirely to the application. A production
system would validate on the way in and treat an unserialisable stored record
as a defect requiring data repair — which is exactly what happened with the
erasure placeholder in D-012, arriving at the same conclusion from a
different direction.
