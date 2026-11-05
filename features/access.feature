Feature: Who sees what
  A practice has one general practitioner; the lab never learns a patient's name.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: A practice has one general practitioner
    When general practitioner "Dr. Demo B" is added to the practice
    Then adding them is refused with code "one_general_practitioner"
    And the database refuses it

  Scenario: The lab never sees a patient's name
    Given a CBC order for "Test Patient 1"
    Then the lab's samples hold sample ID, registered sex, age, test, whether the indication is screened and results, and no general practitioner
    And no lab query returns the patient's name
