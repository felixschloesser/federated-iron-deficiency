Feature: The hospital's lab-order endpoint
  The hospital receives lab orders (DF23) from the practices it works with and
  hands each practice the lab reports (DF25) of its own lab orders, over gRPC.
  Every message names the sending practice by the certificate name the hospital
  issued it; the hospital refuses a practice it does not know. The report's
  mutual TLS, which would take the certificate name from the connection, is
  left out of the demo. The general practitioner's side is in
  features/practice/messaging.feature.

  Background:
    Given hospital "AZ Diest"
    And "AZ Diest" knows practice "De Ceder" by certificate name "de-ceder"

  Scenario: A lab order reaches the hospital
    When practice "de-ceder" sends a lab order for a CBC on sample "1-1", indication screened, registered sex female, aged 32
    Then "AZ Diest" has a lab order for sample "1-1"
    And the lab order holds sample ID, test, whether its indication is screened, registered sex and age, from certificate name "de-ceder"

  Scenario: The hospital stores no clinical indication
    When practice "de-ceder" sends a lab order for a CBC on sample "1-1", indication screened, registered sex female, aged 32
    Then no lab order names a clinical indication

  Scenario: The same lab order sent twice is recorded once
    Given practice "de-ceder" sent a lab order for a CBC on sample "1-1", indication not screened, registered sex female, aged 32
    When practice "de-ceder" sends a lab order for a CBC on sample "1-1", indication not screened, registered sex female, aged 32
    Then "AZ Diest" has one lab order for sample "1-1"

  Scenario: A lab order that names no practice is refused
    When a lab order that names no practice is sent to "AZ Diest"
    Then it is refused as practice required
    And "AZ Diest" has no lab order

  Scenario: A lab order from a practice the hospital does not know is refused
    When practice "de-linde", which "AZ Diest" does not know, sends a lab order
    Then it is refused as unknown practice
    And "AZ Diest" has no lab order

  Scenario: A practice fetches the lab reports of its lab orders
    Given "AZ Diest" released a ferritin lab report on sample "1-1" of practice "de-ceder"
    When practice "de-ceder" fetches its new lab reports
    Then it receives the lab report on sample "1-1"

  Scenario: A lab report says whether ferritin is suggested
    Given "AZ Diest" released a CBC lab report with ferritin suggested on sample "1-1" of practice "de-ceder"
    When practice "de-ceder" fetches its new lab reports
    Then the lab report on sample "1-1" has ferritin suggested

  Scenario: An acknowledged lab report is handed out no more
    Given "AZ Diest" released a ferritin lab report on sample "1-1" of practice "de-ceder"
    And practice "de-ceder" acknowledged the lab report on sample "1-1"
    When practice "de-ceder" fetches its new lab reports
    Then it receives no lab reports

  Scenario: Another practice gets none of these lab reports
    Given "AZ Diest" released a ferritin lab report on sample "1-1" of practice "de-ceder"
    And "AZ Diest" knows practice "De Berk" by certificate name "de-berk"
    When practice "de-berk" fetches its new lab reports
    Then it receives no lab reports
    And the lab report on sample "1-1" is still new at "AZ Diest"

  Scenario: Another practice cannot acknowledge these lab reports
    Given "AZ Diest" released a ferritin lab report on sample "1-1" of practice "de-ceder"
    And "AZ Diest" knows practice "De Berk" by certificate name "de-berk"
    When practice "de-berk" acknowledges the lab report on sample "1-1"
    Then the lab report on sample "1-1" is still new at "AZ Diest"

  Scenario: The same sample ID from two practices is two samples
    Given "AZ Diest" knows practice "De Berk" by certificate name "de-berk"
    And practice "de-ceder" sent a lab order for a CBC on sample "1-1", indication not screened, registered sex female, aged 32
    When practice "de-berk" sends a lab order for a CBC on sample "1-1", indication not screened, registered sex female, aged 32
    Then "AZ Diest" has two samples with sample ID "1-1"

  Scenario: Neither message can carry a name or blood values
    Then the lab order has no field for a patient's name or blood values, only the practice's certificate name
    And the lab report says only whether ferritin is suggested, nothing else of screening
