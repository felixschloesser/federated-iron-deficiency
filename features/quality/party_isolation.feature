Feature: Each party's software and data stay inside its trust boundary
  Quality attribute: privacy, as isolation. A deployment is the one party PARTY
  names (hospital, practice or startup) and reads only its folder, DATA_DIR; it
  installs, migrates and serves only its own party's apps. Code under
  web/ imports from the training package only ml.cohort and ml.dataset; the
  hospital's also ml.final_model and ml.inference, the startup's also
  ml.final_model, to read its final models, never to screen (the audit
  checks that).
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
      | startup  | accounts_user          | "lab_", "nhanes_", "deployment_", "practice_"   |

  Scenario: A web app refuses a database outside its party's folder
    Given a hospital deployment in a folder of its own
    When its settings name a database elsewhere
    Then the web app does not start, naming "DATA_DIR"

  Scenario: A deployment is a party the code knows
    Given a hospital deployment in a folder of its own
    When its settings name the party "clinic"
    Then the web app does not start, naming "PARTY"

  Scenario: A deployment keeps its data in a folder of its own
    Given a hospital deployment in a folder of its own
    When its settings name no folder
    Then the web app does not start, naming "DATA_DIR"
