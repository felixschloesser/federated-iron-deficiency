Feature: Final models at each hospital
  When the laboratory director fetches a final model (features/hospital/fetch.feature),
  the hospital's web app stores it in the screening-models folder: a new file named
  after its training run's ID, never overwriting one, with the federated metrics the startup sent,
  and its local validation on this hospital's test split, which no training run
  trained or was chosen on: a confusion
  matrix at each threshold the laboratory director may choose, and AUROC. The
  training run sets no threshold. Its metadata holds only this hospital's local validation and the
  federated aggregate, never another hospital's metrics.

  Background:
    Given a hospital's training cohort

  Scenario: Each run's final model is a file of its own
    When the hospital stores the final model of run 11
    Then the hospital holds "11.pt"
    And it holds the weights, standardization, run ID, when it was stored, the federated metrics and the local validation
    And it holds no threshold

  Scenario: A final model is never overwritten
    Given the hospital stored the final models of runs 11 and 12
    When the hospital stores the final model of run 11 again
    Then storing it is refused
    And "11.pt" is unchanged
    And the hospital holds "11.pt" and "12.pt"

  Scenario: Local validation is a confusion matrix at each threshold, and AUROC
    When the hospital stores the final model of run 11
    Then its local validation holds the four counts of its test split at each threshold from 0.05 to 0.95 in steps of 0.05
    And an AUROC

  Scenario: A hospital learns no other hospital's metrics
    When the hospital stores the final model of run 11
    Then its federated metrics are exactly the aggregate the ServerApp sent

  Scenario: The web app never reads half a final model
    Given the disk fills up while the final model of run 11 is written
    When the hospital stores the final model of run 11
    Then storing it fails
    And the hospital holds no final model

  Scenario: A fetched final model is stored under its training run's ID
    When the hospital receives the final model of run 11
    Then the hospital holds "11.pt"

  Scenario: A final model fetched again is kept as it was
    Given the hospital received the final model of run 11
    When the hospital receives the final model of run 11 again
    Then receiving it succeeds
    And "11.pt" is unchanged

  Scenario: Other weights fetched under a stored run's ID are refused
    Given the hospital received the final model of run 11
    When the hospital receives other weights as the final model of run 11
    Then receiving it is refused
    And "11.pt" is unchanged
