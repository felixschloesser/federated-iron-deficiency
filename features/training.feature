Feature: The startup's training runs
  The startup keeps every training run's final model (DS4), with the AUROC
  across hospitals. Its data scientist sees them on the startup's own web app.
  A training run sets no threshold: each hospital's laboratory director chooses
  one when deploying (features/deployment.feature).

  Background:
    Given data scientist "Data One"

  Scenario: The startup keeps each final model with its AUROC across hospitals
    When the ServerApp keeps the final model of run "7" with AUROC across hospitals 0.86
    Then the startup's final models are "7"
    And final model "7" shows AUROC across hospitals 0.86

  Scenario: The final models are listed newest first
    Given the startup kept the final model of run "1" at 30 Oct 2026, 14:02
    And the startup kept the final model of run "2" at 31 Oct 2026, 09:15
    Then the startup's final models are "2", "1"

  Scenario: No final model yet
    Then the startup's final models are none

  Scenario: Submitting a training run
    When the data scientist submits a training run
    Then the SuperLink receives a run without a screening threshold
    And the submission gives the run's ID

  Scenario: A SuperLink that refuses the run
    Given the SuperLink refuses runs
    When the data scientist submits a training run
    Then the submission is refused with code "superlink_refused"

  Scenario: A final model for sale holds its weights only
    Given the startup kept the final model of run "7" at 30 Oct 2026, 14:02
    When the startup downloads final model "7" for sale
    Then the download holds the final model's weights
    And it holds no threshold, no standardization and no metrics: the buyer chooses and standardizes on its own cohort

  Scenario: No final model of a run the startup did not keep
    When the startup downloads final model "9" for sale
    Then there is nothing to download

  Scenario: A SuperLink that does not answer in time
    Given the SuperLink does not answer
    When the data scientist submits a training run
    Then the submission is refused with code "superlink_no_answer"
    And the submission waited at most 20 seconds

  Scenario: The training runs show each run's status, newest first
    Given the SuperLink knows the runs:
      | run | status             | pending at           | running at           | finished at          |
      | 6   | finished:completed | 2026-10-30 13:20:00Z | 2026-10-30 13:21:00Z | 2026-10-30 13:40:00Z |
      | 7   | running            | 2026-10-30 14:01:00Z | 2026-10-30 14:02:00Z | N/A                  |
      | 8   | pending            | 2026-10-30 14:05:00Z | N/A                  | N/A                  |
    Then the training runs are:
      | run | status    | since            |
      | 8   | Pending   | 2026-10-30 14:05 |
      | 7   | Running   | 2026-10-30 14:02 |
      | 6   | Completed | 2026-10-30 13:40 |

  Scenario: A failed training run says why
    Given the SuperLink knows run "9" failed with details "ServerApp raised an exception"
    Then training run "9" is "Failed", with details "ServerApp raised an exception"

  Scenario Outline: Without the SuperLink's answer the training runs' statuses are unknown
    Given the SuperLink <state>
    When the data scientist looks at the training runs
    Then looking is refused with code "<code>"

    Examples:
      | state                         | code                  |
      | does not answer               | superlink_no_answer   |
      | answers that it is unavailable | superlink_unavailable |
