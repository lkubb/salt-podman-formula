# vim: ft=sls

{#-
    Removes rootless user accounts, configured
    containers, secrets and the containers' unit files.
    Has a dependency on `podman.containers.service.clean`_.
#}

{%- set tplroot = tpldir.split("/")[0] %}
{%- set sls_service_clean = tplroot ~ ".containers.service.clean" %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_service_clean }}

{%- for cnt_name, cnt in podman.containers.items() %}
{%-   set rootless = cnt.get("rootless", True) %}

Container {{ cnt_name }} systemd unit is removed:
  file.absent:
    - name: {{ ((podman.lookup.containers.base | path_join(cnt_name, ".config", "systemd", "user")) if rootless else "/etc/systemd/system")
                | path_join(cnt_name ~ ".service") }}
    - require:
      - sls: {{ sls_service_clean }}

Container {{ cnt_name }} is absent:
  podman.absent:
    - name: {{ cnt_name }}
{%-   if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
{%-   endif %}
    - require:
      - sls: {{ sls_service_clean }}

{%-   if cnt.get("env_secrets") %}

Container {{ cnt_name }} secrets are absent:
  podman.secret_absent:
    - names: {{ cnt.env_secrets | list | json }}
{%-     if cnt.get("rootless", True) %}
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
{%-     endif %}
    - require:
      - sls: {{ sls_service_clean }}
{%-   endif %}

{%-   if cnt.get("rootless", True) %}

Podman API for container {{ cnt_name }} is dead:
  compose.systemd_service_dead:
    - name: podman
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
    - require:
      - Container {{ cnt_name }} is absent
      - Container {{ cnt_name }} secrets are absent

Podman API for container {{ cnt_name }} is disabled:
  compose.systemd_service_disabled:
    - name: podman
    - user: {{ cnt_name }}
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
    - require:
      - Podman API for container {{ cnt_name }} is dead

User session for container {{ cnt_name }} is not initialized at boot:
  compose.lingering_managed:
    - name: {{ cnt_name }}
    - enable: false
    - onlyif:
      - fun: user.info
        name: {{ cnt_name }}
    - require:
      - Podman API for container {{ cnt_name }} is disabled

User account for container {{ cnt_name }} is absent:
  user.absent:
    - name: {{ cnt_name }}
    - purge: {{ cnt.get("clean_purge", false) }}
    - require:
      - User session for container {{ cnt_name }} is not initialized at boot
    - retry:
        attempts: 5
        interval: 2
{%-   endif %}
{%- endfor %}
