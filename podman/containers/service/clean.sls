# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

{%- for cnt_name, cnt in podman.containers.items() %}

Container {{ cnt_name }} is dead:
  compose.systemd_service_dead:
    - name: {{ cnt_name }}
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
{%-   endif %}

Container {{ cnt_name }} is disabled:
  compose.systemd_service_disabled:
    - name: {{ cnt_name }}
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
{%-   endif %}
{%- endfor %}
