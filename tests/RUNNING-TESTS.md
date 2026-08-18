# Running the SmartRetailX test suite

## Where the files go

Copy the `tests/` folder and `pytest.ini` into the project root:

    smartretailx/
      pytest.ini          <-- new
      tests/              <-- new
        conftest.py
        requirements-test.txt
        unit/  integration/  api/  e2e/  security/
      services/
      shared/
      keys/

## One-time setup

With the virtual environment active, from the project root:

    pip install -r tests/requirements-test.txt

## Before running

The Docker Compose stack must be up and every container healthy:

    docker compose up -d
    docker compose ps

The suite also needs an account holding the `admin` role. It defaults to
`shakya@example.com` / `CorrectHorseBattery`. If yours differs, set:

    $env:ADMIN_EMAIL="your@email.com"
    $env:ADMIN_PASSWORD="YourPassword"

Also confirm the payment service is NOT in forced-failure mode, or the
end-to-end tests will fail by design:

    docker compose exec payment-service printenv FORCE_PAYMENT_FAILURE
    # must print: false

## Running

Everything:

    pytest

By layer:

    pytest -m unit
    pytest -m integration
    pytest -m api
    pytest -m e2e
    pytest -m security

## Coverage (for the report)

    pytest -m unit --cov=services/user-service --cov-report=term --cov-report=html

Open `htmlcov/index.html` for the browsable report.

Note honestly in the report that coverage is measured only over the
modules exercised in-process by the unit tests. The integration, API,
end-to-end and security tests exercise code running inside containers,
which the coverage instrument does not observe. Those layers are
evidenced by test counts and results rather than by line coverage.

## Evidence to capture

  evidence/08-testing/08-01-pytest-full-run.png       full run summary
  evidence/08-testing/08-02-coverage-report.png       htmlcov/index.html
  evidence/08-testing/08-03-security-tests.png        pytest -m security
  evidence/08-testing/08-04-e2e-saga-tests.png        pytest -m e2e

For a clean summary screenshot:

    pytest --tb=no -q

## If the e2e tests time out

The saga is asynchronous and the tests poll for up to 25 seconds. On a
slow machine, raise `SAGA_TIMEOUT` at the top of
`tests/e2e/test_order_saga.py`.
