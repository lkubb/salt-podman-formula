# vim: ft=sls

{#-
    Stops the podman service and disables it at boot time.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

Podman is dead:
  service.dead:
    - name: {{ podman.lookup.service.name }}.socket
    - enable: false
