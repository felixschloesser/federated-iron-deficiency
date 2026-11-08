Feature: A released final model reaches a hospital as a screening model only when its laboratory director fetches it
  The real ServerApp and ClientApp, in their containers, on a small synthetic
  cohort, and the startup's and the hospital's real web app containers: a
  training run keeps its final model at the startup; a hospital holds none until
  the data scientist releases it and the hospital fetches it as a screening
  model over the screening-models network, even AZ Diest, which never trained; fetching again
  changes nothing
  (features/startup/release.feature, features/hospital/fetch.feature).
  Each scenario's last step is its response measure, true or false.

  @containers
  Scenario: Train, release, fetch, fetch again
    Given the SuperLink and UZ Leuven's SuperNode and ClientApp are running
    And Heilig Hart Leuven's SuperNode and ClientApp too, as FedAvg trains only with two hospitals
    When the data scientist trains for one round
    Then the startup keeps the run's final model and UZ Leuven stores none
    When the data scientist releases that final model
    Then AZ Diest stores none yet
    When AZ Diest fetches new screening models
    Then AZ Diest stores the screening model under the training run's ID, with its local validation
    When AZ Diest fetches new screening models again
    Then it fetches none and AZ Diest's copy is unchanged
