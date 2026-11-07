Feature: A hospital fetches final models when its laboratory director asks
  A final model enters the hospital only when its laboratory director fetches
  new final models: the hospital's own web app asks the startup's
  final-models endpoint with the hospital's certificate name (DF38), validates
  each final model on the hospital's validation split (DF39), stores it under
  its training run's ID (DF17) and acknowledges it. The startup's code at the
  hospital writes nothing there (tests/quality/security/test_compose.py).
  Each scenario's last step is its response measure, true or false.

  Background:
    Given a hospital's training cohort
    And the startup released final model "11"

  Scenario: Nothing enters the hospital until the laboratory director asks
    Then the hospital holds no final model

  Scenario: The laboratory director fetches new final models
    When the laboratory director fetches new final models
    Then the hospital holds "11.pt" with its local validation and the AUROC across hospitals
    And the startup is told the hospital stored final model "11"

  Scenario: A final model fetched again is never overwritten
    Given the laboratory director fetched new final models
    And the startup offers final model "11" again, with other weights
    When the laboratory director fetches new final models
    Then "11.pt" is unchanged

  Scenario: A startup that cannot be reached
    Given the startup cannot be reached
    When the laboratory director fetches new final models
    Then the page says the startup could not be reached
    And the hospital holds no final model

  Scenario: A hospital without a training cohort fetches nothing
    Given the laboratory director has not provided a training cohort
    When the laboratory director fetches new final models
    Then the page says to provide the training cohort first
    And the hospital holds no final model
    And the startup is not asked
