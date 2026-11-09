Feature: Lab orders in, lab reports out, practice by practice
  The hospital records the lab orders (DF23) of each practice it works with,
  known by its name, and lets each practice fetch the lab
  reports (DF25) of its own lab orders until the practice acknowledges them.
  The gRPC endpoint that carries both is tested in tests/hospital/test_messaging.py.

  Background:
    Given hospital "AZ Diest" knows practices "De Ceder" and "De Berk"

  Scenario: The same lab order received twice is recorded once
    Given practice "De Ceder" sent a lab order for a CBC on sample "135318"
    When practice "De Ceder" sends a lab order for a CBC on sample "135318"
    Then "AZ Diest" has one test request on sample "135318"

  Scenario: The same sample ID from two practices is two samples
    Given practice "De Ceder" sent a lab order for a CBC on sample "135318"
    When practice "De Berk" sends a lab order for a CBC on sample "135318"
    Then "AZ Diest" has two samples with sample ID "135318"

  Scenario: A lab order not yet analysed has no lab report to fetch
    Given practice "De Ceder" sent a lab order for a CBC on sample "135318"
    Then practice "De Ceder" fetches no lab reports

  Scenario: A practice fetches the lab reports of its own lab orders only
    Given "AZ Diest" released a lab report on sample "135318" of practice "De Ceder"
    Then practice "De Ceder" fetches the lab report on sample "135318"
    And practice "De Berk" fetches no lab reports

  Scenario: An acknowledged lab report is fetched no more
    Given "AZ Diest" released a lab report on sample "135318" of practice "De Ceder"
    When practice "De Ceder" acknowledges the lab report on sample "135318"
    Then practice "De Ceder" fetches no lab reports

  Scenario: A practice cannot acknowledge another practice's lab report
    Given "AZ Diest" released a lab report on sample "135318" of practice "De Ceder"
    When practice "De Berk" acknowledges the lab report on sample "135318"
    Then practice "De Ceder" fetches the lab report on sample "135318"

  Scenario: An acknowledgement naming one lab report twice is refused
    Given "AZ Diest" released a lab report on sample "135318" of practice "De Ceder"
    When practice "De Ceder" acknowledges the lab report on sample "135318" twice
    Then acknowledging is refused as naming a lab report twice
    And practice "De Ceder" fetches the lab report on sample "135318"

  Scenario: A practice whose name makes a registered practice's slug is refused
    When hospital "AZ Diest" registers practice "De-Ceder"
    Then registering is refused as a slug taken
