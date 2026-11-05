Feature: Screening a CBC
  The deployed model screens a CBC only for a screened indication (suspected
  anaemia, suspected irritable bowel syndrome or unexplained fatigue, which the
  lab order does not name) in a woman aged 18–49. Only the result, the
  not-screened reason and the screening model that produced it are stored,
  never a score; a CBC outside the screening is not eligible, never why.

  Every analysed CBC gets a result and its lab report at once.

  Background:
    Given screening model "run-1"

  Scenario Outline: The model's decision becomes the result
    Given the laboratory director deployed "run-1" at threshold 0.5
    And a CBC sample of a woman aged 30 for a screened indication
    And the deployed model scores the sample <side> the threshold
    When laboratory staff run the analyser
    Then the screening result is "<result>"

    Examples:
      | side  | result                  |
      | above | ferritin suggested      |
      | below | ferritin not suggested  |

  Scenario Outline: The lab report says only whether ferritin is suggested
    Given the laboratory director deployed "run-1" at threshold 0.5
    And a CBC sample of a woman aged 30 for a screened indication
    And the deployed model scores the sample <side> the threshold
    When laboratory staff run the analyser
    Then the lab report is released <suggested> ferritin suggested

    Examples:
      | side  | suggested |
      | above | with      |
      | below | without   |

  Scenario Outline: A CBC outside the screening is not eligible, never why
    Given a CBC sample <indication>, registered sex <sex>, aged <age>
    When laboratory staff run the analyser
    Then the screening result is "not screened" with reason "not_eligible"
    And the lab report is released without ferritin suggested

    Examples:
      | indication                       | sex    | age |
      | for an indication not screened   | female | 30  |
      | for a screened indication        | male   | 30  |
      | for a screened indication        | female | 17  |
      | for a screened indication        | female | 50  |
      | for an indication not screened   | male   | 70  |

  Scenario Outline: The age range includes its ends
    Given the laboratory director deployed "run-1" at threshold 0.5
    And a CBC sample for a screened indication, registered sex female, aged <age>
    When laboratory staff run the analyser
    Then the sample is screened by the model

    Examples:
      | age |
      | 18  |
      | 49  |

  Scenario: The result records the screening model that produced it
    Given the laboratory director deployed "run-1" at threshold 0.4
    And a CBC sample of a woman aged 30 for a screened indication
    When laboratory staff run the analyser
    Then the screening result records screening model "run-1", its SHA-256 and threshold 0.4

  Scenario: No score is stored
    Given the laboratory director deployed "run-1" at threshold 0.5
    And a CBC sample of a woman aged 30 for a screened indication
    When laboratory staff run the analyser
    Then no stored field of the sample or its screening result holds a score

  Scenario Outline: Without a usable deployed model the CBC is released not screened
    Given <state>
    And a CBC sample of a woman aged 30 for a screened indication
    When laboratory staff run the analyser
    Then the screening result is "not screened" with reason "<reason>"
    And the lab report is released without ferritin suggested

    Examples:
      | state                                                | reason                  |
      | no screening model has been deployed                 | no_deployed_model       |
      | the file of the deployed "run-1" has changed on disk | deployed_model_changed  |

  Scenario: A ferritin sample is never screened
    Given a ferritin sample of a woman aged 30
    When laboratory staff run the analyser
    Then the sample has no screening result
    And the lab report is released without ferritin suggested
