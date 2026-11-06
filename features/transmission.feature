Feature: A final model reaches a hospital only when transmitted
  The real ServerApp and ClientApp, in their containers, on a small synthetic
  cohort: a training run keeps its final model at the startup; transmitting it
  stores it at the hospital under the training run's ID; transmitting it again
  changes nothing there (features/training.feature, features/final_models.feature).
  Each scenario's last step is its response measure, true or false.

  @containers
  Scenario: Train, transmit, transmit again
    Given the SuperLink and UZ Leuven's SuperNode and ClientApp are running
    When the data scientist trains for one round
    Then the startup keeps the run's final model and UZ Leuven stores none
    When the data scientist transmits that final model
    Then the transmitting run completes and UZ Leuven stores the final model under the training run's ID
    When the data scientist transmits it again
    Then that run completes too and UZ Leuven's copy is unchanged
