Feature: The startup's training runs
  The startup keeps every training run's final model (DS4), with the threshold
  it was sent with and the AUROC across hospitals. Its data scientist sees them
  on the startup's own web app.

  Background:
    Given data scientist "Data One"

  Scenario: The startup keeps each final model with its threshold
    When the ServerApp keeps the final model of run "7" with threshold 0.4 and AUROC across hospitals 0.86
    Then the startup's final models are "7"
    And final model "7" shows threshold 0.4 and AUROC across hospitals 0.86

  Scenario: The final models are listed newest first
    Given the startup kept the final model of run "1" at 30 Oct 2026, 14:02
    And the startup kept the final model of run "2" at 31 Oct 2026, 09:15
    Then the startup's final models are "2", "1"

  Scenario: No final model yet
    Then the startup's final models are none
