Feature: Deploying a screening model
  Each training run sends a screening model to every hospital. It screens no one
  until the hospital's laboratory director deploys it, after comparing its
  local validation with the deployed model's. A hospital has one laboratory
  director.

  Background:
    Given laboratory director "Director One"
    And screening model "run-1" with local validation:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 7                  | 3                      |
      | not deficient   | 5                  | 37                     |
    And its local AUROC is 0.84
    And screening model "run-2" with local validation:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 8                  | 2                      |
      | not deficient   | 6                  | 36                     |
    And its local AUROC is 0.86

  Scenario: A hospital has one laboratory director
    When laboratory director "Director Two" is added to the hospital
    Then adding them is refused with code "one_laboratory_director"
    And the database refuses the second director

  Scenario: A screening model screens no one until it is deployed
    Then there is no deployed model
    And screening models "run-1" and "run-2" can be deployed

  Scenario: Deploying a screening model
    When the laboratory director deploys screening model "run-2"
    Then "run-2" is the deployed model

  Scenario: Deploying an older screening model rolls back
    Given the laboratory director deployed "run-1", then "run-2"
    When the laboratory director deploys screening model "run-1"
    Then "run-1" is the deployed model
    And the deployment history lists "run-1", "run-2", "run-1"

  Scenario: Local validation is shown next to the deployed model's
    Given the laboratory director deployed "run-1"
    Then the screening models show "run-1", deployed, with sensitivity 7 of 10, specificity 37 of 42, positive predictive value 7 of 12, negative predictive value 37 of 40, AUROC 0.84
    And they show "run-2", with sensitivity 8 of 10, specificity 36 of 42, positive predictive value 8 of 14, negative predictive value 36 of 38, AUROC 0.86

  Scenario Outline: A screening model that cannot be deployed says why
    Given screening model "run-3" that <problem>
    Then screening model "run-3" cannot be deployed, with reason code "<code>"
    And deploying screening model "run-3" is refused with code "<code>"

    Examples:
      | problem                              | code                     |
      | is not a readable model file         | unreadable               |
      | was trained on other features        | features_differ          |
      | has no threshold                     | threshold_missing        |
      | has no standardization               | standardization_missing  |

  Scenario: A deployed model whose file changed on disk stops screening
    Given the file of the deployed "run-1" has changed on disk
    Then there is no usable deployed model, with reason code "deployed_model_changed"
    And the Models page says the deployed model changed on disk

  Scenario: Only the laboratory director deploys
    Given laboratory staff member "Lab One"
    When "Lab One" tries to deploy screening model "run-1"
    Then there is no deployed model
