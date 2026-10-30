Feature: Lab reports for the general practitioner
  The general practitioner reads a lab report on the patient's page: the
  values under NHANES's names and units, no interpretation, a comment only when
  ferritin is suggested, and Order ferritin beside that comment. Covers R9, R11,
  R12.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: A CBC lab report shows the 13 values with their names and units
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then the lab report shows "Hemoglobin" in "g/dL" with the analyser's value
    And the lab report shows 13 values in the order of the CBC

  Scenario: Ferritin suggested shows the comment
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then the lab report's comment is "Ferritin suggested."

  Scenario: Without a suggestion the lab report says nothing about screening
    Given a CBC lab report for "Test Patient 1" without ferritin suggested
    Then the lab report has no comment

  Scenario: Order ferritin is offered beside the suggestion
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then ordering ferritin is offered on the lab report

  Scenario: Order ferritin is not offered once ferritin was ordered
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    And a ferritin order for "Test Patient 1"
    Then ordering ferritin is not offered on the lab report

  Scenario: Order ferritin is not offered without a suggestion
    Given a CBC lab report for "Test Patient 1" without ferritin suggested
    Then ordering ferritin is not offered on the lab report

  Scenario: A ferritin lab report shows ferritin in ng/mL
    Given a ferritin lab report for "Test Patient 1" with ferritin 12 ng/mL
    Then the lab report shows "Ferritin" in "ng/mL" with the analyser's value
    And the lab report has no comment
    And ordering ferritin is not offered on the lab report

  Scenario: Ferritin that NHANES does not have
    Given a ferritin lab report for "Test Patient 1" without a value
    Then the lab report shows no values
