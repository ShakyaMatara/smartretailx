# Performance testing — SmartRetailX

## Where the files go

Copy the whole `perf/` folder into the project root:

    smartretailx/
      perf/
        locustfile.py
        compare.py
        run-tests.ps1
        run-scaling.ps1
        requirements-perf.txt
        results/          (created on first run)

Add to .gitignore:

    perf/results/

## Setup

    pip install -r perf/requirements-perf.txt

## Before running

  - All containers healthy:            docker compose ps
  - Payment NOT in failure mode:       docker compose exec payment-service printenv FORCE_PAYMENT_FAILURE
  - Close other heavy applications. Results are only comparable if the
    machine is in a similar state across runs.

## The four required scenarios

    .\perf\run-tests.ps1

Runs, in order:
  1. Baseline      10 users,  1 min, health endpoint only  -> latency floor
  2. Load test    100 users,  5 min, mixed traffic         -> the headline result
  3. API test      50 users,  3 min, browsing only         -> per-endpoint latency
  4. Stress test  500 users,  6 min, mixed traffic         -> breaking point

Total run time about 15 minutes. Reports land in perf\results\ as both
CSV and HTML. The HTML files contain the charts.

## The scalability comparison

    .\perf\run-scaling.ps1

Runs identical load (200 users, 4 min) against 1 instance and then 3
instances of the order service, scaled with Docker Compose. Takes about
10 minutes.

Then produce the comparison table:

    python perf/compare.py

## Watching resource use

In a second terminal during any run:

    docker stats

Screenshot it mid-run at peak load.

## Evidence to capture

  evidence/06-performance/06-01-load-test-charts.png      02-load.html, charts section
  evidence/06-performance/06-02-load-test-stats.png       02-load.html, statistics table
  evidence/06-performance/06-03-stress-test-charts.png    04-stress.html
  evidence/06-performance/06-04-scaling-1x.png            05-scale-1x.html
  evidence/06-performance/06-05-scaling-3x.png            06-scale-3x.html
  evidence/06-performance/06-06-scaling-comparison.png    output of compare.py
  evidence/06-performance/06-07-docker-stats.png          docker stats at peak

## Interpreting the results

The numbers alone earn few marks. The analysis earns them. For each run
be ready to state:

  - Where the bottleneck was. Usually the database connection pool or a
    synchronous call that should have been asynchronous. Correlate the
    latency curve against docker stats CPU and memory.
  - Why POST /orders is slower than GET /products. It performs a
    synchronous HTTP call to the catalogue service, writes to PostgreSQL,
    and publishes to SNS, whereas the catalogue read is a single indexed
    DynamoDB lookup.
  - What the stress test revealed. Find the concurrency level at which
    the error rate first rises and latency degrades sharply.
  - Whether tripling instances tripled throughput. It will not have. Say
    why: the shared database, the single host, and container contention
    for the same CPU cores.

## Known limitations to state in the report

  - Load generator and system under test share one machine, so they
    compete for CPU. Absolute figures understate real capacity.
  - No network latency simulation; all traffic is over the loopback
    interface.
  - LocalStack emulates SNS and SQS; performance characteristics differ
    from managed AWS services.
  - Scaling was tested to three instances only, and all three ran on the
    same host.
