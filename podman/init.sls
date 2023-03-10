# vim: ft=sls

{#-
    *Meta-state*.

    This installs Podman,
    manages the Podman configuration,
    possibly starts the podman socket
    and creates and starts configured containers
    with their rootless user accounts.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - .package
  - .config
{%- if podman.salt_compat or podman.service_enable %}
  - .service
{%- endif %}
  - .containers
