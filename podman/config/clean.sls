# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- set sls_service_clean = tplroot ~ '.service.clean' %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_service_clean }}

podman-config-clean-file-absent:
  file.absent:
    - names:
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.containers) }}
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.policy) }}
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.registries) }}
{%- if podman.config.global.mounts %}
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.mounts) }}
{%- endif %}
{%- if podman.config.global.storage %}
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.storage) }}
{%- endif %}
{%- for username, config in podman.config.user.items() %}
{%-   if salt["user.info"](username) %}
{%-     set xdg_config = salt["cmd.run_stdout"]("echo ${XDG_CONFIG_HOME:-$HOME/.config}/containers", runas=username) %}
{%-     for scope in ["mounts", "storage", "policy", "registries", "containers"] %}
{%-       if scope in config %}
      - {{ xdg_config | path_join(podman.lookup.config_files[scope]) }}
{%-       endif %}
{%-     endfor %}
{%-   endif %}
{%- endfor %}
    - require:
      - sls: {{ sls_service_clean }}
