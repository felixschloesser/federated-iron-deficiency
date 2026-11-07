Feature: Deploying a screening model
  Each training run sends a screening model to every hospital. It screens no one
  until the hospital's laboratory director deploys it at a threshold, after
  comparing its local validation at each threshold with the deployed model's.
  The threshold is the hospital's choice, made on its own past patients; the
  training run sets none. A hospital has one laboratory director.

  Background:
    Given laboratory director "Director One"
    And screening model "1" with local validation at threshold 0.5:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 7                  | 3                      |
      | not deficient   | 5                  | 37                     |
    And its local AUROC is 0.84
    And screening model "2" with local validation at threshold 0.5:
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
    And screening models "1" and "2" can be deployed

  Scenario: Deploying a screening model at a threshold
    When the laboratory director deploys screening model "2" at threshold 0.5
    Then "2" is the deployed model, at threshold 0.5
    And the deployment records local validation sensitivity 8 of 10 and specificity 36 of 42

  Scenario: Deploying the deployed model at another threshold
    Given screening model "1" also has local validation at threshold 0.4:
      |                 | ferritin suggested | ferritin not suggested |
      | deficient       | 9                  | 1                      |
      | not deficient   | 12                 | 30                     |
    And the laboratory director deployed "1" at threshold 0.5
    When the laboratory director deploys screening model "1" at threshold 0.4
    Then "1" is the deployed model, at threshold 0.4
    And the deployment history lists "1" at 0.5, "1" at 0.4

  Scenario: A threshold without local validation is refused
    When the laboratory director deploys screening model "1" at threshold 0.42
    Then deploying is refused with code "threshold_not_offered" on the threshold
    And there is no deployed model

  Scenario: Deploying an older screening model rolls back
    Given the laboratory director deployed "1", then "2", at threshold 0.5
    When the laboratory director deploys screening model "1" at threshold 0.5
    Then "1" is the deployed model, at threshold 0.5
    And the deployment history lists "1" at 0.5, "2" at 0.5, "1" at 0.5

  Scenario: Local validation is shown next to the deployed model's
    Given the laboratory director deployed "1" at threshold 0.5
    Then the screening models show "1", deployed, at threshold 0.5 with sensitivity 7 of 10, specificity 37 of 42, positive predictive value 7 of 12, negative predictive value 37 of 40, AUROC 0.84
    And they show "2", at threshold 0.5 with sensitivity 8 of 10, specificity 36 of 42, positive predictive value 8 of 14, negative predictive value 36 of 38, AUROC 0.86

  Scenario Outline: Each measure of local validation carries its 95% confidence interval
    Given a measure of <part> of <whole>
    Then it reads <percent>, with a 95% confidence interval of <interval>

    Examples:
      | part | whole | percent | interval |
      | 7    | 10    | 70%     | 40–89%   |
      | 0    | 10    | 0%      | 0–28%    |
      | 10   | 10    | 100%    | 72–100%  |
      | 0    | 0     | none    | none     |

  Scenario Outline: A screening model that cannot be deployed says why
    Given screening model "3" that <problem>
    Then screening model "3" cannot be deployed, with reason code "<code>"
    And deploying screening model "3" at threshold 0.5 is refused with code "<code>"

    Examples:
      | problem                              | code                     |
      | is not a readable model file         | unreadable               |
      | was trained on other features        | features_differ          |
      | has no local validation              | local_validation_missing |
      | has no standardization               | standardization_missing  |

  Scenario: A deployed model whose file changed on disk stops screening
    Given the file of the deployed "1" has changed on disk
    Then there is no usable deployed model, with reason code "deployed_model_changed"
    And the Models page says the deployed model changed on disk

  Scenario: Only the laboratory director deploys
    Given laboratory staff member "Lab One"
    When "Lab One" tries to deploy screening model "1" at threshold 0.5
    Then there is no deployed model
