# vim: ft=sls

{#-
    Starts the configured containers' services.
    Has a dependency on `podman.containers.package`_.
#}

include:
  - .running
