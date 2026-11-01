Feature: Who sees what
  A general practitioner sees only their own patients; the lab never learns a patient's name;
  demo login exists only in development. Covers R13–R15. A lab report shows only
  on its patient's page, so another general practitioner's lab report is as
  unreachable as their patient (view tests: tests/test_practice_views.py).

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"
    And general practitioner "Dr. Demo B" with patient "Test Patient 2"

  Scenario: A general practitioner cannot order for another general practitioner's patient
    When "Dr. Demo A" orders a CBC for "Test Patient 2" with indication other
    Then the order is refused with code "not_your_patient" on field "patient"

  Scenario: The lab never sees a patient's name
    Given a CBC order for "Test Patient 1"
    Then the lab's samples hold sample ID, ordering general practitioner, registered sex, age, test, indication and results
    And no lab query returns the patient's name

  Scenario: Demo login buttons when enabled
    Given DEMO_LOGIN is on
    When the login page is shown
    Then it offers one login button per seeded user

  Scenario: No demo login by default
    Given DEMO_LOGIN is off
    Then logging in as a seeded user without a password is refused

  Scenario: Demo login fails the deploy check
    Given DEMO_LOGIN is on and DEBUG is off
    When the deploy check runs
    Then it reports an error
