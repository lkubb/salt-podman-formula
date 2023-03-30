# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_package_install = tplroot ~ ".containers.package.install" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

{%- for cnt_name, cnt in podman.containers.items() %}

Container {{ cnt_name }} is running:
  user_service.running:
    - name: {{ cnt_name }}
    - enable: true
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
{%-   endif %}
    - watch:
      - sls: {{ sls_package_install }}
{%- endfor %}
