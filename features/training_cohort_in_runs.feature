Feature: A training run trains on one training cohort per hospital
  The startup's code at a hospital (its ClientApp) trains only on the training
  cohort the hospital's laboratory director provided
  (features/hospital/training_cohort.feature). It notes which one in a run's
  first round; if the director withdraws or replaces it during the run, the
  hospital's next round fails rather than train on another cohort, and the
  run goes on without that hospital.
  Each scenario's last step is its response measure, true or false.

  Background:
    Given a hospital whose laboratory director provided the training cohort

  Scenario: A run trains on the provided training cohort
    When the startup's code at the hospital reads the training cohort in a run's first round
    Then it reads the provided training cohort's rows

  Scenario: A run's later round reads the same training cohort
    Given the startup's code at the hospital read the training cohort in a run's first round
    When it reads the training cohort in the run's next round
    Then it reads the provided training cohort's rows

  Scenario Outline: A change to the training cohort during a run fails the hospital's next round
    Given the startup's code at the hospital read the training cohort in a run's first round
    And the laboratory director <change>
    When it reads the training cohort in the run's next round
    Then reading fails, naming "<reason>"

    Examples:
      | change                                                       | reason                        |
      | withdrew the training cohort                                 | no training cohort            |
      | provided a new training cohort after new lab records arrived | training cohort changed       |

  Scenario: A hospital without a provided training cohort takes no part
    Given the laboratory director withdrew the training cohort
    When the startup's code at the hospital reads the training cohort in a run's first round
    Then reading fails, naming "no training cohort"

  Scenario: A new run trains on the training cohort provided since
    Given the startup's code at the hospital read the training cohort in a run's first round
    And the laboratory director provided a new training cohort after new lab records arrived
    When the startup's code at the hospital reads the training cohort in another run's first round
    Then it reads the provided training cohort's rows
