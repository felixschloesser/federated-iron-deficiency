Feature: The startup's code at a hospital reads only the cohort and writes nothing
  Quality attribute: privacy, as isolation. The ClientApp, the startup's code
  at each hospital (DF7, TB4), runs in a container of its own that mounts only
  the hospital's cohort, read-only: a final model enters the hospital only when
  its laboratory director fetches it (features/hospital/fetch.feature). It runs on a network it shares
  only with its hospital's SuperNode: it sees no database, no key and no other
  party's folder, and reaches neither the hospital's web app nor anything
  outside the demo, so what it sends leaves only through DF9 and DF10.
  Each scenario's last step is its response measure, true or false.

  Scenario Outline: compose.yaml gives the startup's code only the cohort, read-only
    Given the demo as compose.yaml declares it
    When the ClientApp at <hospital> starts
    Then it mounts only its hospital's cohort, read-only
    And it shares a network only with its hospital's SuperNode, and that network is internal

    Examples:
      | hospital           |
      | uz-leuven          |
      | heilig-hart-leuven |
      | az-diest           |

  Scenario: Only the hospitals' web apps reach the startup's final-models endpoint
    Given the demo as compose.yaml declares it
    When the demo starts
    Then the final-models network joins the startup's web app and every hospital's web app, and nothing else
    And the final-models network is internal

  @containers
  Scenario: The startup's running code finds only the cohort and reaches nothing
    Given the SuperLink and UZ Leuven's SuperNode and ClientApp are running
    And UZ Leuven's folder holds a database beside the cohort
    When the data scientist runs an app that lists every file it can read and every address it can reach
    Then the only files it finds are the cohort's
    And it reaches no address
