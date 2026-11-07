Feature: The startup releases final models; recipient hospitals fetch them
  A final model leaves the startup only after its data scientist released it,
  and only when a recipient hospital fetches it from the startup's
  final-models endpoint (P5, DF33). The startup knows each recipient
  hospital by its name; any hospital it registers is
  one, whether or not it trained. Each scenario's last step is its response
  measure, true or false.

  Background:
    Given the startup kept final model "7" with AUROC across hospitals 0.81
    And the startup knows hospital "UZ Leuven"

  Scenario: Releasing a final model records who released it
    When data scientist "Data One" releases final model "7"
    Then final model "7" is released by "Data One"

  Scenario: A final model not released cannot be fetched
    When "UZ Leuven" fetches new final models
    Then it receives no final model

  Scenario: A recipient hospital fetches a released final model's weights, AUROC across hospitals and run ID
    Given data scientist "Data One" released final model "7"
    When "UZ Leuven" fetches new final models
    Then it receives final model "7" with its weights and AUROC across hospitals 0.81
    And it receives no run configuration

  Scenario: A recipient hospital gets each released final model once
    Given data scientist "Data One" released final model "7"
    And "UZ Leuven" fetched new final models and acknowledged final model "7"
    When "UZ Leuven" fetches new final models
    Then it receives no final model

  Scenario: A hospital the startup does not know is refused
    Given data scientist "Data One" released final model "7"
    When "AZ Gent" fetches new final models
    Then fetching is refused as unknown hospital

  Scenario: A fetch that names no hospital is refused
    Given data scientist "Data One" released final model "7"
    When a hospital fetches new final models without naming itself
    Then fetching is refused as naming no hospital

  Scenario: A hospital whose name makes a registered hospital's slug is refused
    When the startup registers hospital "UZ-Leuven"
    Then registering is refused as a slug taken

  Scenario: A hospital that never trained may fetch
    Given the startup knows hospital "AZ Gent"
    And data scientist "Data One" released final model "7"
    When "AZ Gent" fetches new final models
    Then it receives final model "7" with its weights and AUROC across hospitals 0.81

  Scenario: The startup shows which hospitals fetched a final model
    Given data scientist "Data One" released final model "7"
    And "UZ Leuven" fetched new final models and acknowledged final model "7"
    When the data scientist opens the final models
    Then final model "7" shows "Fetched by UZ Leuven"
