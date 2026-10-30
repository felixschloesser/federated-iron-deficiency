Feature: Lab orders and lab reports between the general practitioner and the hospital
  The general practitioner's own app sends lab orders (DF1) to its one
  hospital and fetches lab reports (DF20) from it, over gRPC with mutual TLS.
  The hospital accepts only the client certificate its own certificate
  authority issued to that general practitioner's app. Covers R22–R25.

  Background:
    Given hospital "AZ Diest" with its certificate authority
    And general practitioner "Dr. Demo A" of practice "De Ceder", with a client certificate from "AZ Diest"
    And patient "Test Patient 1" of "Dr. Demo A", registered sex female, aged 32

  Scenario: A placed order reaches the hospital
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication non-specific complaint
    Then "AZ Diest" has a lab order for the sample of "Test Patient 1"
    And the lab order holds sample ID, test, clinical indication, registered sex, age and "Dr. Demo A"

  Scenario: The same lab order sent twice is recorded once
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When the same lab order is sent again
    Then "AZ Diest" has one lab order for the sample of "Test Patient 1"

  Scenario Outline: A client the hospital did not certify is refused
    Given a client with <certificate>
    When it sends a lab order to "AZ Diest"
    Then the connection is refused
    And "AZ Diest" has no lab order from it

    Examples:
      | certificate                                    |
      | no certificate                                 |
      | a certificate from another hospital's authority |
      | a certificate from the startup's authority      |

  Scenario: The general practitioner's app fetches its lab reports
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has the lab report of "Test Patient 1"

  Scenario: A lab report is fetched once
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And the general practitioner's app checked for lab reports
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has one lab report of "Test Patient 1"

  Scenario: Neither message can carry a name or blood values
    Then the lab order has no field for a patient's name or blood values
    And the lab report has no field for a score or a screening result
