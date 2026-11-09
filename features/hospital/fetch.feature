Feature: A hospital fetches screening models when its laboratory director asks
  A released final model reaches a hospital as a screening model, and only when
  its laboratory director fetches new screening models: the hospital's own web
  app asks the startup's screening-models endpoint as the hospital, by its name, saying
  which screening models it holds, validates each screening model on the hospital's test split
  and stores it under its training run's ID. The startup's code at the
  hospital writes nothing there (tests/quality/security/test_compose.py).
  Each scenario's last step is its response measure, true or false.

  Background:
    Given a hospital's training cohort
    And the startup released final model "11"

  Scenario: Nothing enters the hospital until the laboratory director asks
    Then the hospital holds no screening model

  Scenario: The laboratory director fetches new screening models
    When the laboratory director fetches new screening models
    Then the hospital holds "11.pt" with its local validation and the AUROC across hospitals

  Scenario: The next fetch tells the startup which screening models the hospital holds
    Given the laboratory director fetched new screening models
    When the laboratory director fetches new screening models
    Then the startup is told the hospital holds screening model "11"

  Scenario: A screening model fetched again is never overwritten
    Given the laboratory director fetched new screening models
    And the startup offers screening model "11" again, with other weights
    When the laboratory director fetches new screening models
    Then "11.pt" is unchanged

  Scenario: Weights that do not fit the network are not stored
    Given the startup released final model "12" with weights that do not fit the network
    When the laboratory director fetches new screening models
    Then the hospital holds only "11.pt"

  Scenario Outline: A screening model missing any part is not stored
    Given the startup released final model "12" without its <part>
    When the laboratory director fetches new screening models
    Then the hospital holds only "11.pt"

    Examples:
      | part            |
      | run_id          |
      | weights         |
      | federated_auroc |

  Scenario: A startup that cannot be reached
    Given the startup cannot be reached
    When the laboratory director fetches new screening models
    Then the page says the startup could not be reached
    And the hospital holds no screening model

  Scenario: A hospital without a training cohort fetches nothing
    Given the laboratory director has not provided a training cohort
    When the laboratory director fetches new screening models
    Then the page says to provide the training cohort first
    And the hospital holds no screening model
    And the startup is not asked
