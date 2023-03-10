# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

{%- for cnt_name, cnt in podman.containers.items() %}
{%-   set rootless = cnt.get("rootless", True) %}

Container {{ cnt_name }} is dead:
  compose.systemd_service_dead:
    - name: {{ cnt_name }}
{%-   if rootless %}
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
{%-   endif %}

Container {{ cnt_name }} is disabled:
  compose.systemd_service_disabled:
    - name: {{ cnt_name }}
{%-   if rootless %}
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
{%-   endif %}
{%- endfor %}