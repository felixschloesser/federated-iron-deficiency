Feature: Each party's software and data stay inside its trust boundary
  Quality attribute: privacy, as isolation. Each party's web app has its own
  folder: a hospital's reads only HOSPITAL_DIR, a practice's only PRACTICE_DIR,
  the startup's only STARTUP_DIR, and each installs, migrates and serves only its own party's apps. Code under
  web/ imports from the training package only iron_deficiency.screening,
  iron_deficiency.cohort and iron_deficiency.dataset (the audit checks that).
  Each scenario's last step is its response measure, true or false.

  Scenario Outline: A party's database holds only its own party's tables
    Given a <party> deployment in a folder of its own
    When it migrates and seeds its database
    Then its database has the table "<own>"
    And its database has no table starting with <others>

    Examples:
      | party    | own                    | others                                          |
      | hospital | lab_laborder           | "practice_", "training_"                        |
      | practice | practice_patient       | "lab_", "nhanes_", "deployment_", "training_"   |
      | startup  | training_datascientist | "lab_", "nhanes_", "deployment_", "practice_"   |

  Scenario: A web app refuses a database outside its party's folder
    Given a hospital deployment in a folder of its own
    When its settings name a database elsewhere
    Then the web app does not start, naming "HOSPITAL_DIR"

  Scenario: A deployment is one party
    Given a hospital deployment in a folder of its own
    When its settings also name a practice's folder
    Then the web app does not start, naming "PRACTICE_DIR"
