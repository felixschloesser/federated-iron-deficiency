Feature: Deploying a final model
  Each training run sends a final model to every hospital. It screens no one
  until the hospital's laboratory director deploys it, after comparing its
  local validation with the deployed model's. Only a newer final model can be
  deployed: there is no rollback. Covers R17–R19.

  Background:
    Given laboratory director "Director One"
    And final models are stored in the order "run-1", "run-2"
    And final model "run-1" with local validation:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 7                  | 3                      |
      | not deficient   | 5                  | 37                     |
    And its local AUROC is 0.84
    And final model "run-2" with local validation:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 8                  | 2                      |
      | not deficient   | 6                  | 36                     |
    And its local AUROC is 0.86

  Scenario: A final model screens no one until it is deployed
    Then there is no deployed model
    And final models "run-1" and "run-2" can be deployed

  Scenario: Deploying a final model
    When the laboratory director deploys final model "run-2"
    Then "run-2" is the deployed model

  Scenario: An older final model cannot be deployed
    Given the laboratory director deployed "run-2"
    Then final model "run-1" cannot be deployed, with reason code "older_than_deployed"
    And deploying final model "run-1" is refused with code "older_than_deployed"
    And "run-2" is the deployed model

  Scenario: Local validation is shown next to the deployed model's
    Given the laboratory director deployed "run-1"
    Then the final models show "run-1", deployed, finding 7 of 10 deficient with 5 unnecessary suggestions, AUROC 0.84
    And they show "run-2", finding 8 of 10 deficient with 6 unnecessary suggestions, AUROC 0.86

  Scenario: Every deployment is kept, so each result can name its final model
    Given the laboratory director deployed "run-1"
    When the laboratory director deploys final model "run-2"
    Then the deployment history lists "run-1", then "run-2"

  Scenario Outline: A final model that cannot be deployed says why
    Given final model "run-3" that <problem>
    Then final model "run-3" cannot be deployed, with reason code "<code>"
    And deploying final model "run-3" is refused with code "<code>"

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
    When "Lab One" tries to deploy final model "run-1"
    Then there is no deployed model
