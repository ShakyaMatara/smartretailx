# API testing with Postman / Newman

## Files

    postman/
      SmartRetailX.postman_collection.json    32 requests, 68 assertions
      SmartRetailX.postman_environment.json   base URLs and admin credentials
      run-newman.ps1                          headless runner
      results/                                generated reports (gitignore this)

## One-time setup

    npm install -g newman newman-reporter-htmlextra

## Before running

  - All containers healthy:   docker compose ps
  - Payment not forced to fail:
        docker compose exec payment-service printenv FORCE_PAYMENT_FAILURE
    must print false.

If your admin account differs from shakya@example.com, edit
`admin_email` and `admin_password` in the environment file.

## Run

    .\postman\run-newman.ps1

## Structure

The five folders run in order and depend on one another:

  1 Setup          authenticates as administrator and customer, creates a
                   product and stocks it. Stores tokens and identifiers as
                   collection variables for the folders that follow.
  2 Functional     core behaviour: profile, catalogue browsing, category
                   filtering, stock check, order placement, order listing.
  3 Security       missing and malformed tokens, RBAC refusals, account
                   enumeration resistance, JWKS publication.
  4 API contract   status-code semantics (409, 422, 404), mandatory
                   idempotency key, pagination bounds, version prefixing.
  5 Health         readiness and response time for all six services.

Because later folders consume variables set by Setup, the collection
must be run as a whole. Running an individual request in the Postman GUI
will fail with unresolved variables unless Setup has run first in the
same session.

## Using the GUI instead

Import both JSON files into Postman, select the "SmartRetailX Local"
environment, then use Runner on the whole collection.

## Evidence to capture

  evidence/08-testing/08-05-newman-cli-summary.png    terminal summary table
  evidence/08-testing/08-06-newman-html-report.png    newman-report.html
