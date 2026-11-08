Feature: Collecting a sample and ordering tests on it
  A general practitioner collects a sample from one of their patients, then
  orders tests on it: blood is collected into the standard tubes first and the tests
  are chosen afterwards (a simplification of WHO LQMS 5-3, where the request
  comes first). The order carries only what the lab needs: the sample ID, the
  test, the clinical indication, registered sex and age. Ferritin is ordered
  only on suspicion: beside a lab report of the sample that suggests it.

  Background:
    Given general practitioner "Dr. Demo A" with patient "Test Patient 1", registered sex female, aged 32
    And "Dr. Demo A" collected a sample from "Test Patient 1"

  Scenario: A CBC order records the indication and copies sex and age
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then the order has test CBC and indication unexplained fatigue
    And the order has registered sex female and age 32

  Scenario: A CBC order without an indication is refused
    When "Dr. Demo A" orders a CBC for "Test Patient 1" without an indication
    Then the order is refused with code "indication_required"

  Scenario: A ferritin order has no indication
    Given the sample has a CBC lab report suggesting ferritin
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order has test ferritin and no indication

  Scenario: A ferritin order with an indication is refused
    Given the sample has a CBC lab report suggesting ferritin
    When "Dr. Demo A" orders ferritin for "Test Patient 1" with indication other
    Then the order is refused with code "indication_not_applicable"

  Scenario: Ferritin without a suggestion is refused
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order is refused with code "ferritin_not_suggested" on field "test"

  Scenario: Ferritin beside a lab report without a suggestion is refused
    Given the sample has a CBC lab report without a suggestion
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order is refused with code "ferritin_not_suggested" on field "test"

  Scenario: An order's refusal is known before its indication is asked
    When "Dr. Demo A" asks whether ferritin can be ordered for "Test Patient 1"
    Then it would be refused with code "ferritin_not_suggested" on field "test"

  Scenario: A test the sample has is known to be refused before its form
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" asks whether a CBC can be ordered for "Test Patient 1"
    Then it would be refused with code "already_ordered"

  Scenario: A CBC on a fresh sample would not be refused, whatever its indication
    When "Dr. Demo A" asks whether a CBC can be ordered for "Test Patient 1"
    Then it would not be refused

  Scenario: A collected sample is the patient's, collected at the current time
    Then the sample is sample 1 of "Test Patient 1", collected at the current time

  Scenario: A sample takes the unused sample ID of the patient's sex nearest in age
    Given the practice's stock of sample IDs holds only "200001" (female, 50), "200002" (female, 34) and "200003" (male, 32)
    When "Dr. Demo A" collects a sample from "Test Patient 1"
    Then the sample is sample 2 of "Test Patient 1", with sample ID "200002"

  Scenario: A patient's samples carry different sample IDs
    When "Dr. Demo A" collects a sample from "Test Patient 1"
    Then the sample is sample 2 of "Test Patient 1", collected at the current time
    And the samples of "Test Patient 1" carry different sample IDs

  Scenario: Without a sample ID left for the patient collecting is refused
    Given the practice's stock of sample IDs holds only "200003" (male, 32)
    When "Dr. Demo A" collects a sample from "Test Patient 1"
    Then the collection is refused with code "no_sample_id" on field "sample_id"

  Scenario: The database holds each sample ID to one sample
    When a second sample with the first sample's ID is written straight to the database
    Then the database refuses it

  Scenario: Several tests go on one sample
    Given the sample has a CBC lab report suggesting ferritin
    When "Dr. Demo A" orders ferritin for "Test Patient 1"
    Then the order is on sample 1 of "Test Patient 1"

  Scenario: A test the sample already has is refused
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication other
    When "Dr. Demo A" orders a CBC for "Test Patient 1" with indication unexplained fatigue
    Then the order is refused with code "already_ordered"

  Scenario: The database holds the indication rule too
    When a CBC order without an indication is written straight to the database
    Then the database refuses it

  Scenario: A sample goes to the laboratory chosen when collecting it
    Given the practice works with laboratories "UZ Leuven" and "AZ Diest"
    When "Dr. Demo A" collects a sample from "Test Patient 1" for "AZ Diest"
    Then the sample goes to "AZ Diest"

  Scenario: The database holds every sample to a laboratory
    When a sample without a laboratory is written straight to the database
    Then the database refuses it

  Scenario: A practice has one primary laboratory
    Given the practice works with laboratories "UZ Leuven" and "AZ Diest"
    When "AZ Diest" is made the primary laboratory
    And "UZ Leuven" is made the primary laboratory
    Then "UZ Leuven" is the primary laboratory and "AZ Diest" is not

  Scenario: The database holds one primary laboratory too
    Given the practice works with laboratories "UZ Leuven" and "AZ Diest"
    When both are written straight to the database as primary
    Then the database refuses it

  Scenario: A rejected lab order keeps its reason for rejection and is sent no more
    Given "Dr. Demo A" ordered a CBC for "Test Patient 1" with indication unexplained fatigue
    When the laboratory rejects its lab order because "age: This field is required."
    Then the order records the reason for rejection "age: This field is required."
    And the order is not among the lab orders to send

  Scenario: The database holds no rejection without its reason
    When an order is written straight to the database as rejected without a reason
    Then the database refuses it
