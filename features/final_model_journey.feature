Feature: A final model reaches a hospital only when its laboratory director fetches it
  The real ServerApp and ClientApp, in their containers, on a small synthetic
  cohort, and the startup's and the hospital's real web app containers: a
  training run keeps its final model at the startup; the hospital holds none
  until the data scientist releases it and the hospital fetches it over the
  final-models network; fetching again changes nothing
  (features/startup/release.feature, features/hospital/fetch.feature).
  Each scenario's last step is its response measure, true or false.

  @containers
  Scenario: Train, release, fetch, fetch again
    Given the SuperLink and UZ Leuven's SuperNode and ClientApp are running
    And Heilig Hart Leuven's SuperNode and ClientApp too, as FedAvg trains only with two hospitals
    When the data scientist trains for one round
    Then the startup keeps the run's final model and UZ Leuven stores none
    When the data scientist releases that final model
    Then UZ Leuven still stores none
    When UZ Leuven fetches new final models
    Then UZ Leuven stores the final model under the training run's ID, with its local validation
    When UZ Leuven fetches new final models again
    Then it fetches none and UZ Leuven's copy is unchanged
