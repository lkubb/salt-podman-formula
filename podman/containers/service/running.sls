# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_package_install = tplroot ~ ".containers.package.install" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

{%- for cnt_name, cnt in podman.containers.items() %}

Container {{ cnt_name }} is enabled:
  compose.systemd_service_enabled:
    - name: {{ cnt_name }}
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
{%-   endif %}
    - require:
      - sls: {{ sls_package_install }}

Container {{ cnt_name }} is running:
  compose.systemd_service_running:
    - name: {{ cnt_name }}
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
{%-   endif %}
    - require:
      - sls: {{ sls_package_install }}
{%- endfor %}
