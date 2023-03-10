# vim: ft=sls

{#-
    Starts the podman service and enables it at boot time.
    Has a dependency on `podman.config`_.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
{%- if podman.service_enable or podman.salt_compat %}
  - .running
{%- else %}
  - .clean
{%- endif %}
