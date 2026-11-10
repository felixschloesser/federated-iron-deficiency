Feature: Deploying a screening model
  Each training run sends a screening model to every hospital. It screens no one
  until the hospital's laboratory director deploys it. The director first sets
  a target sensitivity: the share of iron-deficient women the screening should
  suggest ferritin for, a policy of the hospital's own. Each screening model is
  deployed at the highest threshold that reaches the target on this hospital's
  test split, so it suggests ferritin for as few women as the target allows.
  The training run sets no threshold. A hospital has one laboratory director.

  Background:
    Given laboratory director "Director One"
    And screening model "1" with local validation:
      | threshold | deficient, suggested | deficient, not suggested | not deficient, suggested | not deficient, not suggested |
      | 0.2       | 10                   | 0                        | 20                       | 22                           |
      | 0.4       | 9                    | 1                        | 12                       | 30                           |
      | 0.5       | 7                    | 3                        | 5                        | 37                           |
    And its local AUROC is 0.84
    And screening model "2" with local validation:
      | threshold | deficient, suggested | deficient, not suggested | not deficient, suggested | not deficient, not suggested |
      | 0.1       | 10                   | 0                        | 30                       | 12                           |
      | 0.3       | 9                    | 1                        | 8                        | 34                           |
      | 0.6       | 8                    | 2                        | 6                        | 36                           |
    And its local AUROC is 0.86

  Scenario: A hospital has one laboratory director
    When laboratory director "Director Two" is added to the hospital
    Then adding them is refused with code "one_laboratory_director"
    And the database refuses the second director

  Scenario: A screening model screens no one until it is deployed
    Then there is no deployed screening model
    And there is no target sensitivity
    And screening models "1" and "2" can be deployed

  Scenario: Deploying before a target sensitivity is set is refused
    When the laboratory director deploys screening model "1"
    Then deploying is refused with code "no_target_sensitivity"
    And there is no deployed screening model

  Scenario: Setting the target sensitivity deploys nothing
    When the laboratory director sets the target sensitivity to 90%
    Then the target sensitivity is 90%, set by "Director One"
    And there is no deployed screening model

  Scenario: Only a target sensitivity on offer can be set
    When the laboratory director sets the target sensitivity to 75%
    Then setting it is refused with code "invalid_choice" on the target sensitivity
    And there is no target sensitivity
    And the database refuses a target sensitivity of 75%

  Scenario Outline: A screening model is deployed at the highest threshold that reaches the target
    Given the laboratory director set the target sensitivity to <target>%
    When the laboratory director deploys screening model "<run>"
    Then "<run>" is the deployed screening model, at threshold <threshold>, for target <target>%, deployed by "Director One"

    Examples:
      | target | run | threshold |
      | 100    | 1   | 0.2       |
      | 90     | 1   | 0.4       |
      | 85     | 1   | 0.4       |
      | 90     | 2   | 0.3       |
      | 80     | 2   | 0.6       |

  Scenario: The deployment records local validation at the threshold
    Given the laboratory director set the target sensitivity to 90%
    When the laboratory director deploys screening model "2"
    Then the deployment records local validation sensitivity 9 of 10 and specificity 34 of 42

  Scenario: Changing the target sensitivity redeploys the deployed screening model
    Given the laboratory director set the target sensitivity to 90%
    And the laboratory director deployed "1"
    When the laboratory director sets the target sensitivity to 100%
    Then "1" is the deployed screening model, at threshold 0.2, for target 100%, deployed by "Director One"
    And the deployment history lists "1" at 0.4 for 90%, "1" at 0.2 for 100%

  Scenario: A deployed screening model whose file changed is not redeployed at a new target
    Given the laboratory director set the target sensitivity to 90%
    And the file of the deployed "1" has changed on disk
    When the laboratory director sets the target sensitivity to 100%
    Then the target sensitivity is 100%, set by "Director One"
    And there is no usable deployed screening model, with reason code "deployed_model_changed"
    And the deployment history lists "1" at 0.4 for 90%

  Scenario: Deploying an older screening model rolls back
    Given the laboratory director set the target sensitivity to 90%
    And the laboratory director deployed "1", then "2"
    When the laboratory director deploys screening model "1"
    Then "1" is the deployed screening model, at threshold 0.4, for target 90%, deployed by "Director One"
    And the deployment history lists "1" at 0.4 for 90%, "2" at 0.3 for 90%, "1" at 0.4 for 90%

  Scenario: Local validation at the target is shown next to the deployed screening model's
    Given the laboratory director set the target sensitivity to 90%
    And the laboratory director deployed "1"
    Then the screening models show "1", deployed, at threshold 0.4 with sensitivity 9 of 10, specificity 30 of 42, positive predictive value 9 of 21, negative predictive value 30 of 31, AUROC 0.84
    And they show "2", at threshold 0.3 with sensitivity 9 of 10, specificity 34 of 42, positive predictive value 9 of 17, negative predictive value 34 of 35, AUROC 0.86

  Scenario Outline: Each measure of local validation carries its 95% confidence interval
    Given a measure of <part> of <whole>
    Then it reads <percent>, with a 95% confidence interval of <interval>

    Examples:
      | part | whole | percent | interval |
      | 7    | 10    | 70%     | 40–89%   |
      | 0    | 10    | 0%      | 0–28%    |
      | 10   | 10    | 100%    | 72–100%  |
      | 0    | 0     | none    | none     |

  Scenario Outline: The AUROC here carries its 95% confidence interval
    Given a local validation with AUROC <auroc> on <deficient> iron-deficient and <other> other past patients
    Then its AUROC has a 95% confidence interval of <interval>

    Examples:
      | auroc | deficient | other | interval  |
      | 0.84  | 10        | 42    | 0.68–1.00 |
      | 0.86  | 10        | 42    | 0.71–1.00 |
      | 0.84  | 84        | 170   | 0.78–0.90 |
      | 0.50  | 10        | 42    | 0.30–0.70 |

  Scenario Outline: Local validation says whether a screening model performs here as claimed across hospitals
    Given a local validation with AUROC <auroc> on 10 iron-deficient and 42 other past patients, and <federated> across hospitals
    Then it says the screening model "<verdict>"

    Examples:
      | auroc | federated | verdict                                     |
      | 0.84  | 0.87      | performs here as claimed across hospitals   |
      | 0.84  | 0.70      | performs here as claimed across hospitals   |
      | 0.50  | 0.87      | performs worse here than across hospitals   |
      | 0.50  | 0.20      | performs better here than across hospitals  |

  Scenario Outline: A screening model file that is not whole is not listed and cannot be deployed
    Given the laboratory director set the target sensitivity to 90%
    And screening model "3" that <problem>
    Then screening model "3" is not listed
    And deploying screening model "3" is refused with code "not_found"

    Examples:
      | problem                                          |
      | has no file                                      |
      | is not a readable model file                     |
      | was trained on other features                    |
      | lacks its weights                                |
      | misses an iron-deficient past patient at its lowest threshold |

  Scenario: A deployed screening model whose file changed on disk stops screening
    Given the laboratory director set the target sensitivity to 90%
    And the file of the deployed "1" has changed on disk
    Then there is no usable deployed screening model, with reason code "deployed_model_changed"
    And the Models page says the deployed screening model changed on disk

  Scenario: Only the laboratory director deploys
    Given the laboratory director set the target sensitivity to 90%
    And laboratory staff member "Lab One"
    When "Lab One" tries to deploy screening model "1"
    Then there is no deployed screening model
