# vim: ft=sls

{#-
    *Meta-state*.

    Manages rootless user accounts, creates configured
    containers, secrets and installs and runs the containers
    using systemd service units.
#}

include:
  - .package
  - .service
