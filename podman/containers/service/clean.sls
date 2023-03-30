# vim: ft=sls

{#-
    Stops the configured containers' services.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

{%- for cnt_name, cnt in podman.containers.items() %}
{%-   set rootless = cnt.get("rootless", True) %}

Container {{ cnt_name }} is dead:
  user_service.dead:
    - name: {{ cnt_name }}
    - enable: false
{%-   if rootless %}
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
{%-   endif %}
{%- endfor %}
