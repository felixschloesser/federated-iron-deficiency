Feature: Receiving and analysing samples
  Laboratory staff receive each order's sample and run the analyser, which
  returns the patient's NHANES 2021–2023 values. Covers R2, R3, R12.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32
    And "Test Patient 1" has NHANES CBC values and ferritin 11.0 ng/mL

  Scenario: Receiving an order assigns a sample ID
    Given a CBC order for "Test Patient 1"
    When laboratory staff receive the order
    Then the order has a sample with a sample ID, received at the current time

  Scenario: An order is received only once
    Given a CBC order for "Test Patient 1" that has been received
    When laboratory staff receive the order
    Then receiving is refused with code "already_received"

  Scenario: Running the analyser records the patient's CBC
    Given a received CBC sample for "Test Patient 1"
    When laboratory staff run the analyser
    Then the sample has the 13 NHANES CBC values of "Test Patient 1"

  Scenario: A sample is analysed only once
    Given an analysed CBC sample for "Test Patient 1"
    When laboratory staff run the analyser
    Then running the analyser is refused with code "already_analysed"

  Scenario: The analyser cannot run before the sample is received
    Given a CBC order for "Test Patient 1"
    Then running the analyser is not offered for the order

  Scenario: A ferritin sample records the NHANES ferritin
    Given a received ferritin sample for "Test Patient 1"
    When laboratory staff run the analyser
    Then the sample has ferritin 11.0 ng/mL

  Scenario: Ferritin missing from NHANES
    Given patient "Test Patient 2" of "Dr. Demo A" without NHANES ferritin
    And a received ferritin sample for "Test Patient 2"
    When laboratory staff run the analyser
    Then the sample's ferritin is not available in the demo data
