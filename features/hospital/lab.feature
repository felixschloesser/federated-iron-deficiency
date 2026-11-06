Feature: Analysing samples
  Each sample arrives with its lab order; laboratory staff run the analyser,
  which returns the patient's NHANES 2021–2023 values.

  Background:
    Given practice "De Ceder" sends samples of patient "Test Patient 1", registered sex female, aged 32
    And "Test Patient 1" has NHANES CBC values and ferritin 11.0 ng/mL

  Scenario: A lab order is ready to analyse as soon as it arrives
    Given a CBC order for "Test Patient 1"
    Then the CBC order is ready to analyse
    And its sample is not a stored sample

  Scenario: Running the analyser records the patient's CBC
    Given a CBC order for "Test Patient 1"
    When laboratory staff run the analyser
    Then the sample has the 13 NHANES CBC values of "Test Patient 1"

  Scenario: A sample is analysed only once
    Given an analysed CBC sample for "Test Patient 1"
    When laboratory staff run the analyser
    Then running the analyser is refused with code "already_analysed"

  Scenario: A sample analysed from another page is not analysed again
    Given a CBC order for "Test Patient 1"
    And laboratory staff opened the CBC order on two pages
    When laboratory staff run the analyser from the first page
    And laboratory staff run the analyser from the second page
    Then running the analyser is refused with code "already_analysed"
    And the CBC order keeps the analysis from the first page

  Scenario: The analyser has no tube for the sample ID
    Given a CBC order for "Test Patient 1"
    And the analyser stand-in has no values for the sample of "Test Patient 1"
    When laboratory staff run the analyser
    Then running the analyser is refused with code "no_tube"

  Scenario: A ferritin sample records the NHANES ferritin
    Given a ferritin order for "Test Patient 1"
    When laboratory staff run the analyser
    Then the sample has ferritin 11.0 ng/mL

  Scenario: Ferritin missing from NHANES
    Given patient "Test Patient 2" without NHANES ferritin
    And a ferritin order for "Test Patient 2"
    When laboratory staff run the analyser
    Then the sample's ferritin is not available in the demo data

  Scenario: A later test is measured on the stored sample
    Given an analysed CBC sample for "Test Patient 1"
    And a ferritin order on that sample
    Then the ferritin order is ready to analyse
    And its sample is a stored sample
    When laboratory staff run the analyser
    Then the sample has ferritin 11.0 ng/mL

  Scenario: Every sample of a patient measures the patient's NHANES values
    Given an analysed CBC sample for "Test Patient 1"
    And a CBC order for "Test Patient 1"
    When laboratory staff run the analyser
    Then the sample has the 13 NHANES CBC values of "Test Patient 1"

  Scenario: The lab never sees a patient's name
    Given a CBC order for "Test Patient 1"
    Then the lab's samples hold sample ID, registered sex, age, test, whether the indication is screened and results, and no general practitioner
    And the lab's records relate to nothing outside the hospital
