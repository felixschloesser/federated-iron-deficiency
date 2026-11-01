Feature: Collecting a sample and ordering tests on it
  A general practitioner collects a sample from one of their patients, then
  orders tests on it: blood is drawn into the standard tubes first and the tests
  are chosen afterwards (a simplification of WHO LQMS 5-3, where the request
  comes first). The order carries only what the lab needs: the sample ID, the
  test, the clinical indication, registered sex and age. Covers R1, R26.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32
    And "Dr. Demo A" collected a sample from "Test Patient 1"

  Scenario: A CBC order records the indication and copies sex and age
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then the order has test CBC and indication unexplained fatigue
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

  Scenario: A collected sample gets the patient's next sample ID
    Then the sample is sample 1 of "Test Patient 1", collected at the current time

  Scenario: A patient can give several samples
    When "Dr. Demo A" collects a sample from "Test Patient 1"
    Then the sample is sample 2 of "Test Patient 1", collected at the current time

  Scenario: Several tests go on one sample
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order is on sample 1 of "Test Patient 1"

  Scenario: A test the sample already has is refused
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then the order is refused with code "already_ordered" on field "test"
