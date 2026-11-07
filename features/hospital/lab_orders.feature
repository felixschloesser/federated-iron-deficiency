Feature: Lab orders in, lab reports out, practice by practice
  The hospital records the lab orders (DF23) of each practice it works with,
  known by the certificate name it issued, and lets each practice fetch the lab
  reports (DF25) of its own lab orders until the practice acknowledges them.
  The gRPC endpoint that carries both is tested in tests/hospital/test_messaging.py.

  Background:
    Given hospital "AZ Diest" knows practices "de-ceder" and "de-berk"

  Scenario: The same lab order received twice is recorded once
    Given practice "de-ceder" sent a lab order for a CBC on sample "1-1"
    When practice "de-ceder" sends a lab order for a CBC on sample "1-1"
    Then "AZ Diest" has one test request on sample "1-1"

  Scenario: The same sample ID from two practices is two samples
    Given practice "de-ceder" sent a lab order for a CBC on sample "1-1"
    When practice "de-berk" sends a lab order for a CBC on sample "1-1"
    Then "AZ Diest" has two samples with sample ID "1-1"

  Scenario: A lab order not yet analysed has no lab report to fetch
    Given practice "de-ceder" sent a lab order for a CBC on sample "1-1"
    Then practice "de-ceder" fetches no lab reports

  Scenario: A practice fetches the lab reports of its own lab orders only
    Given "AZ Diest" released a lab report on sample "1-1" of practice "de-ceder"
    Then practice "de-ceder" fetches the lab report on sample "1-1"
    And practice "de-berk" fetches no lab reports

  Scenario: An acknowledged lab report is fetched no more
    Given "AZ Diest" released a lab report on sample "1-1" of practice "de-ceder"
    When practice "de-ceder" acknowledges the lab report on sample "1-1"
    Then practice "de-ceder" fetches no lab reports

  Scenario: A practice cannot acknowledge another practice's lab report
    Given "AZ Diest" released a lab report on sample "1-1" of practice "de-ceder"
    When practice "de-berk" acknowledges the lab report on sample "1-1"
    Then practice "de-ceder" fetches the lab report on sample "1-1"
