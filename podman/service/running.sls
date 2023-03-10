# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_config_file = tplroot ~ ".config.file" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_config_file }}

Podman is running:
  service.running:
    - name: {{ podman.lookup.service.name }}.socket
    - enable: true
    - watch:
      - sls: {{ sls_config_file }}
