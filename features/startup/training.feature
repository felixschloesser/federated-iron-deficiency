Feature: The startup's training runs
  The startup keeps every training run's final model, with the AUROC
  across hospitals. Its data scientist sees them on the startup's own web app.
  A training run sets no threshold: each hospital's laboratory director chooses
  one when deploying (features/hospital/deployment.feature).

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

  Scenario Outline: A final model file that is not whole is not listed
    Given the startup kept the final model of run "1" at 30 Oct 2026, 14:02
    And the startup's file of run "2" <problem>
    Then the startup's final models are "1"

    Examples:
      | problem                                   |
      | is not a readable model file              |
      | holds weights that do not fit the network |
      | lacks its weights                         |

  Scenario: Submitting a training run
    When the data scientist submits a training run
    Then the SuperLink receives a run without a screening threshold
    And the submission gives the run's ID

  Scenario: Submitting a training run with its run configuration
    When the data scientist submits a training run with:
      | rounds | local epochs | learning rate | weight decay | batch size | seed |
      | 5      | 2            | 0.05          | 0.0          | 128        | 7    |
    Then the SuperLink receives the run configuration:
      | key               | value |
      | num-server-rounds | 5     |
      | local-epochs      | 2     |
      | learning-rate     | 0.05  |
      | weight-decay      | 0.0   |
      | batch-size        | 128   |
      | model-seed        | 7     |
    And the run configuration sets no fraction of hospitals evaluating and no W&B key

  Scenario Outline: A run configuration out of bounds is refused
    When the data scientist submits a training run with <parameter> <value>
    Then the run configuration is refused on <parameter> with code "<code>"
    And the SuperLink receives no run

    Examples:
      | parameter     | value | code      |
      | batch size    | 16    | min_value |
      | rounds        | 0     | min_value |
      | rounds        | 21    | max_value |
      | local epochs  | 11    | max_value |
      | learning rate | 0     | min_value |
      | weight decay  | -0.1  | min_value |

  Scenario: The startup keeps each final model with its run configuration
    When the ServerApp keeps the final model of run "7" trained with run configuration:
      | key               | value              |
      | num-server-rounds | 5                  |
      | local-epochs      | 2                  |
      | learning-rate     | 0.05               |
      | weight-decay      | 0.0                |
      | batch-size        | 128                |
      | model-seed        | 7                  |
      | fraction-evaluate | 1.0                |
      | demo-dir          | /srv/demo          |
      | wandb-api-key     | secret             |
    Then final model "7" shows run configuration "Rounds 5, Local epochs 2, Learning rate 0.05, Weight decay 0.0, Batch size 128, Seed 7"
    And the startup's copy of final model "7" holds no W&B key and no folder

  Scenario: A SuperLink that refuses the run
    Given the SuperLink refuses runs
    When the data scientist submits a training run
    Then the submission is refused with code "superlink_refused"

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

  Scenario: Stopping a training run in progress
    Given the SuperLink knows run "7" is running
    When the data scientist stops training run "7"
    Then the SuperLink is asked to stop run "7"

  Scenario Outline: A stop the SuperLink does not carry out
    Given the SuperLink knows run "7" is running
    And the SuperLink <state>
    When the data scientist stops training run "7"
    Then stopping is refused with code "<code>"

    Examples:
      | state                  | code                   |
      | refuses to stop it     | superlink_refused_stop |
      | does not answer        | superlink_no_answer    |
