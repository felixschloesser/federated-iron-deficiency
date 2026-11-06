Feature: The general practitioner's app sends lab orders and fetches lab reports
  The general practitioner's own app sends lab orders (DF23) to the laboratory
  chosen for each sample, any hospital's, and fetches lab reports (DF25) from
  each hospital it works with, over gRPC. Every message names the practice by
  the certificate name the hospital issued it. Here the hospital is a stand-in
  that keeps to features/hospital/messaging.feature: it records what it is
  sent and hands out the lab reports it was given until they are acknowledged.

  Background:
    Given hospital "AZ Diest"
    And general practitioner "Dr. Demo A" of practice "De Ceder", working with "AZ Diest"
    And "AZ Diest" issued the practice certificate name "de-ceder"
    And patient "Test Patient 1" of "Dr. Demo A", registered sex female, aged 32

  Scenario: A placed order reaches the hospital
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then "AZ Diest" received a lab order for the sample of "Test Patient 1"
    And the lab order holds sample ID, test, whether its indication is screened, registered sex and age, from certificate name "de-ceder"

  Scenario Outline: The lab order says only whether the indication is screened, never which
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication <indication>
    Then the lab order says its indication is <screened>

    Examples:
      | indication                         | screened     |
      | suspected anaemia                  | screened     |
      | suspected irritable bowel syndrome | screened     |
      | unexplained fatigue                | screened     |
      | start of pregnancy                 | not screened |
      | chronic kidney disease follow-up   | not screened |
      | other                              | not screened |

  Scenario: The general practitioner's app fetches its lab reports
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has the lab report of "Test Patient 1"
    And the lab report of "Test Patient 1" is no longer new at "AZ Diest"

  Scenario: A suggestion of ferritin reaches the general practitioner
    Given "AZ Diest" released a CBC lab report with ferritin suggested for the sample of "Test Patient 1"
    When the general practitioner's app checks for lab reports
    Then the lab report of "Test Patient 1" has ferritin suggested at "Dr. Demo A"

  Scenario: A lab report is fetched once
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And the general practitioner's app checked for lab reports
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has one lab report of "Test Patient 1"

  Scenario: A lab report the app cannot match does not block the others
    Given "AZ Diest" released a lab report for the sample of "Test Patient 1"
    And "AZ Diest" released a lab report for a sample "Dr. Demo A" never ordered
    When the general practitioner's app checks for lab reports
    Then "Dr. Demo A" has the lab report of "Test Patient 1"
    And the lab report of "Test Patient 1" is no longer new at "AZ Diest"
    And the lab report for the sample never ordered is still new at "AZ Diest"
