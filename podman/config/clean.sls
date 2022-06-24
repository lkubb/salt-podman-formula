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
{%- if podman.mounts %}
      - {{ podman.lookup.config | path_join(podman.lookup.config_files.mounts) }}
{%- endif %}
{%- if podman.storage %}
      {{ podman.lookup.config | path_join(podman.lookup.config_files.storage) }}
{%- endif %}
    - require:
      - sls: {{ sls_service_clean }}
