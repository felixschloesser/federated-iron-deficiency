Feature: Who sees what
  A practice has one general practitioner. That the lab never learns a patient's
  name is in lab.feature and hospital/messaging.feature.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: A practice has one general practitioner
    When general practitioner "Dr. Demo B" is added to the practice
    Then adding them is refused with code "one_general_practitioner"
    And the database refuses it
