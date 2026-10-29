Feature: Who sees what
  A general practitioner sees only their own patients; the lab never learns a patient's name;
  demo login exists only in development. Covers R13–R15.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"
    And general practitioner "Dr. Demo B" with patient "Test Patient 2"

  Scenario: A general practitioner sees only their own lab reports
    Given lab reports for "Test Patient 1" and "Test Patient 2"
    Then "Dr. Demo A"'s lab reports contain only the one for "Test Patient 1"

  Scenario: A general practitioner cannot open another general practitioner's lab report
    Given a lab report for "Test Patient 2"
    When "Dr. Demo A" opens that lab report
    Then it is not found

  Scenario: A general practitioner cannot order for another general practitioner's patient
    When "Dr. Demo A" orders a CBC for "Test Patient 2" with indication other
    Then the order is refused with code "not_your_patient" on field "patient"

  Scenario: A general practitioner cannot mark another general practitioner's lab report as read
    Given an unread lab report for "Test Patient 2"
    When "Dr. Demo A" marks that lab report as read
    Then it is not found

  Scenario: The lab never sees a patient's name
    Given a received CBC sample for "Test Patient 1"
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
