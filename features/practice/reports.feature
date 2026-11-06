Feature: Lab reports for the general practitioner
  The general practitioner reads a lab report on the patient's page: the
  values under NHANES's names and units, no interpretation, a comment only when
  ferritin is suggested, and Order ferritin beside that comment.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: A CBC lab report shows the 13 values with their names and units
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then the lab report shows "Hemoglobin" in "g/dL" with the analyser's value
    And the lab report shows 13 values in the order of the CBC

  Scenario: Ferritin suggested shows the comment
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then the lab report's comment is "Ferritin suggested by the hospital's screening of this CBC. Likely iron deficiency; not a diagnosis."

  Scenario: Without a suggestion the lab report says nothing about screening
    Given a CBC lab report for "Test Patient 1" without ferritin suggested
    Then the lab report has no comment
    And the lab report's note is "No ferritin suggestion. This does not rule out iron deficiency."

  Scenario: A patient is marked ferritin suggested until ferritin is ordered
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then "Test Patient 1" is marked ferritin suggested
    When ferritin is ordered on the lab report's sample
    Then "Test Patient 1" is not marked ferritin suggested

  Scenario: Order ferritin is offered beside the suggestion
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    Then ordering ferritin is offered on the lab report

  Scenario: Order ferritin is not offered once its sample has ferritin
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    And a ferritin order on the lab report's sample
    Then ordering ferritin is not offered on the lab report

  Scenario: Ferritin on another sample still offers Order ferritin
    Given a CBC lab report for "Test Patient 1" with ferritin suggested
    And a ferritin order for "Test Patient 1"
    Then ordering ferritin is offered on the lab report

  Scenario: Order ferritin is not offered without a suggestion
    Given a CBC lab report for "Test Patient 1" without ferritin suggested
    Then ordering ferritin is not offered on the lab report

  Scenario: A ferritin lab report shows ferritin in ng/mL
    Given a ferritin lab report for "Test Patient 1" with ferritin 12 ng/mL
    Then the lab report shows "Ferritin" in "ng/mL" with the analyser's value
    And the lab report has no comment
    And the lab report has no note
    And ordering ferritin is not offered on the lab report

  Scenario: Ferritin that NHANES does not have
    Given a ferritin lab report for "Test Patient 1" without a value
    Then the lab report shows no values
