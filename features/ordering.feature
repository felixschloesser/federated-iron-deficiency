Feature: Ordering a test
  A GP orders one test for one of their patients. The order carries only what
  the lab needs: the test, the clinical indication, registered sex and age.
  Covers R1.

  Background:
    Given GP "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32

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
