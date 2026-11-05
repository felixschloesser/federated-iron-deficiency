Feature: Final models at each hospital
  After each training run the ClientApp's deploy handler stores the final model
  in the hospital's screening-models folder: a new file named after the Flower run
  ID, never overwriting one, with the threshold, the federated metrics the
  ServerApp sends, and its local validation on this hospital's validation
  split. Its metadata holds only this hospital's local validation and the
  federated aggregate, never another hospital's metrics.

  Background:
    Given a hospital's training cohort

  Scenario: Each run's final model is a file of its own
    When the ClientApp stores the final model of run 11
    Then the hospital holds "11.pt"
    And it holds the weights, standardization, threshold, run ID, when it was stored, the federated metrics and the local validation

  Scenario: A final model is never overwritten
    Given the ClientApp stored the final models of runs 11 and 12
    When the ClientApp stores the final model of run 11 again
    Then storing it is refused
    And "11.pt" is unchanged
    And the hospital holds "11.pt" and "12.pt"

  Scenario: Local validation is a confusion matrix at the threshold, and AUROC
    When the ClientApp stores the final model of run 11
    Then its local validation holds the four counts of its validation split and an AUROC

  Scenario: A hospital learns no other hospital's metrics
    When the ClientApp stores the final model of run 11
    Then its federated metrics are exactly the aggregate the ServerApp sent

  Scenario: The web app never reads half a final model
    Given the disk fills up while the final model of run 11 is written
    When the ClientApp stores the final model of run 11
    Then storing it fails
    And the hospital holds no final model
