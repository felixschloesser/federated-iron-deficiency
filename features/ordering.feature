Feature: Ordering a test
  A general practitioner orders one test for one of their patients, on a newly
  collected sample or on one the laboratory holds. The order carries only what
  the lab needs: the sample ID, the test, the clinical indication, registered sex
  and age. Covers R1, R26.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32

  Scenario: A CBC order records the indication and copies sex and age
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication non-specific complaint
    Then the order has test CBC and indication non-specific complaint
    And the order has registered sex female and age 32

  Scenario: A CBC order without an indication is refused
    When "Dr. Demo A" orders a CBC for "Test Patient 1" without an indication
    Then the order is refused with code "indication_required" on field "indication"

  Scenario: A ferritin order has no indication
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order has test ferritin and no indication

  Scenario: A ferritin order with an indication is refused
    When "Dr. Demo A" orders ferritin for "Test Patient 1" with indication other
    Then the order is refused with code "indication_not_applicable" on field "indication"

  Scenario: An order collects a new sample with its own sample ID
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication non-specific complaint
    Then the order is on sample 1 of "Test Patient 1", collected at the current time

  Scenario: A second CBC collects another sample
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication non-specific complaint
    Then the order is on sample 2 of "Test Patient 1", collected at the current time

  Scenario: Ferritin on the CBC's sample goes to the same sample
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders ferritin on that CBC's sample
    Then the order is on sample 1 of "Test Patient 1"

  Scenario: A test the sample already has is refused
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders a CBC on that CBC's sample with indication non-specific complaint
    Then the order is refused with code "already_ordered" on field "test"
