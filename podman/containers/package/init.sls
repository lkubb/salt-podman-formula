# vim: ft=sls

{#-
    Manages rootless user accounts, creates configured
    containers, secrets and installs the containers as services.
    Has a dependency on `podman.config`_ or `podman.service`_.,
    depending on if any container runs rootful or not.
#}

include:
  - .install
