Feature: The demo admits any SuperNode
  Quality attribute: security, as authentication; not in the demo. The
  report's control: the SuperLink admits only SuperNodes whose public key the
  startup registered (Flower's SuperNode authentication, over TLS). The demo
  runs every Flower connection with --insecure and admits any node, for
  simplicity. This scenario pins the gap so that it is not mistaken for the
  control. Its last step is its response measure, true or false.

  Scenario: Every Flower connection in the demo runs without TLS
    Given the demo as compose.yaml declares it
    When a SuperNode connects to the SuperLink
    Then every Flower component runs with "--insecure", and nothing else does
