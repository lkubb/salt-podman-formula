# vim: ft=sls

{%- set tplroot = tpldir.split("/")[0] %}
{%- from tplroot ~ "/libtofsstack.jinja" import files_switch with context %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}
{%- set sls_config_file = tplroot ~ ".package.install" %}
{%- set sls_service_running = "" %}
{%- if podman.containers.values() | selectattr("rootless", "defined") | rejectattr("rootless") | list %}
{%-   set sls_service_running = tplroot ~ ".service.running" %}
{%- endif %}

include:
  - {{ sls_config_file }}
{%- if sls_service_running %}
  - {{ sls_service_running }}
{%- endif %}

{%- if podman.lookup.containers.user %}
{%-   set username = podman.lookup.containers.user.name %}
User account {{ username }} is present:
  group.present:
    - name: {{ username }}
    - system: {{ podman.lookup.user.system }}
    - gid: {{ podman.lookup.containers.user.get('gid', 'null') }}

  user.present:
    - name: {{ username }}
    - home: {{ podman.lookup.containers.base }}
    - createhome: true
    - system: {{ podman.lookup.user.system }}
    {%- for x in ['uid', 'gid'] %}
    - {{ x }}: {{ podman.lookup.containers.user.get(x, 'null') }}
    {%- endfor %}
    - require_in:
        - User session for {{ username }} is initialized at boot
{%- endif %}

{%- for cnt_name, cnt in podman.containers.items() %}
{%-   set rootless = cnt.get("rootless", True) %}
{%-   if rootless %}
{%-     if podman.lookup.containers.user %}
{%-       set username = podman.lookup.containers.user.name %}
{%-     else %}

User account for container {{ cnt_name }} is present:
  user.present:
    - name: {{ cnt_name }}
    - home: {{ podman.lookup.containers.base | path_join(cnt_name) }}
    - createhome: true
    - usergroup: true
    - system: {{ podman.lookup.user.system }}

{%-       set username = cnt_name %}
{%-     endif %}

User session for {{ username }} is initialized at boot:
  compose.lingering_managed:
    - name: {{ username }}
    - enable: true
    - require:
      - user: {{ username }}

Podman API for {{ username }} is enabled:
  compose.systemd_service_enabled:
    - name: podman.socket
    - user: {{ username }}
    - require:
      - User session for {{ username }} is initialized at boot

Podman API for {{ username }} is available:
  compose.systemd_service_running:
    - name: podman.socket
    - user: {{ username }}
    - require:
      - Podman API for {{ username }} is enabled
{%-   endif %}

{%-   if cnt.get("env_secrets") %}

Container {{ cnt_name }} secrets are present:
  podman.secret_present:
    - names:
{%-     for sname, sval in cnt.env_secrets | dictsort %}
      - {{ sname }}:
{%-       if sval is mapping %}
{%-         for param, val in sval.items() %}
        - {{ param }}: {{ val | json }}
{%-         endfor %}
{%-       else %}
        - data: {{ sval | json }}
{%-       endif %}
{%-     endfor %}
{%-     if rootless %}
    - user: {{ cnt_name }}
{%-     endif %}
    - require:
{%-     if rootless %}
      - Podman API for {{ username }} is available
{%-     else %}
      - sls: {{ sls_service_running }}
{%-     endif %}
    - require_in:
      - Container {{ cnt_name }} is present
{%-   endif %}

{%-   set secret_env = {} %}
{%-   for secret in cnt.get("env_secrets", {}) %}
{%-     do secret_env.update({secret: secret}) %}
{%-   endfor %}
{%-   do secret_env.update(cnt.get("secret_env", {})) %}

{%-   set labels = {"PODMAN_SYSTEMD_UNIT": cnt_name} %}
{%-   do labels.update(cnt.get("labels", {})) %}

Container {{ cnt_name }} is present:
  podman.present:
    - name: {{ cnt_name }}
    - image: {{ cnt.image }}
    - labels: {{ labels | json }}
{%-   if secret_env %}
    - secret_env: {{ secret_env | json }}
{%-   endif %}
{%-   for cparam, cval in cnt | dictsort %}
{%-     if cparam in ["autoupdate", "env_secrets", "generate_params", "image", "labels", "name", "secret_env", "user"] %}
{%-       continue %}
{%-     endif %}
    - {{ cparam }}: {{ cval | json }}
{%-   endfor %}
{%-   if rootless %}
    - user: {{ username }}
{%-   endif %}
    - require:
{%-   if rootless %}
      - Podman API for {{ username }} is available
{%-   else %}
      - sls: {{ sls_service_running }}
{%-   endif %}

{%- if podman.lookup.containers.user %}
{%-  set userunitdir = podman.lookup.containers.base | path_join(".config", "systemd", "user") %}
{%- else %}
{%-  set userunitdir = podman.lookup.containers.base | path_join(cnt_name, ".config", "systemd", "user") %}
{%- endif %}

Container {{ cnt_name }} systemd unit is installed:
  file.managed:
    - name: {{ ( userunitdir if rootless else "/etc/systemd/system" )
                 | path_join(cnt_name ~ ".service") }}
    - source: {{ files_switch(
                    [cnt_name ~ ".service.j2", "container.service.j2"],
                    config=podman,
                    lookup="Container {} systemd unit is installed".format(cnt_name),
                 )
              }}
    - mode: '0644'
    - user: {{ cnt_name if rootless else "root" }}
    - group: {{ cnt_name if rootless else mariadb.lookup.rootgroup }}
    - makedirs: true
    - template: jinja
    - require:
      - Container {{ cnt_name }} is present
    - context:
        name: {{ cnt_name }}
        generate_params: {{ cnt.get("generate_params", {}) | json }}
        user: {{ username if rootless else "root" }}
{%-   if rootless %}
  module.run:
    - user_service.daemon_reload:
        - user: {{ username }}
    - onchanges:
      - file: {{ userunitdir | path_join(cnt_name ~ ".service") }}
{%-   endif %}
{%- endfor %}
