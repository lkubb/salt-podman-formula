# vim: ft=sls

{#-
    *Meta-state*.

    Undoes everything performed in the ``podman.compose`` meta-state
    in reverse order, i.e.
    stops and removes the configured containers' services,
    removes configured secrets and containers,
    removes rootless user accounts.
#}

include:
  - .service.clean
  - .package.clean
