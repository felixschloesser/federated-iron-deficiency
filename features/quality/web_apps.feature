Feature: Every web app runs with DEBUG off
  Quality attribute: security, as hardening. Each of the six web apps runs
  gunicorn with DEBUG off; WhiteNoise serves the stylesheets. The demo serves
  plain HTTP: the report's TLS (HTTPS, secure cookies, HSTS) is left out for
  simplicity. Only the seed commands that prepare runs set DJANGO_DEBUG, for
  themselves: seeding the demo accounts needs it. Each scenario's last step is
  its response measure, true or false.

  Scenario: No running service has DEBUG on
    Given the demo as compose.yaml declares it
    When the demo starts
    Then no service sets "DJANGO_DEBUG"

  @containers
  Scenario: A hospital's web app serves its pages and stylesheets with DEBUG off
    Given AZ Diest's web app is running as compose.yaml starts it
    When a browser asks it for the login page and that page's stylesheet
    Then both answer 200, the stylesheet as "text/css"
