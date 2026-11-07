Feature: Providing the training cohort
  The startup's code at this hospital (its ClientApp) trains on the training
  cohort, and only once the laboratory director has provided it. Providing
  extracts it from the laboratory's lab records: eligible past patients with a
  complete CBC ordered for a screened indication, a ferritin and a CRP result,
  as the 13 CBC values, age and whether iron deficient (WHO: ferritin below 15
  ng/mL, or below 70 ng/mL with inflammation, CRP above 5 mg/L); nothing else. Before deciding, the director
  sees how many past patients it holds, never their records. The director may
  withdraw it at any time; the startup's code then finds none. Each decision
  is recorded with who made it, when, and the cohort's SHA-256.
  Each scenario's last step is its response measure, true or false.

  Background:
    Given laboratory director "Director One"
    And lab records of 120 eligible past patients, 20 of them iron deficient
    And lab records of 30 patients who are not eligible
    And lab records of 5 eligible past patients without a ferritin result

  Scenario: Before providing, the director sees how many past patients it would hold
    Then no training cohort is provided
    And providing would hold 120 past patients, 20 of them iron deficient

  Scenario: A CBC ordered at the start of pregnancy stays out of the training cohort
    Given lab records of 5 eligible past patients whose CBC was ordered at the start of pregnancy
    Then providing would hold 120 past patients, 20 of them iron deficient

  Scenario: With inflammation, ferritin below 70 counts as iron deficient
    Given lab records of 4 eligible past patients with inflammation and ferritin 40
    When the laboratory director provides the training cohort
    Then the startup's code at this hospital finds 124 rows, 24 of them labelled iron deficient
    And providing would hold 124 past patients, 24 of them iron deficient

  Scenario: A past patient without a CRP result stays out, and is counted
    Given lab records of 3 eligible past patients without a CRP result
    When the laboratory director provides the training cohort
    Then the startup's code at this hospital finds 120 rows of the 13 CBC values, age and the label, and nothing else
    And providing would hold 120 past patients, 20 of them iron deficient
    And providing would leave out 3 eligible past patients without a CRP result

  Scenario: Providing the training cohort
    When the laboratory director provides the training cohort
    Then the startup's code at this hospital finds 120 rows of the 13 CBC values, age and the label, and nothing else
    And the training cohort is provided by "Director One", with its SHA-256

  Scenario: Withdrawing the training cohort
    Given the laboratory director provided the training cohort
    When the laboratory director withdraws the training cohort
    Then the startup's code at this hospital finds no training cohort
    And the training cohort is recorded as withdrawn by "Director One"

  Scenario: Withdrawing when none is provided is refused
    When the laboratory director withdraws the training cohort
    Then withdrawing is refused with code "nothing_provided"

  Scenario: Providing again after new lab records replaces the training cohort
    Given the laboratory director provided the training cohort
    And lab records of 5 more eligible past patients, none of them iron deficient
    When the laboratory director provides the training cohort
    Then the startup's code at this hospital finds 125 rows of the 13 CBC values, age and the label, and nothing else
    And the earlier training cohort is recorded as withdrawn by "Director One"

  Scenario: Providing an unchanged training cohort is refused
    Given the laboratory director provided the training cohort
    When the laboratory director provides the training cohort
    Then providing is refused with code "unchanged"

  Scenario Outline: Providing a training cohort too small to train on is refused
    Given the lab records hold only <past patients> eligible past patients, <deficient> of them iron deficient
    When the laboratory director provides the training cohort
    Then providing is refused with code "<code>"
    And the startup's code at this hospital finds no training cohort

    Examples:
      | past patients | deficient | code                       |
      | 99            | 20        | too_few_past_patients      |
      | 120           | 9         | too_few_iron_deficient     |
      | 120           | 111       | too_few_not_iron_deficient |

  Scenario: Only the laboratory director provides the training cohort
    Given laboratory staff member "Lab One"
    When "Lab One" tries to provide the training cohort
    Then no training cohort is provided
