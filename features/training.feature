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

  Scenario: Submitting a training run with a threshold
    When the data scientist submits a training run with threshold 0.4
    Then the SuperLink receives a run whose screening threshold is 0.4
    And the submission gives the run's ID

  Scenario Outline: A threshold outside 0 and 1 is refused
    When the data scientist submits a training run with threshold <threshold>
    Then the submission is refused with code "<code>" on the threshold
    And no run reaches the SuperLink

    Examples:
      | threshold | code                     |
      | 0         | threshold_not_above_zero |
      | -0.1      | threshold_not_above_zero |
      | 1         | threshold_not_below_one  |
      | 1.5       | threshold_not_below_one  |

  Scenario: A SuperLink that refuses the run
    Given the SuperLink refuses runs
    When the data scientist submits a training run with threshold 0.5
    Then the submission is refused with code "superlink_refused"
