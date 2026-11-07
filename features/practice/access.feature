Feature: Who sees what
  A practice has one general practitioner, and only the practice's roles log in to
  its web app: an account whose role is another party's has no role here. That the lab never learns a patient's
  name is in features/hospital/lab.feature and tests/tools/test_messages.py.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: A practice has one general practitioner
    When general practitioner "Dr. Demo B" is added to the practice
    Then adding them is refused with code "one_general_practitioner"
    And the database refuses it

  Scenario: An account whose role is another party's cannot log in here
    Given an account "staff" of laboratory staff
    When "staff" logs in to the practice's web app
    Then logging in is refused with code "no_role"
