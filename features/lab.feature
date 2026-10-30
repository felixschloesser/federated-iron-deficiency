Feature: Receiving and analysing samples
  Laboratory staff receive each order's sample and run the analyser, which
  returns the patient's NHANES 2021–2023 values. Covers R2, R3, R12.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32
    And "Test Patient 1" has NHANES CBC values and ferritin 11.0 ng/mL

  Scenario: Receiving registers the sample's tube
    Given a CBC order for "Test Patient 1"
    When laboratory staff receive the order
    Then the sample of "Test Patient 1" is received at the current time

  Scenario: A sample is received only once
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

  Scenario: The analyser has no tube for the sample ID
    Given a received CBC sample for "Test Patient 1"
    And the analyser stand-in has no values for the sample of "Test Patient 1"
    When laboratory staff run the analyser
    Then running the analyser is refused with code "no_tube"

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

  Scenario: A later test is measured on the stored sample
    Given an analysed CBC sample for "Test Patient 1"
    And a ferritin order for "Test Patient 1"
    Then the ferritin order is ready to analyse without being received
    When laboratory staff run the analyser
    Then the sample has ferritin 11.0 ng/mL
