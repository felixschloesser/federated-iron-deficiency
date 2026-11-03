Feature: Lab orders and lab reports between the general practitioner and the hospital
  The general practitioner's own app sends lab orders (DF23) to its one
  hospital and fetches lab reports (DF25) from it, over gRPC with mutual TLS.
  The hospital accepts only the client certificate its own certificate
  authority issued to that general practitioner's app, and gives each app
  only the lab reports of its own lab orders. Covers R22–R25.

  Background:
    Given hospital "AZ Diest" with its certificate authority
    And general practitioner "Dr. Demo A" of practice "De Ceder", with a client certificate from "AZ Diest"
    And patient "Test Patient 1" of "Dr. Demo A", registered sex female, aged 32

  Scenario: A placed order reaches the hospital
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then "AZ Diest" has a lab order for the sample of "Test Patient 1"
    And the lab order holds sample ID, test, whether its indication is screened, registered sex, age and "Dr. Demo A"

  Scenario Outline: The lab order says only whether the indication is screened, never which
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication <indication>
    Then the lab order says its indication is <screened>
    And no lab order names a clinical indication

    Examples:
      | indication                         | screened     |
      | suspected anaemia                  | screened     |
      | suspected irritable bowel syndrome | screened     |
      | unexplained fatigue                | screened     |
      | start of pregnancy                 | not screened |
      | chronic kidney disease follow-up   | not screened |
      | other                              | not screened |

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

  Scenario: A suggestion of ferritin reaches the general practitioner
    Given "AZ Diest" released a CBC lab report with ferritin suggested for the sample of "Test Patient 1"
    When the general practitioner's app checks for lab reports
    Then the lab report of "Test Patient 1" has ferritin suggested at "Dr. Demo A"

  Scenario: A lab report is fetched once
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And the general practitioner's app checked for lab reports
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has one lab report of "Test Patient 1"

  Scenario: Another general practitioner's app of the same hospital gets none of these lab reports
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And another general practitioner's app with a client certificate from "AZ Diest"
    When the other app checks for lab reports
    Then it receives no lab reports
    And the lab report of "Test Patient 1" is still new at "AZ Diest"

  Scenario: Another general practitioner's app cannot acknowledge these lab reports
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And another general practitioner's app with a client certificate from "AZ Diest"
    When the other app acknowledges the lab report of "Test Patient 1"
    Then the lab report of "Test Patient 1" is still new at "AZ Diest"

  Scenario: The same sample ID from two apps is two samples
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    And another general practitioner's app with a client certificate from "AZ Diest"
    When the other app sends a lab order with the sample ID of "Test Patient 1"
    Then "AZ Diest" has two samples with the sample ID of "Test Patient 1"

  Scenario: A lab report the app cannot match does not block the others
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And "AZ Diest" released a lab report for a sample "Dr. Demo A" never ordered
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has the lab report of "Test Patient 1"
    And the lab report of "Test Patient 1" is no longer new at "AZ Diest"

  Scenario: Neither message can carry a name or blood values
    Then the lab order has no field for a patient's name or blood values
    And the lab report says only whether ferritin is suggested, nothing else of screening
