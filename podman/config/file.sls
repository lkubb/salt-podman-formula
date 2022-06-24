# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- set sls_package_install = tplroot ~ '.package.install' %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

{%- if podman.mounts %}

Podman mounts file is managed:
  file.managed:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.mounts) }}
    - contents: {{ podman.mounts | json }}
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
{%- endif %}

Podman policy file is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.policy) }}
    - serializer: json
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.policy | json }}

Podman registry configuration is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.registries) }}
    - serializer: toml
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.registries | json }}
