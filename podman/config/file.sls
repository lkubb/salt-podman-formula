# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- set sls_package_install = tplroot ~ '.package.install' %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - {{ sls_package_install }}

{%- if podman.config.global.mounts %}

Podman global mounts configuration is managed:
  file.managed:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.mounts) }}
    - contents: {{ podman.config.global.mounts | json }}
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
{%- endif %}

{%- if podman.config.global.storage %}

Podman global storage configuration is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.storage) }}
    - serializer: toml
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.config.global.storage | json }}
{%- endif %}

Podman global policy configuration is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.policy) }}
    - serializer: json
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.config.global.policy | json }}

Podman global registry configuration is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.registries) }}
    - serializer: toml
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.config.global.registries | json }}

Podman global container configuration is managed:
  file.serialize:
    - name: {{ podman.lookup.config | path_join(podman.lookup.config_files.containers) }}
    - serializer: toml
    - mode: '0644'
    - user: root
    - group: {{ podman.lookup.rootgroup }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ podman.config.global.containers | json }}

{%- for username, config in podman.config.user.items() %}
{%-   if salt["user.info"](username) %}
{%-     set primary_group = salt["user.primary_group"](username) %}
{%-     set xdg_config = salt["cmd.run_stdout"]("echo ${XDG_CONFIG_HOME:-$HOME/.config}/containers", runas=username) %}
{%-     if "mounts" in config %}

Podman mounts configuration is managed for user {{ username }}:
  file.managed:
    - name: {{ xdg_config | path_join(podman.lookup.config_files.mounts) }}
    - contents: {{ config.mounts | json }}
    - mode: '0644'
    - user: {{ username }}
    - group: {{ primary_group }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
{%-     endif %}

{%-     if "policy" in config %}

Podman policy configuration is managed for user {{ username }}:
  file.serialize:
    - name: {{ xdg_config | path_join(podman.lookup.config_files.policy) }}
    - serializer: json
    - mode: '0644'
    - user: {{ username }}
    - group: {{ primary_group }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ config.policy | json }}
{%-     endif %}

{%-     for scope in ["storage", "registries", "containers"] %}
{%-       if scope in config %}

Podman {{ scope }} configuration is managed for user {{ username }}:
  file.serialize:
    - name: {{ xdg_config | path_join(podman.lookup.config_files[scope]) }}
    - serializer: toml
    - mode: '0644'
    - user: {{ username }}
    - group: {{ primary_group }}
    - makedirs: True
    - require:
      - sls: {{ sls_package_install }}
    - dataset: {{ config[scope] | json }}
{%-       endif %}
{%-     endfor %}
{%-   endif %}
{%- endfor %}
