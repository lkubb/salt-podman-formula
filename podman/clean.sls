# vim: ft=sls

{#-
    *Meta-state*.

    Undoes everything performed in the ``podman`` meta-state
    in reverse order, i.e.
    stops and deletes configured containers and their rootless user accounts,
    possibly stops the podman socket,
    removes the Podman configuration and
    uninstalls the Podman package.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - .containers.clean
{%- if podman.salt_compat or podman.service_enable %}
  - .service.clean
{%- endif %}
  - .config.clean
  - .package.clean
