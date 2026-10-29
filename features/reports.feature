Feature: Lab reports for the general practitioner
  The general practitioner sees the results of their own orders, a comment only when ferritin is
  suggested, and can order ferritin from such a report. Covers R9–R11.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1"

  Scenario: Ferritin suggested shows the comment
    Given a lab report for "Test Patient 1" with result "ferritin suggested"
    Then the lab report shows the CBC values
    And the lab report shows the comment suggesting ferritin

  Scenario Outline: No word about screening otherwise
    Given a lab report for "Test Patient 1" with result "<result>"
    Then the lab report shows the CBC values
    And the lab report shows no comment and no screening result

    Examples:
      | result                 |
      | ferritin not suggested |
      | not screened           |

  Scenario: A new lab report is unread
    Given a lab report for "Test Patient 1" that has just become visible
    Then the lab report is unread in "Dr. Demo A"'s lab reports

  Scenario: Marking a lab report as read
    Given an unread lab report for "Test Patient 1"
    When "Dr. Demo A" marks the lab report as read
    Then the lab report is read at the current time

  Scenario: Order ferritin is offered when ferritin is suggested
    Given a lab report for "Test Patient 1" with result "ferritin suggested"
    And no ferritin order for "Test Patient 1" after that order
    Then ordering ferritin is offered on the lab report

  Scenario: Order ferritin is not offered once ferritin was ordered
    Given a lab report for "Test Patient 1" with result "ferritin suggested"
    And a ferritin order for "Test Patient 1" after that order
    Then ordering ferritin is not offered on the lab report

  Scenario Outline: Order ferritin is not offered without a suggestion
    Given a lab report for "Test Patient 1" with result "<result>"
    Then ordering ferritin is not offered on the lab report

    Examples:
      | result                 |
      | ferritin not suggested |
      | not screened           |
