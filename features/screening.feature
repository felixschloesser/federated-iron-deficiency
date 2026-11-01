Feature: Screening a CBC
  The deployed model screens a CBC only for suspected anaemia, suspected
  irritable bowel syndrome or unexplained fatigue in a woman aged 18–49. Only
  the result, the not-screened reason and the screening model that produced it are
  stored, never a score. Covers R4–R9, R19.
  Every analysed CBC gets a result and its lab report at once.

  Background:
    Given screening model "run-1" with threshold 0.5

  Scenario Outline: The model's decision becomes the result
    Given the laboratory director deployed "run-1"
    And a CBC sample of a woman aged 30 with indication unexplained fatigue
    And the deployed model scores the sample <side> the threshold
    When laboratory staff run the analyser
    Then the screening result is "<result>"

    Examples:
      | side  | result                  |
      | above | ferritin suggested      |
      | below | ferritin not suggested  |

  Scenario Outline: The lab report says only whether ferritin is suggested
    Given the laboratory director deployed "run-1"
    And a CBC sample of a woman aged 30 with indication unexplained fatigue
    And the deployed model scores the sample <side> the threshold
    When laboratory staff run the analyser
    Then the lab report is released <suggested> ferritin suggested

    Examples:
      | side  | suggested |
      | above | with      |
      | below | without   |

  Scenario Outline: A CBC for an indication the guidelines answer without ferritin is screened
    Given the laboratory director deployed "run-1"
    And a CBC sample with indication <indication>, registered sex female, aged 30
    When laboratory staff run the analyser
    Then the sample is screened by the model

    Examples:
      | indication                         |
      | suspected anaemia                  |
      | suspected irritable bowel syndrome |
      | unexplained fatigue                |

  Scenario Outline: Each failing condition gives its own reason, with or without a deployed model
    Given a CBC sample with indication <indication>, registered sex <sex>, aged <age>
    When laboratory staff run the analyser
    Then the screening result is "not screened" with reason "<reason>"
    And the lab report is released without ferritin suggested

    Examples:
      | indication             | sex    | age | reason     |
      | other                  | female | 30  | indication |
      | unexplained fatigue | male   | 30  | sex        |
      | unexplained fatigue | female | 17  | age        |
      | unexplained fatigue | female | 50  | age        |
      | other                  | male   | 70  | indication |
      | start of pregnancy     | female | 30  | indication |
      | chronic kidney disease follow-up | female | 30 | indication |

  Scenario Outline: The age range includes its ends
    Given the laboratory director deployed "run-1"
    And a CBC sample with indication unexplained fatigue, registered sex female, aged <age>
    When laboratory staff run the analyser
    Then the sample is screened by the model

    Examples:
      | age |
      | 18  |
      | 49  |

  Scenario: The result records the screening model that produced it
    Given the laboratory director deployed "run-1"
    And a CBC sample of a woman aged 30 with indication unexplained fatigue
    When laboratory staff run the analyser
    Then the screening result records screening model "run-1", its SHA-256 and threshold 0.5

  Scenario: No score is stored
    Given the laboratory director deployed "run-1"
    And a CBC sample of a woman aged 30 with indication unexplained fatigue
    When laboratory staff run the analyser
    Then no stored field of the sample or its screening result holds a score

  Scenario Outline: Without a usable deployed model the CBC is released not screened
    Given <state>
    And a CBC sample of a woman aged 30 with indication unexplained fatigue
    When laboratory staff run the analyser
    Then the screening result is "not screened" with reason "<reason>"
    And the lab report is released without ferritin suggested

    Examples:
      | state                                                | reason                  |
      | no screening model has been deployed                     | no_deployed_model       |
      | the file of the deployed "run-1" has changed on disk | deployed_model_changed  |

  Scenario: A ferritin sample is never screened
    Given a ferritin sample of a woman aged 30
    When laboratory staff run the analyser
    Then the sample has no screening result
    And the lab report is released without ferritin suggested
